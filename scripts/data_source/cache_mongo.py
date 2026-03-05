from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import pandas as pd


class MongoDataCache:
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        self.enabled = os.getenv("MONGO_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
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
        except Exception as exc:
            self.enabled = False
            self._coll = None
            self.logger.warning("Mongo 缓存初始化失败，已禁用缓存: %s", exc)

    def _is_ready(self) -> bool:
        return self.enabled and self._coll is not None

    @staticmethod
    def _is_stock_key(key: str) -> bool:
        return bool(re.fullmatch(r"\d{6}", str(key).strip()))

    def get_df(self, key: str) -> pd.DataFrame | None:
        if not self._is_ready():
            return None
        if not self._is_stock_key(key):
            return None

        doc = self._coll.find_one({"_id": key})
        if not doc:
            return None

        data = doc.get("data")
        if not data:
            return None

        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df

    def set_df(
        self,
        key: str,
        df: pd.DataFrame,
        tail_rows: int | None = None,
        meta: dict | None = None,
    ) -> None:
        if not self._is_ready() or df.empty:
            return
        if not self._is_stock_key(key):
            # market_cache 仅允许股票代码 _id
            return

        now = datetime.utcnow()

        out = df.copy()
        if tail_rows is not None and tail_rows > 0:
            out = out.tail(tail_rows).reset_index(drop=True)
        for col in out.columns:
            if str(out[col].dtype).startswith("datetime"):
                out[col] = out[col].dt.strftime("%Y-%m-%d")

        payload = {
            "_id": key,
            "updated_at": now,
            "data": out.to_dict(orient="records"),
        }
        # 保留历史文档中的额外顶层字段（例如 mktcap）
        old = self._coll.find_one({"_id": key})
        if old:
            for k, v in old.items():
                if k not in {"_id", "updated_at", "data"}:
                    payload[k] = v
        if meta:
            for k, v in meta.items():
                payload[k] = v
        self._coll.replace_one({"_id": key}, payload, upsert=True)
