from __future__ import annotations

import logging
import os
from datetime import datetime

import pandas as pd
from pymongo import UpdateOne


class MongoEtfHistory:
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        self.enabled = os.getenv("MONGO_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self._coll = None
        if not self.enabled:
            return

        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
        db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            self._coll = client[db_name]["etf_history"]
            self._coll.create_index([("code", 1), ("run_date", 1)], unique=True)
            self._coll.create_index("saved_at")
        except Exception as exc:
            self.enabled = False
            self._coll = None
            self.logger.warning("Mongo ETF 历史初始化失败，已禁用: %s", exc)

    def _is_ready(self) -> bool:
        return self.enabled and self._coll is not None

    @staticmethod
    def _normalize_value(v):
        if pd.isna(v):
            return None
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                return v
        return v

    @staticmethod
    def _build_doc_id(code: str, run_date: str) -> str:
        return f"{str(code).strip()}.{str(run_date).strip()}"

    def save_daily(self, run_date: str, rank_df: pd.DataFrame, decision: str) -> int:
        if not self._is_ready() or rank_df is None or rank_df.empty:
            return 0

        now = datetime.utcnow()
        ops: list[UpdateOne] = []
        for row in rank_df.to_dict(orient="records"):
            code = str(row.get("code", "")).strip()
            if not code:
                continue
            payload = {k: self._normalize_value(v) for k, v in row.items()}
            payload.update(
                {
                    "_id": self._build_doc_id(code=code, run_date=run_date),
                    "run_date": run_date,
                    "code": code,
                    "decision": decision,
                    "saved_at": now,
                }
            )
            ops.append(UpdateOne({"_id": payload["_id"]}, {"$set": payload}, upsert=True))

        if not ops:
            return 0

        self._coll.bulk_write(ops, ordered=False)
        return len(ops)
