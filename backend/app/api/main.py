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
from ..db.models import PREFILTER_VERSION
from . import (
    routes_admin,
    routes_auth,
    routes_chat,
    routes_dashboard,
    routes_entities,
    routes_refresh,
    routes_suggestions,
    routes_symbols,
    routes_users,
)
from .routes_auth import get_current_user

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Ön-filtre kuralı değiştiyse eski sürümle elenmiş makaleleri yeniden aç
    # (Render'da elle SQL çalıştırılamadığı için açılışta otomatik; idempotent).
    from ..analysis.pipeline import reconcile_prefilter

    # KOŞULSUZ logla (0 olsa bile) — reconcile'ın açılışta gerçekten çalıştığı
    # loglardan tek bakışta doğrulansın; sessiz kalırsa "çalışmıyor mu?" şüphesi doğar.
    _log = logging.getLogger("newsradar")
    try:
        reopened = reconcile_prefilter()
        _log.info(
            "Ön-filtre reconcile (v%d): %d makale yeniden değerlendirmeye açıldı.",
            PREFILTER_VERSION, reopened,
        )
    except Exception:  # noqa: BLE001 — reconcile hatası açılışı çökertmesin
        _log.exception("Ön-filtre reconcile açılışta başarısız (atlandı).")
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

# Katman 1 — genel şifre ucu (/auth/login) korumasız; genel token buradan alınır.
app.include_router(routes_auth.router)

# Katman 2 — kişisel hesaplar. register/login GENEL şifre kapısının arkasında
# (kendi route bağımlılıklarında), /users/me kişisel token ister.
app.include_router(routes_users.router)

# Tüm veri uçları artık KİŞİSEL token ister (get_current_user). Kişisel token ancak
# genel şifre geçilip kayıt/giriş yapılınca alınır → iki katman da zorunlu.
_user = [Depends(get_current_user)]
app.include_router(routes_entities.router, dependencies=_user)
app.include_router(routes_dashboard.router, dependencies=_user)
app.include_router(routes_refresh.router, dependencies=_user)
app.include_router(routes_chat.router, dependencies=_user)
app.include_router(routes_suggestions.router, dependencies=_user)
app.include_router(routes_symbols.router, dependencies=_user)

# Admin paneli — yalnızca is_admin (router içinde require_admin).
app.include_router(routes_admin.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Basit sağlık kontrolü — kasıtlı olarak korumasız."""
    return {"status": "ok"}
