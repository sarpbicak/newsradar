"""FastAPI uygulaması — tüm uçları bağlar, açılışta DB + zamanlayıcıyı başlatır.

Çalıştır:  uvicorn app.api.main:app --reload  (backend/ içinden)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import scheduler
from ..db.database import init_db
from . import routes_auth, routes_chat, routes_dashboard, routes_entities, routes_refresh
from .routes_auth import require_auth

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="NewsRadar API", version="1.0", lifespan=lifespan)

# Kişisel araç: yerel Vite geliştirme sunucusuna izin ver.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Giriş ucu (/auth/login) korumasız — token buradan alınır.
app.include_router(routes_auth.router)

# Tüm veri uçları paylaşılan-şifre kapısının arkasında: geçerli token olmadan
# /entities, /entities/{id}/dashboard, /refresh, /status ve /chat'e erişilemez.
_protected = [Depends(require_auth)]
app.include_router(routes_entities.router, dependencies=_protected)
app.include_router(routes_dashboard.router, dependencies=_protected)
app.include_router(routes_refresh.router, dependencies=_protected)
app.include_router(routes_chat.router, dependencies=_protected)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Basit sağlık kontrolü — kasıtlı olarak korumasız."""
    return {"status": "ok"}
