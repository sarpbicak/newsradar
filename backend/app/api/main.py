"""FastAPI uygulaması — tüm uçları bağlar, açılışta DB + zamanlayıcıyı başlatır.

Çalıştır:  uvicorn app.api.main:app --reload  (backend/ içinden)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
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
# GÜVENLİK (kritik): httpx/httpcore INFO seviyesinde tam istek URL'ini loglar; bu URL
# NewsAPI/Finnhub/FMP anahtarını query parametresi olarak taşır → loglara sır sızar.
# Bu logger'ları WARNING'e çekerek URL loglamayı kapat.
for _noisy in ("httpx", "httpcore", "openai", "anthropic"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Güvenlik: ayrı APP_SECRET önerilir (token imza sırrı). Yoksa APP_PASSWORD'a
    # düşülür — çalışır ama uyar; ikisi de boşsa giriş uçları zaten 503 döner.
    if not os.getenv("APP_SECRET", "").strip():
        logging.getLogger("newsradar").warning(
            "APP_SECRET ayarlı değil — token imzası APP_PASSWORD'a düşüyor. "
            "Üretimde ayrı, güçlü bir APP_SECRET ayarlayın."
        )
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


# Temel güvenlik header'ları — her yanıta eklenir (ucuz sertleştirme).
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


# CORS: yerel Vite + FRONTEND_URL (deploy'da Render frontend domain'i).
# İzinli origin'ler ortam değişkeninden okunur (bkz. config.cors_origins).
# allow_credentials=False (kimlik Authorization header ile taşınır, cookie yok) →
# '*' origin bile kimlik hırsızlığına yol açmaz; yine de config '*'e izin vermez (bkz. cors_origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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
