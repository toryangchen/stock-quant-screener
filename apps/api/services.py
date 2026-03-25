from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from cache import TTLCache
from config import get_settings
from db import get_client
from repositories import MongoReadRepository
from utils import build_points, to_float


class QuantReadService:
    def __init__(self, repo: MongoReadRepository | None = None) -> None:
        self.repo = repo or MongoReadRepository()
        self.settings = get_settings()
        self.cache = TTLCache()

    def health(self) -> dict[str, Any]:
        try:
            get_client().admin.command("ping")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"mongodb unavailable: {exc}") from exc
        return {"ok": True, "db": get_settings().db_name}

    def get_screening_dates(self) -> dict[str, list[str]]:
        cache_key = "dates:screening"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        result = {"dates": self.repo.get_screening_dates()}
        return self.cache.set(cache_key, result, self.settings.dates_cache_ttl_seconds)

    def get_etf_dates(self) -> dict[str, list[str]]:
        cache_key = "dates:etf"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        result = {"dates": self.repo.get_etf_dates()}
        return self.cache.set(cache_key, result, self.settings.dates_cache_ttl_seconds)

    def get_analysis_dates(self) -> dict[str, list[str]]:
        cache_key = "dates:analysis"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        result = {"dates": self.repo.get_analysis_dates()}
        return self.cache.set(cache_key, result, self.settings.dates_cache_ttl_seconds)

    def get_screening_by_date(self, run_date: str) -> dict[str, Any]:
        cache_key = f"screening:{run_date}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        docs = self.repo.get_screening_docs(run_date)
        if not docs:
            raise HTTPException(status_code=404, detail=f"date not found: {run_date}")

        codes = [str(doc.get("code", "")).strip() for doc in docs if str(doc.get("code", "")).strip()]
        market_map = self.repo.get_market_docs_by_codes(codes)

        primary_stocks: list[dict[str, Any]] = []
        secondary_stocks: list[dict[str, Any]] = []
        trends: list[dict[str, Any]] = []
        latest_dates: list[str] = []

        for doc in docs:
            code = str(doc.get("code", "")).strip()
            if not code:
                continue
            market_doc = market_map.get(code, {})
            points = build_points(list(market_doc.get("data") or []), run_date)
            if points:
                latest_dates.append(points[-1]["date"])

            pick = self._build_stock_pick(
                {
                    **doc,
                    "close": points[-1]["close"] if points else doc.get("close"),
                },
                market_doc,
            )
            primary_stocks.append(pick)
            trends.append({"code": code, "name": pick["name"], "points": points})
            if pick["is_secondary"]:
                secondary_stocks.append(pick)

        today = max(latest_dates) if latest_dates else run_date
        result = {
            "date": run_date,
            "today": today,
            "stocks": secondary_stocks,
            "primary_stocks": primary_stocks,
            "secondary_stocks": secondary_stocks,
            "trends": trends,
        }
        return self.cache.set(cache_key, result, self.settings.response_cache_ttl_seconds)

    def get_etf_by_date(self, run_date: str) -> dict[str, Any]:
        cache_key = f"etf:{run_date}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        docs = self.repo.get_etf_docs(run_date)
        if not docs:
            raise HTTPException(status_code=404, detail=f"etf date not found: {run_date}")

        etfs: list[dict[str, Any]] = []
        decision = ""
        for doc in docs:
            decision = decision or str(doc.get("decision") or "")
            ret_pct = to_float(doc.get("retN_pct"))
            if ret_pct is None:
                ret_pct = (to_float(doc.get("retN")) or 0.0) * 100
            etfs.append(
                {
                    "code": str(doc.get("code", "")).strip(),
                    "name": str(doc.get("name", "")).strip(),
                    "rank": int(to_float(doc.get("rank")) or 0),
                    "ret_pct": round(ret_pct, 2),
                    "above_ma": bool(doc.get("above_ma")),
                    "ma_price": round(to_float(doc.get("maN")) or 0.0, 4),
                    "close": round(to_float(doc.get("close")) or 0.0, 4),
                    "decision": str(doc.get("decision") or ""),
                }
            )

        result = {"date": run_date, "decision": decision, "etfs": etfs}
        return self.cache.set(cache_key, result, self.settings.response_cache_ttl_seconds)

    def get_analysis_by_date(self, run_date: str) -> dict[str, Any]:
        cache_key = f"analysis:{run_date}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        docs = self.repo.get_analysis_docs(run_date)
        if not docs:
            raise HTTPException(status_code=404, detail=f"analysis date not found: {run_date}")

        codes = [str(doc.get("code", "")).strip() for doc in docs if str(doc.get("code", "")).strip()]
        market_map = self.repo.get_market_docs_by_codes(codes)

        stocks: list[dict[str, Any]] = []
        trends: list[dict[str, Any]] = []
        latest_dates: list[str] = []

        for doc in docs:
            code = str(doc.get("code", "")).strip()
            if not code:
                continue

            market_doc = market_map.get(code, {})
            points = build_points(list(market_doc.get("data") or []), run_date)
            if points:
                latest_dates.append(points[-1]["date"])

            entry_price = to_float(doc.get("entry_price")) or 0.0
            latest_price = to_float(points[-1]["close"] if points else None)
            if latest_price is None:
                latest_price = entry_price

            return_pct = 0.0
            if entry_price:
                return_pct = round((latest_price - entry_price) / entry_price * 100, 2)

            name = str(doc.get("name") or market_doc.get("name") or code)
            stocks.append(
                {
                    "code": code,
                    "name": name,
                    "entry_price": round(entry_price, 2),
                    "latest_price": round(latest_price, 2),
                    "return_pct": return_pct,
                    "pct_chg": round(to_float(doc.get("pct_chg")) or 0.0, 2),
                    "source_file": str(doc.get("source_file") or ""),
                }
            )
            trends.append({"code": code, "name": name, "points": points})

        today = max(latest_dates) if latest_dates else run_date
        result = {"date": run_date, "today": today, "stocks": stocks, "trends": trends}
        return self.cache.set(cache_key, result, self.settings.response_cache_ttl_seconds)

    def _build_stock_pick(self, doc: dict[str, Any], market_doc: dict[str, Any]) -> dict[str, Any]:
        entry_price = to_float(doc.get("entry_price"))
        if entry_price is None:
            entry_price = to_float(doc.get("close"))
        latest_price = to_float(doc.get("close"))
        if latest_price is None:
            latest_price = entry_price
        if latest_price is None:
            latest_price = 0.0
        if entry_price is None:
            entry_price = latest_price

        return_pct = 0.0
        if entry_price:
            return_pct = round((latest_price - entry_price) / entry_price * 100, 2)

        name = str(doc.get("name") or market_doc.get("name") or doc.get("code") or "")
        return {
            "code": str(doc.get("code", "")).strip(),
            "name": name,
            "is_secondary": bool(doc.get("is_secondary")),
            "entry_price": round(entry_price, 2),
            "latest_price": round(latest_price, 2),
            "return_pct": return_pct,
            "pct_chg": round((to_float(doc.get("pct_chg")) or 0.0) * 100, 2),
            "ret_20_stock": round((to_float(doc.get("ret_20_stock")) or 0.0) * 100, 2),
            "vol_ratio": round(to_float(doc.get("vol_ratio")) or 0.0, 2),
            "vol_score": round(to_float(doc.get("vol_score")) or 0.0, 4),
            "risk_pct": round((to_float(doc.get("risk_pct")) or 0.0) * 100, 2),
            "stop_price": round(to_float(doc.get("stop_price")) or 0.0, 2),
            "ma10_price": round(to_float(doc.get("ma10_price")) or 0.0, 3),
            "ma20_price": round(to_float(doc.get("ma20_price")) or 0.0, 3),
            "score": round(to_float(doc.get("score")) or 0.0, 4),
            "suggested_shares": int(to_float(doc.get("suggested_shares")) or 0),
            "suggested_position_value": round(to_float(doc.get("suggested_position_value")) or 0.0, 2),
            "mkt_cap": round((to_float(doc.get("mkt_cap")) or 0.0) / 100000000, 2),
        }
