from __future__ import annotations

import logging
import os
import re

import pandas as pd
from pymongo import MongoClient

from scripts.data_source.base import DataSource


def _norm_code(code: str) -> str:
    s = str(code).strip().upper()
    m = re.search(r"(\d{6})", s)
    return m.group(1) if m else s


class MongoOnlyDataSource(DataSource):
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
        db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
        coll_name = os.getenv("MONGO_COLLECTION", "market_cache").strip() or "market_cache"
        self._coll = MongoClient(uri)[db_name][coll_name]

    def get_a_spot(self) -> pd.DataFrame:
        cur = self._coll.find(
            {"_id": {"$regex": r"^\d{6}$"}},
            {"_id": 1, "name": 1, "mktcap": 1, "data": {"$slice": -1}},
        )
        rows: list[dict] = []
        for doc in cur:
            code = _norm_code(doc.get("_id", ""))
            data = doc.get("data") or []
            latest = data[-1] if data else {}
            rows.append(
                {
                    "code": code,
                    "name": str(doc.get("name") or code),
                    "close": pd.to_numeric(latest.get("close"), errors="coerce"),
                    "mktcap": pd.to_numeric(doc.get("mktcap"), errors="coerce"),
                }
            )
        out = pd.DataFrame(rows)
        if out.empty:
            return pd.DataFrame(columns=["code", "name", "close", "mktcap"])
        out = out.dropna(subset=["code"]).sort_values("code").reset_index(drop=True)
        return out

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        code6 = _norm_code(code)
        doc = self._coll.find_one({"_id": code6}, {"_id": 1, "data": 1})
        if not doc:
            return pd.DataFrame(columns=["date", "close", "volume", "low", "pre_close", "open", "turnover"])
        data = doc.get("data") or []
        out = pd.DataFrame(data)
        if out.empty:
            return pd.DataFrame(columns=["date", "close", "volume", "low", "pre_close", "open", "turnover"])
        for col in ["close", "volume", "low", "pre_close", "open", "turnover"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out = out.sort_values("date").reset_index(drop=True)
        return out

    def get_stock_daily_bulk(self, codes: list[str], min_days: int = 60) -> dict[str, pd.DataFrame]:
        code_set = sorted({_norm_code(c) for c in codes if str(c).strip()})
        if not code_set:
            return {}
        out: dict[str, pd.DataFrame] = {}
        cur = self._coll.find({"_id": {"$in": code_set}}, {"_id": 1, "data": {"$slice": -max(min_days, 60)}})
        for doc in cur:
            code = _norm_code(doc.get("_id", ""))
            data = doc.get("data") or []
            df = pd.DataFrame(data)
            if df.empty:
                continue
            for col in ["close", "volume", "low", "pre_close", "open", "turnover"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.sort_values("date").reset_index(drop=True)
            if len(df) >= min_days:
                out[code] = df
        return out

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        # breakout 场景默认不依赖 ETF 数据；这里返回空，避免任何外部请求。
        return pd.DataFrame(columns=["date", "close", "volume"])
