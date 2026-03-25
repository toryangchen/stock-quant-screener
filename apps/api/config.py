from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def load_env_files() -> None:
    current = Path(__file__).resolve()
    for candidate in (current.parents[2] / ".env", current.parent / ".env"):
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    db_name: str
    screening_collection: str
    market_collection: str
    etf_history_collection: str
    analysis_stock_collection: str
    cors_origins: tuple[str, ...]
    response_cache_ttl_seconds: int
    dates_cache_ttl_seconds: int
    mongo_max_pool_size: int
    mongo_min_pool_size: int


def parse_csv_env(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_settings() -> MongoSettings:
    load_env_files()
    return MongoSettings(
        uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip(),
        db_name=os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener",
        screening_collection=os.getenv("MONGO_HISTORY_COLLECTION", "screening_history").strip() or "screening_history",
        market_collection=os.getenv("MONGO_COLLECTION", "market_cache").strip() or "market_cache",
        etf_history_collection=os.getenv("MONGO_ETF_HISTORY_COLLECTION", "etf_history").strip() or "etf_history",
        analysis_stock_collection=os.getenv("MONGO_ANALYSIS_STOCK_COLLECTION", "analysis_stock").strip()
        or "analysis_stock",
        cors_origins=parse_csv_env("API_CORS_ORIGINS", "*"),
        response_cache_ttl_seconds=max(parse_int_env("API_RESPONSE_CACHE_TTL_SECONDS", 60), 0),
        dates_cache_ttl_seconds=max(parse_int_env("API_DATES_CACHE_TTL_SECONDS", 300), 0),
        mongo_max_pool_size=max(parse_int_env("MONGO_MAX_POOL_SIZE", 20), 1),
        mongo_min_pool_size=max(parse_int_env("MONGO_MIN_POOL_SIZE", 1), 0),
    )
