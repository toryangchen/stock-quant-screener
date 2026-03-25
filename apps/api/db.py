from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from config import get_settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    settings = get_settings()
    client = MongoClient(
        settings.uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
        maxPoolSize=settings.mongo_max_pool_size,
        minPoolSize=settings.mongo_min_pool_size,
        appname="quant-screener-api",
    )
    client.admin.command("ping")
    return client


def get_db() -> Database:
    settings = get_settings()
    return get_client()[settings.db_name]
