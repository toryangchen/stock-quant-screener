from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import pandas as pd


class MongoDataCache:
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        self.enabled = os.getenv("MONGO_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.ttl_seconds = int(os.getenv("MONGO_CACHE_TTL_SECONDS", "43200"))
        self._coll = None

        if not self.enabled:
            return

        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
        db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
        coll_name = os.getenv("MONGO_COLLECTION", "market_cache").strip() or "market_cache"

        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            db = client[db_name]
            self._coll = db[coll_name]
            self._coll.create_index("expires_at")
        except Exception as exc:
            self.enabled = False
            self._coll = None
            self.logger.warning("Mongo 缓存初始化失败，已禁用缓存: %s", exc)

    def _is_ready(self) -> bool:
        return self.enabled and self._coll is not None

    def get_df(self, key: str) -> pd.DataFrame | None:
        if not self._is_ready():
            return None

        now = datetime.utcnow()
        doc = self._coll.find_one({"_id": key})
        if not doc:
            return None

        expires_at = doc.get("expires_at")
        if expires_at and expires_at < now:
            return None

        data = doc.get("data")
        if not data:
            return None

        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df

    def set_df(self, key: str, df: pd.DataFrame) -> None:
        if not self._is_ready() or df.empty:
            return

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        out = df.copy()
        for col in out.columns:
            if str(out[col].dtype).startswith("datetime"):
                out[col] = out[col].dt.strftime("%Y-%m-%d")

        payload = {
            "_id": key,
            "cached_at": now,
            "expires_at": expires_at,
            "data": out.to_dict(orient="records"),
        }
        self._coll.replace_one({"_id": key}, payload, upsert=True)
