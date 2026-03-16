from __future__ import annotations

from typing import Any

from db import get_db
from config import get_settings


class MongoReadRepository:
    def __init__(self) -> None:
        self.settings = get_settings()
        db = get_db()
        self.screening_coll = db[self.settings.screening_collection]
        self.market_coll = db[self.settings.market_collection]
        self.etf_history_coll = db[self.settings.etf_history_collection]
        self.analysis_stock_coll = db[self.settings.analysis_stock_collection]

    def get_screening_dates(self) -> list[str]:
        # Show any trading date that produced screening docs, even if secondary picks are empty.
        dates = self.screening_coll.distinct("run_date")
        return sorted(str(item) for item in dates if item)

    def get_etf_dates(self) -> list[str]:
        dates = self.etf_history_coll.distinct("run_date")
        return sorted(str(item) for item in dates if item)

    def get_analysis_dates(self) -> list[str]:
        dates = self.analysis_stock_coll.distinct("run_date")
        return sorted(str(item) for item in dates if item)

    def get_screening_docs(self, run_date: str) -> list[dict[str, Any]]:
        return list(
            self.screening_coll.find(
                {"run_date": run_date},
                {
                    "_id": 0,
                    "code": 1,
                    "name": 1,
                    "entry_price": 1,
                    "close": 1,
                    "is_secondary": 1,
                    "pct_chg": 1,
                    "ret_20_stock": 1,
                    "vol_ratio": 1,
                    "vol_score": 1,
                    "risk_pct": 1,
                    "stop_price": 1,
                    "ma10_price": 1,
                    "ma20_price": 1,
                    "score": 1,
                    "suggested_shares": 1,
                    "suggested_position_value": 1,
                    "mkt_cap": 1,
                },
            ).sort([("is_secondary", -1), ("score", 1), ("vol_score", 1), ("code", 1)])
        )

    def get_market_docs_by_codes(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        docs = self.market_coll.find({"_id": {"$in": codes}}, {"_id": 1, "name": 1, "data": 1})
        return {str(doc.get("_id", "")).strip(): doc for doc in docs}

    def get_etf_docs(self, run_date: str) -> list[dict[str, Any]]:
        return list(
            self.etf_history_coll.find(
                {"run_date": run_date},
                {
                    "_id": 0,
                    "code": 1,
                    "name": 1,
                    "rank": 1,
                    "retN_pct": 1,
                    "retN": 1,
                    "above_ma": 1,
                    "maN": 1,
                    "close": 1,
                    "decision": 1,
                },
            ).sort([("rank", 1), ("code", 1)])
        )

    def get_analysis_docs(self, run_date: str) -> list[dict[str, Any]]:
        return list(
            self.analysis_stock_coll.find(
                {"run_date": run_date},
                {
                    "_id": 0,
                    "code": 1,
                    "name": 1,
                    "entry_price": 1,
                    "pct_chg": 1,
                    "source_file": 1,
                },
            ).sort([("pct_chg", -1), ("code", 1)])
        )
