from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime

import pandas as pd

from .base import DataSource
from .cache_mongo import MongoDataCache


class AkShareDataSource(DataSource):
    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise RuntimeError("akshare 未安装，请先执行: pip install -r requirements.txt") from exc
        self.ak = ak
        self.cache = MongoDataCache()

    def _pick_col(self, df: pd.DataFrame, candidates: Iterable[str], target: str) -> str:
        for col in candidates:
            if col in df.columns:
                return col
        raise ValueError(f"缺少字段 '{target}'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}")

    def _to_market_symbol(self, code: str) -> str:
        raw = str(code).strip().lower()
        if raw.startswith(("sh", "sz", "bj")):
            return raw

        m = re.search(r"(\d{6})$", raw)
        digits = m.group(1) if m else raw[-6:]

        if digits.startswith(("6", "5", "9")):
            return f"sh{digits}"
        if digits.startswith(("0", "1", "2", "3", "4", "8")):
            return f"sz{digits}"
        return f"sh{digits}"

    def _normalize_code(self, code: str) -> str:
        text = str(code).strip()
        low = text.lower()
        if low.startswith(("sh", "sz", "bj")) and len(low) >= 8:
            return low
        m = re.search(r"(\d{6})$", text)
        return m.group(1) if m else text

    def _normalize_daily(self, df: pd.DataFrame, volume_optional: bool = False) -> pd.DataFrame:
        date_col = self._pick_col(df, ["日期", "date", "Date", "交易日期"], "date")
        close_col = self._pick_col(df, ["收盘", "close", "Close"], "close")

        vol_col = None
        for candidate in ["成交量", "volume", "Volume", "成交量(手)", "amount", "成交额"]:
            if candidate in df.columns:
                vol_col = candidate
                break

        if vol_col is None and not volume_optional:
            raise ValueError(f"缺少字段 'volume'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}")

        if vol_col is None:
            out = df[[date_col, close_col]].copy()
            out.columns = ["date", "close"]
            out["volume"] = pd.NA
        else:
            out = df[[date_col, close_col, vol_col]].copy()
            out.columns = ["date", "close", "volume"]

        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")

        required_cols = ["date", "close"] if volume_optional else ["date", "close", "volume"]
        out = out.dropna(subset=required_cols).sort_values("date")
        out = out.reset_index(drop=True)
        return out

    def _run_with_fallback(self, candidates: list[tuple[str, Callable[[], pd.DataFrame]]]) -> pd.DataFrame:
        errors: list[str] = []
        for name, func in candidates:
            try:
                df = func()
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df
                errors.append(f"{name}: empty dataframe")
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        preview = " | ".join(errors[:4])
        raise RuntimeError(f"所有备用接口均失败: {preview}")

    def get_a_spot(self) -> pd.DataFrame:
        cache_key = "akshare:a_spot"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        df = self._run_with_fallback(
            [
                ("stock_zh_a_spot_em", lambda: self.ak.stock_zh_a_spot_em()),
                ("stock_zh_a_spot", lambda: self.ak.stock_zh_a_spot()),
                ("stock_info_a_code_name", lambda: self.ak.stock_info_a_code_name()),
            ]
        )

        code_col = self._pick_col(df, ["代码", "code", "symbol"], "code")
        name_col = self._pick_col(df, ["名称", "name"], "name")

        keep_cols = [code_col, name_col]
        mktcap_col = None
        for candidate in ["总市值", "总市值(元)", "mktcap", "总市值-亿"]:
            if candidate in df.columns:
                mktcap_col = candidate
                keep_cols.append(mktcap_col)
                break

        out = df[keep_cols].copy()
        rename_map = {code_col: "code", name_col: "name"}
        if mktcap_col:
            rename_map[mktcap_col] = "mktcap"
        out = out.rename(columns=rename_map)

        out["code"] = out["code"].map(self._normalize_code)
        out["name"] = out["name"].astype(str)
        if "mktcap" in out.columns:
            out["mktcap"] = pd.to_numeric(out["mktcap"], errors="coerce")

        self.cache.set_df(cache_key, out)
        return out

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        market_symbol = self._to_market_symbol(code)
        cache_key = f"akshare:stock_daily:{market_symbol}"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        def hist_raw() -> pd.DataFrame:
            return self.ak.stock_zh_a_hist(
                symbol=str(code),
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )

        def hist_market() -> pd.DataFrame:
            return self.ak.stock_zh_a_hist(
                symbol=market_symbol,
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )

        df = self._run_with_fallback(
            [
                ("stock_zh_a_hist(raw)", hist_raw),
                ("stock_zh_a_hist(market)", hist_market),
                ("stock_zh_a_daily", lambda: self.ak.stock_zh_a_daily(symbol=market_symbol, adjust="qfq")),
                ("stock_zh_a_hist_tx", lambda: self.ak.stock_zh_a_hist_tx(symbol=market_symbol, adjust="qfq")),
            ]
        )
        out = self._normalize_daily(df, volume_optional=False)
        self.cache.set_df(cache_key, out)
        return out

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        market_symbol = self._to_market_symbol(code)
        cache_key = f"akshare:etf_daily:{market_symbol}"
        cached = self.cache.get_df(cache_key)
        if cached is not None and not cached.empty:
            return cached

        def em_raw() -> pd.DataFrame:
            return self.ak.fund_etf_hist_em(
                symbol=str(code),
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )

        def em_market() -> pd.DataFrame:
            return self.ak.fund_etf_hist_em(
                symbol=market_symbol,
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )

        df = self._run_with_fallback(
            [
                ("fund_etf_hist_em(raw)", em_raw),
                ("fund_etf_hist_em(market)", em_market),
                ("fund_etf_hist_sina", lambda: self.ak.fund_etf_hist_sina(symbol=market_symbol)),
            ]
        )
        out = self._normalize_daily(df, volume_optional=True)
        self.cache.set_df(cache_key, out)
        return out
