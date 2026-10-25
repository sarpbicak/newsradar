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
    routes_feedback,
    routes_how,
    routes_public,
    routes_refresh,
    routes_session,
    routes_suggestions,
    routes_symbols,
    routes_users,
)
from ..security import install_log_masking
from .routes_auth import get_current_user

logging.basicConfig(level=logging.INFO)
# GÜVENLİK (kritik): httpx/httpcore (ve SDK 1.x'in httpx2'si) INFO seviyesinde tam istek
# URL'ini loglar; bu URL NewsAPI/Finnhub/FMP anahtarını query parametresi olarak taşır.
# install_log_masking bu logger'ları WARNING'e çeker VE tüm kayıtlarda anahtarları maskeler
# (query parametresi + çıplak sk-ant-*/sk-or-v1-*/nvapi-* anahtarları).
install_log_masking()


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
    # Lookback dışına düşmüş bekleyen makaleleri açılışta EXPIRED işaretle (LLM'e gitmesin;
    # kuyruk sayıları açılıştan itibaren doğru görünsün).
    try:
        from ..analysis.pipeline import expire_stale_pending

        _log.info("Expired: %d bekleyen makale lookback dışında işaretlendi.",
                  expire_stale_pending())
    except Exception:  # noqa: BLE001 — açılışı çökertmesin
        _log.exception("Expired işaretleme açılışta başarısız (atlandı).")
    # GİZLİLİK: saklama süresini aşan IP kayıtlarını açılışta da temizle (günlük iş ayrıca).
    try:
        from ..security import prune_ip_records

        prune_ip_records()
    except Exception:  # noqa: BLE001 — temizlik hatası açılışı çökertmesin
        _log.exception("IP kayıt temizliği açılışta başarısız (atlandı).")
    # Deploy: kalıcı olmayan diskte DB boş başlamasın diye opsiyonel oto-seed.
    if get_settings().seed_on_start:
        from ..seed import seed

        seed()
    # BİR KEZLİK migration: pre-watchlist ORTAK listeyi admin'e devret (idempotent).
    # seed'den SONRA çalışır ki seed'lenen entity'ler de admin'e taşınabilsin.
    try:
        from ..db.database import session_scope
        from ..watchlist import backfill_watchlist_to_admin

        with session_scope() as _s:
            moved = backfill_watchlist_to_admin(_s)
        if moved:
            _log.info("Watchlist migration: %d entity admin'in listesine devredildi.", moved)
    except Exception:  # noqa: BLE001 — migration hatası açılışı çökertmesin
        _log.exception("Watchlist backfill migration başarısız (atlandı).")
    # Yenileme kuyruğu işçisi (daemon thread; ilk işte de tembel başlar). Kuyruk ve
    # "çalışıyor" durumu yalnızca bellekte: açılışta temizlenecek kalıcı bir işaret yok.
    from .. import refresh_queue

    # Sahte tarama YALNIZCA test/e2e içindir: gerçek haber/analiz yapılmaz, kullanıcı "yenilendi"
    # görür ama veri güncellenmez. Production'da tanımlanırsa yüksek sesle uyar (Caddy arkası =
    # EC2 production profili → ERROR).
    _fake = get_settings().fake_refresh_seconds
    if _fake > 0:
        _lvl = logging.ERROR if get_settings().trusted_proxy == "caddy" else logging.WARNING
        logging.getLogger("newsradar").log(
            _lvl,
            "NEWSRADAR_FAKE_REFRESH_SECONDS=%s tanımlı: yenilemeler SAHTE (ağ/LLM yok, veri güncellenmez). "
            "Bu değişken yalnızca test içindir, production'da ASLA tanımlanmamalı.", _fake)
    # E-posta console arka ucu üretimde gönderim YAPMAZ (yalnızca log): doğrulama/sıfırlama
    # postaları kullanıcıya ulaşmaz. Caddy arkasında (EC2 production profili) ERROR.
    if get_settings().email_backend == "console" and get_settings().trusted_proxy == "caddy":
        logging.getLogger("newsradar").error(
            "EMAIL_BACKEND=console: doğrulama ve şifre sıfırlama e-postaları GÖNDERİLMİYOR "
            "(yalnızca log). Production'da EMAIL_BACKEND=ses kullanın (docs/DEPLOY_AWS.md, SES kurulumu).")
    refresh_queue.ensure_worker()
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
    # HSTS: HTTPS'i zorla (Render TLS sonlandırır). Cross-origin API için değerli.
    resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    # CSP: bu servis yalnızca JSON döndürür (HTML/JS sunmaz) → çok kısıtlı politika yeter.
    # (Frontend HTML'inin CSP'si static host tarafında ayarlanmalı.)
    resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    # Sürüm sızıntısını önle: uvicorn 'Server: uvicorn' ekler → jenerik yap (parmak izi
    # + bilinen-sürüm açığı hedeflemesini zorlaştır). X-Powered-By zaten set edilmiyor.
    resp.headers["Server"] = "NewsRadar"
    return resp


# CORS: yerel Vite + NEWSRADAR_CORS_ORIGINS / FRONTEND_URL. Anonim cihaz cookie'si (HttpOnly)
# cross-origin gönderileceği için allow_credentials=True + KESİN origin listesi (credentials
# ile '*' tarayıcıda geçersiz). Deploy'da tam frontend origin'lerini verin.
_origins = get_settings().cors_origins
if "*" in _origins:
    # '*' + credentials geçersiz → yalnızca yerel dev origin'lerine düş (cookie çalışsın).
    _origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],  # PATCH: admin görünen ad
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After"],  # "Tekrar gönder" bekleme süresi farklı alt alan adından okunabilsin
)

# Genel şifre ucu (/auth/login) — geriye uyum için duruyor ama artık ZORUNLU DEĞİL
# (site herkese açık; anon cihaz oturumu + kayıt/giriş genel şifre gerektirmez).
app.include_router(routes_auth.router)

# Anonim cihaz oturumu (şifresiz) — açılışta /session/bootstrap.
app.include_router(routes_session.router)

# Geri bildirim (şifresiz; anon da yazabilir). Admin okuma uçları routes_admin'de.
app.include_router(routes_feedback.router)

# Kişisel hesaplar: register/login/upgrade (HERKESE AÇIK), /users/me kişisel token ister.
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
app.include_router(routes_how.router, dependencies=_user)

# Admin paneli — yalnızca is_admin (router içinde require_admin).
app.include_router(routes_admin.router)

# Landing sayfası (/) — oturumsuz, yalnızca toplamlar + seed örneği (routes_public).
app.include_router(routes_public.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Basit sağlık kontrolü — kasıtlı olarak korumasız."""
    return {"status": "ok"}


@app.get("/privacy-info", tags=["health"])
def privacy_info() -> dict:
    """Gizlilik metni için gerçek değerler — kasıtlı olarak korumasız (giriş öncesi okunur).

    Metin koddan beslenir: LLM sağlayıcısı aktif provider env'inden, barındırma ve iletişim
    adresi env'den, IP saklama süresi temizlik işinin kullandığı ayardan gelir."""
    from ..analysis.llm import provider_display_name

    s = get_settings()
    return {
        "llm_provider": provider_display_name(),
        "hosting_provider": s.hosting_provider,
        "contact_email": s.contact_email or None,
        "ip_retention_days": s.ip_retention_days,
        # Hesap e-postaları (doğrulama / şifre sıfırlama) kimin üzerinden gider.
        "email_provider": f"Amazon SES ({s.email_ses_region})" if s.email_backend == "ses" else None,
    }
