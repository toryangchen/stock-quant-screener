from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient, UpdateOne


@dataclass
class ImportResult:
    files: int
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


def _normalize_code(value: str) -> str:
    digits = re.findall(r"\d", str(value))
    return "".join(digits)[:6].zfill(6) if digits else str(value).strip()


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _to_float(value: str) -> float | None:
    raw = str(value or "").strip().replace("%", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _infer_run_date(file_path: Path, today: datetime | None = None) -> str:
    today = today or datetime.now()
    stem = file_path.stem.strip()
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", stem)
    if not match:
        raise ValueError(f"无法从文件名解析日期: {file_path.name}")

    month = int(match.group(1))
    day = int(match.group(2))
    year = today.year
    candidate = datetime(year, month, day)
    if candidate.date() > today.date():
        candidate = datetime(year - 1, month, day)
    return candidate.strftime("%Y-%m-%d")


def _parse_file(file_path: Path) -> list[dict]:
    rows: list[dict] = []
    run_date = _infer_run_date(file_path)

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if "│" not in line or "代码" in line or "名称" in line:
            continue
        parts = [part.strip() for part in line.split("│")[1:-1]]
        if len(parts) < 4:
            continue
        code, name, entry_price_raw, pct_chg_raw = parts[:4]
        if not code or not re.search(r"\d", code):
            continue

        entry_price = _to_float(entry_price_raw)
        pct_chg = _to_float(pct_chg_raw)
        if entry_price is None:
            continue

        norm_code = _normalize_code(code)
        rows.append(
            {
                "_id": f"{norm_code}.{run_date}",
                "run_date": run_date,
                "code": norm_code,
                "name": _normalize_name(name),
                "entry_price": float(entry_price),
                "pct_chg": float(pct_chg or 0.0),
                "source_file": file_path.name,
            }
        )
    return rows


def import_analysis_stock(source_dir: str | Path, logger: logging.Logger) -> ImportResult:
    _load_env_file(Path(".env"))

    src = Path(source_dir)
    if not src.exists():
        raise FileNotFoundError(f"目录不存在: {src}")

    files = sorted(path for path in src.glob("*.txt") if path.is_file())
    if not files:
        raise FileNotFoundError(f"目录下没有 txt 文件: {src}")

    all_rows: list[dict] = []
    for file_path in files:
        parsed = _parse_file(file_path)
        logger.info("解析分析股票文件: %s, rows=%s, run_date=%s", file_path.name, len(parsed), parsed[0]["run_date"] if parsed else "-")
        all_rows.extend(parsed)

    if not all_rows:
        return ImportResult(files=len(files), parsed_rows=0, mongo_upserts=0)

    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
    coll_name = os.getenv("MONGO_ANALYSIS_STOCK_COLLECTION", "analysis_stock").strip() or "analysis_stock"

    coll = MongoClient(uri)[db_name][coll_name]
    coll.create_index([("code", 1), ("run_date", 1)], unique=True)
    coll.create_index("run_date")
    coll.create_index("saved_at")

    now = datetime.utcnow()
    ops: list[UpdateOne] = []
    for row in all_rows:
        payload = {**row, "saved_at": now}
        ops.append(UpdateOne({"_id": payload["_id"]}, {"$set": payload}, upsert=True))

    if ops:
        coll.bulk_write(ops, ordered=False)

    return ImportResult(files=len(files), parsed_rows=len(all_rows), mongo_upserts=len(ops))
