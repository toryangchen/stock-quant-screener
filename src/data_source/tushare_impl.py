from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from datetime import datetime

import pandas as pd

from .base import DataSource
from .cache_mongo import MongoDataCache


class TushareDataSource(DataSource):
    def __init__(self, token: str | None = None) -> None:
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise RuntimeError("tushare 未安装，请先执行: pip install -r requirements.txt") from exc

        self.token = token or os.getenv("TUSHARE_TOKEN", "").strip()
        if not self.token:
            raise RuntimeError("未提供 Tushare Token，请设置环境变量 TUSHARE_TOKEN")

        ts.set_token(self.token)
        self.pro = ts.pro_api(self.token)
        self.logger = logging.getLogger("quant_screener")
        self.rate_limit_per_minute = int(os.getenv("TUSHARE_RATE_LIMIT_PER_MINUTE", "50"))
        self._request_timestamps: deque[float] = deque()
        self.cache = MongoDataCache()

        self.akshare_backup = None
        try:
            from .akshare_impl import AkShareDataSource

            self.akshare_backup = AkShareDataSource()
        except Exception:
            self.akshare_backup = None

    def _acquire_request_slot(self) -> None:
        while True:
            now = time.monotonic()
            while self._request_timestamps and now - self._request_timestamps[0] >= 60.0:
                self._request_timestamps.popleft()

            if len(self._request_timestamps) < self.rate_limit_per_minute:
                self._request_timestamps.append(now)
                return

            wait_sec = 60.0 - (now - self._request_timestamps[0]) + 0.01
            if wait_sec > 0:
                self.logger.info(
                    "Tushare 达到每分钟 %s 次上限，等待 %.1f 秒后继续",
                    self.rate_limit_per_minute,
                    wait_sec,
                )
                time.sleep(wait_sec)

    def _normalize_code(self, code: str) -> str:
        text = str(code).strip().lower()
        m = re.search(r"(\d{6})$", text)
        if m:
            return m.group(1)
        return text

    def _to_ts_code(self, code: str) -> str:
        text = str(code).strip().lower()
        if re.match(r"^\d{6}\.(sh|sz|bj)$", text):
            return text.upper()

        if text.startswith("sh") and len(text) >= 8:
            return f"{text[-6:]}.SH"
        if text.startswith("sz") and len(text) >= 8:
            return f"{text[-6:]}.SZ"
        if text.startswith("bj") and len(text) >= 8:
            return f"{text[-6:]}.BJ"

        m = re.search(r"(\d{6})$", text)
        digits = m.group(1) if m else text[-6:]

        if digits.startswith(("6", "5", "9")):
            return f"{digits}.SH"
        if digits.startswith("8"):
            return f"{digits}.BJ"
        return f"{digits}.SZ"

    def _normalize_daily_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["trade_date", "close", "vol"]].rename(
            columns={"trade_date": "date", "close": "close", "vol": "volume"}
        )
        out["date"] = pd.to_datetime(out["date"], format="%Y%m%d", errors="coerce")
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
        out = out.dropna(subset=["date", "close", "volume"]).sort_values("date").reset_index(drop=True)
        return out

    def _get_daily_by_trade_date(self, trade_date: str) -> pd.DataFrame:
        cache_key = f"tushare:daily_trade_date:{trade_date}"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        self._acquire_request_slot()
        df = self.pro.daily(trade_date=trade_date)
        if df is None or df.empty:
            return pd.DataFrame(columns=["ts_code", "trade_date", "close", "vol"])
        need_cols = ["ts_code", "trade_date", "close", "vol"]
        for col in need_cols:
            if col not in df.columns:
                raise ValueError(
                    f"缺少字段 '{col}'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}"
                )
        out = df[need_cols].copy()
        self.cache.set_df(cache_key, out)
        return out

    def get_stock_daily_bulk(self, codes: list[str], min_days: int = 60) -> dict[str, pd.DataFrame]:
        if not codes:
            return {}

        code_to_ts: dict[str, str] = {}
        for code in codes:
            norm_code = self._normalize_code(code)
            code_to_ts[norm_code] = self._to_ts_code(norm_code)

        result: dict[str, pd.DataFrame] = {}
        missing_codes: list[str] = []
        for code, ts_code in code_to_ts.items():
            cache_key = f"tushare:stock_daily:{ts_code}"
            cached = self.cache.get_df(cache_key)
            if cached is not None and len(cached) >= min_days:
                result[code] = cached.sort_values("date").reset_index(drop=True)
            else:
                missing_codes.append(code)

        if not missing_codes:
            return result

        ts_need = {code_to_ts[c] for c in missing_codes}
        collected: dict[str, list[dict]] = {c: [] for c in missing_codes}
        trade_dates: list[str] = []

        cursor = datetime.now()
        looked_back_days = 0
        # 为获取 60 个交易日，通常回看 90~120 个自然日足够，这里上限 240 天
        while len(trade_dates) < min_days and looked_back_days < 240:
            date_str = cursor.strftime("%Y%m%d")
            day_df = self._get_daily_by_trade_date(date_str)
            if not day_df.empty:
                trade_dates.append(date_str)
                day_df = day_df[day_df["ts_code"].isin(ts_need)]
                if not day_df.empty:
                    for _, r in day_df.iterrows():
                        norm_code = self._normalize_code(str(r["ts_code"]).split(".")[0])
                        if norm_code in collected:
                            collected[norm_code].append(
                                {
                                    "date": r["trade_date"],
                                    "close": r["close"],
                                    "volume": r["vol"],
                                }
                            )
            cursor = cursor - pd.Timedelta(days=1)
            looked_back_days += 1

        for code in missing_codes:
            rows = collected.get(code, [])
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
                df = df.dropna(subset=["date", "close", "volume"]).sort_values("date").reset_index(drop=True)
                if not df.empty:
                    result[code] = df
                    self.cache.set_df(f"tushare:stock_daily:{code_to_ts[code]}", df, tail_rows=60)
                    continue

            # 批量模式未覆盖时，再回退单票拉取
            try:
                result[code] = self.get_stock_daily(code)
            except Exception:
                continue

        return result

    def get_a_spot(self) -> pd.DataFrame:
        cache_key = "tushare:a_spot"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        try:
            self._acquire_request_slot()
            df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
            if df is None or df.empty:
                raise RuntimeError("Tushare stock_basic 返回空数据")

            out = df.rename(columns={"ts_code": "code", "name": "name"}).copy()
            out["code"] = out["code"].astype(str).str.split(".").str[0].map(self._normalize_code)
            out["name"] = out["name"].astype(str)
            out = out[["code", "name"]]
            self.cache.set_df(cache_key, out)
            return out
        except Exception as exc:
            if self.akshare_backup is None:
                raise
            self.logger.warning("Tushare stock_basic 不可用，回退 AkShare 股票池: %s", exc)
            out = self.akshare_backup.get_a_spot()
            self.cache.set_df("akshare:a_spot", out)
            return out

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        ts_code = self._to_ts_code(code)
        cache_key = f"tushare:stock_daily:{ts_code}"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        end_date = datetime.now().strftime("%Y%m%d")
        self._acquire_request_slot()
        df = self.pro.daily(ts_code=ts_code, start_date="19900101", end_date=end_date)

        if df is None or df.empty:
            raise RuntimeError(f"Tushare daily 返回空数据: {ts_code}")

        for col in ["trade_date", "close", "vol"]:
            if col not in df.columns:
                raise ValueError(
                    f"缺少字段 '{col}'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}"
                )

        out = self._normalize_daily_frame(df)
        self.cache.set_df(cache_key, out, tail_rows=60)
        return out

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        market_code = self._to_ts_code(code).split(".")[0]
        cache_key = f"akshare:etf_daily:{market_code}"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        if self.akshare_backup is None:
            raise RuntimeError("当前 Token 无 fund_daily 权限，且 AkShare 备用源不可用")
        out = self.akshare_backup.get_etf_daily(code)
        self.cache.set_df(cache_key, out, tail_rows=120)
        return out
