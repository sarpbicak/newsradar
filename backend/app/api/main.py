"""FastAPI uygulaması — tüm uçları bağlar, açılışta DB + zamanlayıcıyı başlatır.

Çalıştır:  uvicorn app.api.main:app --reload  (backend/ içinden)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import scheduler
from ..config import get_settings
from ..db.database import init_db
from . import (
    routes_auth,
    routes_chat,
    routes_dashboard,
    routes_entities,
    routes_refresh,
    routes_suggestions,
    routes_symbols,
)
from .routes_auth import require_auth

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Ön-filtre kuralı değiştiyse eski sürümle elenmiş makaleleri yeniden aç
    # (Render'da elle SQL çalıştırılamadığı için açılışta otomatik; idempotent).
    from ..analysis.pipeline import reconcile_prefilter

    reopened = reconcile_prefilter()
    if reopened:
        logging.getLogger("newsradar").info(
            "Ön-filtre reconcile: %d makale yeniden değerlendirmeye açıldı.", reopened
        )
    # Deploy: kalıcı olmayan diskte DB boş başlamasın diye opsiyonel oto-seed.
    if get_settings().seed_on_start:
        from ..seed import seed

        seed()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="NewsRadar API", version="1.0", lifespan=lifespan)

# CORS: yerel Vite + FRONTEND_URL (deploy'da Render frontend domain'i).
# İzinli origin'ler ortam değişkeninden okunur (bkz. config.cors_origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
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
app.include_router(routes_suggestions.router, dependencies=_protected)
app.include_router(routes_symbols.router, dependencies=_protected)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Basit sağlık kontrolü — kasıtlı olarak korumasız."""
    return {"status": "ok"}
