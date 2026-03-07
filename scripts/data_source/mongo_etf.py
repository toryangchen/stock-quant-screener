from __future__ import annotations

import logging
import os

import pandas as pd
from pymongo import MongoClient

from scripts.data_source.base import DataSource


class MongoEtfDataSource(DataSource):
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
        db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
        self._coll = MongoClient(uri)[db_name]["etf_cache"]

    def get_a_spot(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["code", "name", "mktcap"])

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["date", "close", "volume", "low", "pre_close", "open", "turnover"])

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        doc = self._coll.find_one({"_id": str(code).strip()}, {"data": 1})
        if not doc:
            return pd.DataFrame(columns=["date", "close", "volume", "low", "open", "pre_close", "turnover"])

        out = pd.DataFrame(doc.get("data") or [])
        if out.empty:
            return pd.DataFrame(columns=["date", "close", "volume", "low", "open", "pre_close", "turnover"])

        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out = out.sort_values("date").reset_index(drop=True)
        for col in ["close", "volume", "low", "open", "pre_close", "turnover"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        return out
