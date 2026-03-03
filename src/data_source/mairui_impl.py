from __future__ import annotations

import logging
import os
import time
import re
from datetime import datetime

import pandas as pd
import requests

from .base import DataSource
from .cache_mongo import MongoDataCache


class MairuiDataSource(DataSource):
    def __init__(self, token: str | None = None) -> None:
        self.logger = logging.getLogger("quant_screener")
        self.base_url = os.getenv("MAIRUI_BASE_URL", "https://api.mairui.club").rstrip("/")
        self.token = (
            token
            or os.getenv("MAIRUI_TOKEN", "").strip()
            or "AA4F715E-79CE-4318-A469-3C2365C2CC49"
        ).strip()
        if not self.token:
            raise RuntimeError("未提供 Mairui token，请设置 MAIRUI_TOKEN")

        self.cache = MongoDataCache()
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        self.rate_limit_per_sec = max(1, int(os.getenv("MAIRUI_RATE_LIMIT_PER_SEC", "8")))
        self._last_request_ts = 0.0

        self.tushare_backup = None
        self.akshare_backup = None
        ts_token = os.getenv("TUSHARE_TOKEN", "").strip()
        if ts_token:
            try:
                from .tushare_impl import TushareDataSource

                self.tushare_backup = TushareDataSource(token=ts_token)
            except Exception as exc:
                self.logger.warning("Mairui 备用 Tushare 初始化失败: %s", exc)
        try:
            from .akshare_impl import AkShareDataSource

            self.akshare_backup = AkShareDataSource()
        except Exception as exc:
            self.logger.warning("Mairui 备用 AkShare 初始化失败: %s", exc)

    def _throttle(self) -> None:
        now = time.monotonic()
        min_interval = 1.0 / float(self.rate_limit_per_sec)
        elapsed = now - self._last_request_ts
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_ts = time.monotonic()

    def _get_json(self, path: str):
        self._throttle()
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self._http.get(url, timeout=12)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _norm_code(code: str) -> str:
        text = str(code).strip().lower()
        m = re.search(r"(\d{6})", text)
        if m:
            return m.group(1)
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 6:
            return digits[-6:]
        return digits.zfill(6) if digits else text

    def _stock_cache_key(self, code: str) -> str:
        return self._norm_code(code)

    def _load_today_snapshot(self) -> pd.DataFrame:
        today = datetime.now().strftime("%Y%m%d")
        key = f"mairui:daily_snapshot:{today}"
        cached = self.cache.get_df(key)
        if cached is None or cached.empty:
            return pd.DataFrame()
        return cached

    def has_today_snapshot(self) -> bool:
        snap = self._load_today_snapshot()
        return snap is not None and not snap.empty

    def _fetch_stock_list(self) -> pd.DataFrame:
        raw = self._get_json(f"hslt/list/{self.token}")
        if not isinstance(raw, list) or not raw:
            raise RuntimeError("Mairui 股票列表返回空数据")
        df = pd.DataFrame(raw)
        for c in ["dm", "mc", "jys"]:
            if c not in df.columns:
                raise ValueError(f"Mairui 列表缺少字段: {c}")
        return pd.DataFrame(
            {
                "code": df["dm"].astype(str).map(self._norm_code),
                "name": df["mc"].astype(str),
                "exchange": df["jys"].astype(str),
            }
        )

    def get_a_spot(self, force_refresh: bool = False) -> pd.DataFrame:
        cache_key = "mairui:a_spot"
        if not force_refresh:
            cached = self.cache.get_df(cache_key)
            if cached is not None and not cached.empty and "mktcap" in cached.columns:
                return cached

        out = self._fetch_stock_list()

        # 合并当日快照市值
        snap = self._load_today_snapshot()
        if not snap.empty and {"code", "mktcap"}.issubset(snap.columns):
            out = out.merge(snap[["code", "mktcap"]], on="code", how="left")
        self.cache.set_df(cache_key, out)
        return out

    def _append_history_row(self, code: str, row: dict) -> None:
        key = self._stock_cache_key(code)
        hist = self.cache.get_df(key)
        if hist is None or hist.empty:
            hist = pd.DataFrame(columns=["date", "close", "volume", "low"])
        if "mktcap" in hist.columns:
            hist = hist.drop(columns=["mktcap"])

        new_row = pd.DataFrame(
            [
                {
                    "date": row.get("date"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "low": row.get("low"),
                }
            ]
        )
        merged = new_row if hist.empty else pd.concat([hist, new_row], ignore_index=True)
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        merged["close"] = pd.to_numeric(merged["close"], errors="coerce")
        merged["volume"] = pd.to_numeric(merged["volume"], errors="coerce")
        merged["low"] = pd.to_numeric(merged["low"], errors="coerce")
        merged = merged.dropna(subset=["date", "close", "volume", "low"])
        merged = merged.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        mktcap = pd.to_numeric(row.get("mktcap"), errors="coerce")
        self.cache.set_df(
            key,
            merged,
            tail_rows=60,
            meta={"mktcap": float(mktcap) if pd.notna(mktcap) else None},
        )

    def sync_market_daily(self) -> dict[str, int]:
        # 每次同步都强制拉最新全市场列表，补齐新上市/新增代码
        spot = self.get_a_spot(force_refresh=True)
        if spot.empty:
            raise RuntimeError("Mairui 股票池为空，无法同步日快照")

        sync_limit = int(os.getenv("MAIRUI_SYNC_LIMIT", "0"))
        if sync_limit > 0:
            spot = spot.head(sync_limit).reset_index(drop=True)

        today = datetime.now().strftime("%Y%m%d")
        snapshot_rows: list[dict] = []
        ok, failed = 0, 0

        for code in spot["code"].astype(str).tolist():
            try:
                item = self._get_json(f"hsrl/ssjy/{code}/{self.token}")
                if not isinstance(item, dict):
                    failed += 1
                    continue
                row = {
                    "code": self._norm_code(code),
                    "close": pd.to_numeric(item.get("p"), errors="coerce"),
                    "volume": pd.to_numeric(item.get("v"), errors="coerce"),
                    "low": pd.to_numeric(item.get("l"), errors="coerce"),
                    "mktcap": pd.to_numeric(item.get("sz"), errors="coerce"),
                    "updated_at": str(item.get("t", "")),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }
                if pd.isna(row["close"]) or pd.isna(row["volume"]) or pd.isna(row["low"]):
                    failed += 1
                    continue
                snapshot_rows.append(row)
                self._append_history_row(code, row)
                ok += 1
            except Exception:
                failed += 1

        if snapshot_rows:
            snap_df = pd.DataFrame(snapshot_rows)
            self.cache.set_df(f"mairui:daily_snapshot:{today}", snap_df)

            # 刷新 a_spot 缓存并补齐 mktcap
            a_spot = self.cache.get_df("mairui:a_spot")
            if a_spot is not None and not a_spot.empty:
                a_spot = a_spot.drop(columns=["mktcap"], errors="ignore").merge(
                    snap_df[["code", "mktcap"]], on="code", how="left"
                )
                self.cache.set_df("mairui:a_spot", a_spot)

        self.cache.set_df(
            "mairui:sync_meta",
            pd.DataFrame([{"sync_date": today, "ok": ok, "failed": failed, "total": len(spot)}]),
        )
        return {"total": int(len(spot)), "ok": int(ok), "failed": int(failed)}

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        c = self._norm_code(code)
        key = self._stock_cache_key(c)
        cached = self.cache.get_df(key)
        if cached is not None and not cached.empty and {"date", "close", "volume", "low"}.issubset(cached.columns):
            return cached.sort_values("date").reset_index(drop=True)

        legacy = self.cache.get_df(f"mairui:stock_daily:{c}")
        if legacy is not None and not legacy.empty and {"date", "close", "volume", "low"}.issubset(legacy.columns):
            self.cache.set_df(key, legacy.drop(columns=["mktcap"], errors="ignore"), tail_rows=60)
            return legacy.sort_values("date").reset_index(drop=True)

        for backup in [self.tushare_backup, self.akshare_backup]:
            if backup is None:
                continue
            try:
                out = backup.get_stock_daily(c)
                if out is not None and not out.empty:
                    if "low" not in out.columns:
                        out["low"] = out["close"]
                    self.cache.set_df(key, out.drop(columns=["mktcap"], errors="ignore"), tail_rows=60)
                    return out
            except Exception:
                continue
        raise RuntimeError(f"Mairui 与备用源都无法获取日线: {c}")

    def get_stock_daily_bulk(self, codes: list[str], min_days: int = 60) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        missing: list[str] = []
        for c in codes:
            code = self._norm_code(c)
            key = self._stock_cache_key(code)
            cached = self.cache.get_df(key)
            if cached is None or cached.empty:
                legacy = self.cache.get_df(f"mairui:stock_daily:{code}")
                if legacy is not None and not legacy.empty:
                    cached = legacy
                    self.cache.set_df(key, cached.drop(columns=["mktcap"], errors="ignore"), tail_rows=60)
            if (
                cached is not None
                and len(cached) >= min_days
                and {"date", "close", "volume", "low"}.issubset(cached.columns)
            ):
                result[code] = cached.sort_values("date").reset_index(drop=True)
            else:
                missing.append(code)

        if not missing:
            return result

        if self.tushare_backup is not None and hasattr(self.tushare_backup, "get_stock_daily_bulk"):
            try:
                bulk = self.tushare_backup.get_stock_daily_bulk(missing, min_days=min_days)
                for code, df in bulk.items():
                    if df is None or df.empty:
                        continue
                    if "low" not in df.columns:
                        df["low"] = df["close"]
                    result[code] = df
                    self.cache.set_df(self._stock_cache_key(code), df.drop(columns=["mktcap"], errors="ignore"), tail_rows=60)
                missing = [c for c in missing if c not in result]
            except Exception:
                pass

        for code in missing:
            try:
                result[code] = self.get_stock_daily(code)
            except Exception:
                continue
        return result

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        for backup in [self.akshare_backup, self.tushare_backup]:
            if backup is None:
                continue
            try:
                return backup.get_etf_daily(code)
            except Exception:
                continue
        raise RuntimeError("Mairui 无 ETF 接口，且备用源不可用")
