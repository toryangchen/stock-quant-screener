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


@lru_cache(maxsize=1)
def get_settings() -> MongoSettings:
    load_env_files()
    return MongoSettings(
        uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip(),
        db_name=os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener",
        screening_collection=os.getenv("MONGO_HISTORY_COLLECTION", "screening_history").strip() or "screening_history",
        market_collection=os.getenv("MONGO_COLLECTION", "market_cache").strip() or "market_cache",
        etf_history_collection=os.getenv("MONGO_ETF_HISTORY_COLLECTION", "etf_history").strip() or "etf_history",
    )
