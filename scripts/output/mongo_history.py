from __future__ import annotations

import logging
import os
from datetime import datetime

import pandas as pd
from pymongo import UpdateOne


class MongoScreeningHistory:
    def __init__(self) -> None:
        self.logger = logging.getLogger("quant_screener")
        self.enabled = os.getenv("MONGO_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self._coll = None
        if not self.enabled:
            return

        uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
        db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
        coll_name = os.getenv("MONGO_HISTORY_COLLECTION", "screening_history").strip() or "screening_history"

        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            db = client[db_name]
            self._coll = db[coll_name]
            self._coll.create_index([("run_date", 1), ("code", 1)], unique=True)
            self._coll.create_index("saved_at")
        except Exception as exc:
            self.enabled = False
            self._coll = None
            self.logger.warning("Mongo 筛选历史初始化失败，已禁用: %s", exc)

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

    def save_daily(self, run_date: str, primary_df: pd.DataFrame, secondary_df: pd.DataFrame) -> tuple[int, int]:
        if not self._is_ready():
            return 0, 0

        now = datetime.utcnow()
        # 保证同一天幂等覆盖，仅保留单条(run_date + code)
        self._coll.delete_many({"run_date": run_date})
        if primary_df is None or primary_df.empty:
            return 0, 0

        secondary_codes: set[str] = set()
        if secondary_df is not None and not secondary_df.empty and "code" in secondary_df.columns:
            secondary_codes = {
                str(c).strip() for c in secondary_df["code"].astype(str).tolist() if str(c).strip()
            }

        secondary_extra: dict[str, dict] = {}
        if secondary_df is not None and not secondary_df.empty:
            for row in secondary_df.to_dict(orient="records"):
                code = str(row.get("code", "")).strip()
                if not code:
                    continue
                secondary_extra[code] = {k: self._normalize_value(v) for k, v in row.items() if k != "code"}

        records: list[dict] = []
        for row in primary_df.to_dict(orient="records"):
            code = str(row.get("code", "")).strip()
            if not code:
                continue
            payload = {k: self._normalize_value(v) for k, v in row.items()}
            payload.update(
                {
                    "run_date": run_date,
                    "code": code,
                    "is_secondary": code in secondary_codes,
                    "saved_at": now,
                }
            )
            if code in secondary_extra:
                payload.update(secondary_extra[code])
            records.append(payload)

        if not records:
            return 0, 0

        self._coll.insert_many(records, ordered=False)
        return len(records), len(secondary_codes)

    def mark_secondary(self, run_date: str, secondary_df: pd.DataFrame) -> int:
        """兼容增量场景：将已存在的 run_date 记录标记为二筛命中。"""
        if not self._is_ready() or secondary_df is None or secondary_df.empty:
            return 0

        now = datetime.utcnow()
        ops = []
        for row in secondary_df.to_dict(orient="records"):
            code = str(row.get("code", "")).strip()
            if not code:
                continue
            updates = {k: self._normalize_value(v) for k, v in row.items() if k != "code"}
            updates["is_secondary"] = True
            updates["saved_at"] = now
            ops.append(
                UpdateOne(
                    {"run_date": run_date, "code": code},
                    {"$set": updates},
                    upsert=False,
                )
            )
        if not ops:
            return 0
        result = self._coll.bulk_write(ops, ordered=False)
        return int(result.modified_count)
