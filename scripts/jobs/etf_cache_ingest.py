from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from pymongo import MongoClient, UpdateOne

from scripts.config import AppConfig


@dataclass
class EtfIngestResult:
    total_etfs: int
    ok_etfs: int
    mongo_upserts: int


def _normalize_etf_frame(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["close", "volume", "low", "open", "pre_close", "turnover"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    keep = [c for c in ["date", "close", "volume", "low", "open", "pre_close", "turnover"] if c in out.columns]
    out = out[keep].dropna(subset=["date", "close"]).reset_index(drop=True)

    rows: list[dict] = []
    for row in out.to_dict(orient="records"):
        item = {"date": str(row["date"])}
        for col in keep:
            if col == "date":
                continue
            value = row.get(col)
            item[col] = None if pd.isna(value) else float(value)
        rows.append(item)
    return rows


def run_etf_cache_ingest(ds, cfg: AppConfig, logger: logging.Logger) -> EtfIngestResult:
    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
    coll = MongoClient(uri)[db_name]["etf_cache"]

    ops: list[UpdateOne] = []
    ok = 0
    now = datetime.utcnow()

    for item in cfg.etf_pool:
        code = str(item["code"]).strip()
        name = str(item["name"]).strip()
        try:
            df = ds.get_etf_daily(code)
            rows = _normalize_etf_frame(df)
            if not rows:
                logger.warning("ETF %s(%s) 无有效历史数据，跳过", name, code)
                continue
            payload = {
                "_id": code,
                "code": code,
                "name": name,
                "updated_at": now,
                "data": rows[-250:],
            }
            ops.append(UpdateOne({"_id": code}, {"$set": payload}, upsert=True))
            ok += 1
        except Exception as exc:
            logger.warning("ETF %s(%s) 采集失败，跳过: %s", name, code, exc)

    if ops:
        coll.bulk_write(ops, ordered=False)

    logger.info("ETF 缓存写入完成: total=%s, ok=%s, upserts=%s", len(cfg.etf_pool), ok, len(ops))
    return EtfIngestResult(total_etfs=len(cfg.etf_pool), ok_etfs=ok, mongo_upserts=len(ops))
