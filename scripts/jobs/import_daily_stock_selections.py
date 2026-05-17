from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient, UpdateOne


@dataclass
class ImportDailyStockSelectionResult:
    run_date: str
    source_id: str
    source_count: int
    parsed_rows: int
    mongo_upserts: int


def _load_env_file(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _normalize_code(value: Any) -> str:
    digits = re.findall(r"\d", str(value or ""))
    return "".join(digits)[:6] if len(digits) >= 6 else ""


def _normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace("%", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_run_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"日期格式必须是 YYYY-MM-DD 或 YYYYMMDD: {value}")


def build_analysis_rows(selection: dict[str, Any], saved_at: datetime | None = None) -> list[dict[str, Any]]:
    run_date = _normalize_run_date(str(selection.get("date") or ""))
    if not run_date:
        raise ValueError("daily_stock_selections 文档缺少 date")

    stocks = selection.get("stocks", [])
    if not isinstance(stocks, list):
        raise ValueError("daily_stock_selections.stocks 必须是数组")

    saved_at = saved_at or datetime.utcnow()
    source_id = str(selection.get("_id"))
    source_file = f"daily_stock_selections:{source_id}"
    rows: list[dict[str, Any]] = []

    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        code = _normalize_code(stock.get("code"))
        entry_price = _to_float(stock.get("price"))
        if not code or entry_price is None:
            continue
        pct_chg = _to_float(stock.get("pct_chg"))
        rows.append(
            {
                "_id": f"{code}.{run_date}",
                "run_date": run_date,
                "code": code,
                "name": _normalize_name(stock.get("name")),
                "entry_price": round(entry_price, 2),
                "pct_chg": round(float(pct_chg or 0.0), 2),
                "source_file": source_file,
                "source_collection": "daily_stock_selections",
                "source_id": source_id,
                "source_created_at": selection.get("created_at"),
                "saved_at": saved_at,
            }
        )
    return rows


def import_daily_stock_selections(
    logger: logging.Logger,
    run_date: str | None = None,
) -> ImportDailyStockSelectionResult:
    _load_env_file(Path(".env"))

    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
    source_coll_name = os.getenv("MONGO_DAILY_STOCK_SELECTIONS_COLLECTION", "daily_stock_selections").strip()
    target_coll_name = os.getenv("MONGO_ANALYSIS_STOCK_COLLECTION", "analysis_stock").strip() or "analysis_stock"

    db = MongoClient(uri)[db_name]
    source_coll = db[source_coll_name or "daily_stock_selections"]
    target_coll = db[target_coll_name]

    normalized_run_date = _normalize_run_date(run_date)
    query = {"date": normalized_run_date} if normalized_run_date else {}
    selection = source_coll.find_one(query, sort=[("created_at", -1), ("_id", -1)])
    if not selection:
        detail = f"date={normalized_run_date}" if normalized_run_date else "latest"
        raise RuntimeError(f"未找到 daily_stock_selections 文档: {detail}")

    rows = build_analysis_rows(selection)
    if not rows:
        return ImportDailyStockSelectionResult(
            run_date=str(selection.get("date")),
            source_id=str(selection.get("_id")),
            source_count=int(selection.get("count") or 0),
            parsed_rows=0,
            mongo_upserts=0,
        )

    target_coll.create_index([("code", 1), ("run_date", 1)], unique=True)
    target_coll.create_index("run_date")
    target_coll.create_index("saved_at")

    ops = [UpdateOne({"_id": row["_id"]}, {"$set": row}, upsert=True) for row in rows]
    target_coll.bulk_write(ops, ordered=False)

    logger.info(
        "daily_stock_selections 已导入 analysis_stock: date=%s, source_id=%s, source_count=%s, rows=%s",
        selection.get("date"),
        selection.get("_id"),
        selection.get("count"),
        len(rows),
    )
    return ImportDailyStockSelectionResult(
        run_date=str(selection.get("date")),
        source_id=str(selection.get("_id")),
        source_count=int(selection.get("count") or len(rows)),
        parsed_rows=len(rows),
        mongo_upserts=len(ops),
    )
