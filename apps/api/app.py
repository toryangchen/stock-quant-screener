from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routes import router


def create_app() -> FastAPI:
    settings = get_settings()
    cors_origins = list(settings.cors_origins or ("*",))
    allow_all_origins = cors_origins == ["*"]

    app = FastAPI(title="Quant Screener API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=not allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app
