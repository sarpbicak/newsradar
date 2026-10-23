"""Yenileme uçları: POST /refresh (asenkron) + GET /status (süreç durumu dahil)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import scheduler
from ..config import get_settings
from ..db.database import get_db
from ..db.models import UsageEvent, User
from ..providers import provider_status
from ..quota import newsapi_usage
from ..refresh import get_state, is_running, start_background_refresh
from ..watchlist import user_entity_ids
from .routes_auth import get_current_user
from .schemas import NewsApiQuotaOut, ProviderStatusOut, RefreshAck
from .usage import record_event

router = APIRouter(tags=["refresh"])


def _refresh_window(db: Session, user: User):
    """Son 24 saatteki elle yenileme olayları (rolling pencere) için sorgu koşulları."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        UsageEvent.user_id == user.id,
        UsageEvent.event_type == "refresh",
        UsageEvent.created_at >= since,
    )


def _refresh_quota(db: Session, user: User) -> tuple[bool, int, int]:
    """Kullanıcının elle yenileme kotası (rolling 24s). Admin muaf.

    (uygun_mu, limit, kullanılan) döner. limit=0 → sınırsız.
    """
    limit = get_settings().refresh_limit_for(user)
    if limit <= 0:  # 0 = sınırsız (admin)
        return True, limit, 0
    used = db.scalar(select(func.count()).select_from(UsageEvent).where(*_refresh_window(db, user))) or 0
    return used < limit, limit, used


def _refresh_resets_at(db: Session, user: User, limit: int, used: int) -> datetime | None:
    """Hak dolduysa bir hakkın geri geleceği an: penceredeki en eski yenileme + 24 saat."""
    if limit <= 0 or used < limit:
        return None
    oldest = db.scalar(select(func.min(UsageEvent.created_at)).where(*_refresh_window(db, user)))
    if oldest is None:
        return None
    if oldest.tzinfo is None:  # SQLite naive datetime döndürür (UTC yazılır)
        oldest = oldest.replace(tzinfo=timezone.utc)
    return oldest + timedelta(hours=24)


@router.post("/refresh", response_model=RefreshAck)
def refresh(
    hours: int | None = Query(None, description="Geriye dönük pencere (saat)"),
    scheduler_enabled: bool | None = Query(
        None, description="Saatlik otomatik yenilemeyi aç/kapat"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RefreshAck:
    """Yenilemeyi ARKA PLANDA başlatır ve hemen döner (tarama 1-2 dk sürebilir).

    Frontend, ilerlemeyi /status'u yoklayarak takip eder. Zaten bir tarama
    çalışıyorsa yenisi başlatılmaz. Elle yenileme kullanıcıya kaydedilir
    (scheduler'ın otomatik yenilemesi kullanıcıya bağlı değildir, kaydedilmez).
    """
    if scheduler_enabled is not None:
        scheduler.set_enabled(scheduler_enabled)

    # KİŞİSEL elle yenileme: yalnızca kullanıcının KENDİ listesindeki entity'leri işle
    # (ortak havuzun tamamını değil — ilerleme "1/1" doğru olsun, kota adil olsun).
    # Havuzun geri kalanını scheduler zaten 6 saatte bir tazeliyor.
    my_ids = user_entity_ids(db, user.id)
    if not my_ids:
        return RefreshAck(
            started=False,
            is_running=is_running(),
            message="İzleme listeniz boş — önce bir şirket ekleyin.",
        )

    # Kişi başı günlük elle yenileme kotası (admin muaf). Zaten çalışan bir
    # yenileme kota harcamaz (started=False → event yok); yalnızca YENİ başlatma sayılır.
    ok, limit, used = _refresh_quota(db, user)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(f"Günlük yenileme limitine ulaştınız ({used}/{limit}). "
                    "Otomatik güncelleme arka planda 6 saatte bir çalışıyor."),
        )

    started = start_background_refresh(hours, entity_ids=my_ids, user_id=user.id)
    if started:
        record_event(db, user.id, "refresh", None)
    return RefreshAck(
        started=started,
        is_running=True,
        message="Yenileme başlatıldı." if started else "Yenileme zaten çalışıyor.",
    )


@router.get("/status", response_model=ProviderStatusOut)
def status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProviderStatusOut:
    """Sağlayıcı/LLM/zamanlayıcı + yenileme süreci + NewsAPI kotası + KİŞİSEL yenileme kotası."""
    st = get_state()
    settings = get_settings()
    quota = None
    if settings.newsapi_available:
        quota = NewsApiQuotaOut(**newsapi_usage(db))
    _ok, r_limit, r_used = _refresh_quota(db, user)

    # KİŞİSEL durum: is_running/ilerleme/son özet YALNIZCA bu kullanıcının başlattığı
    # taramaya aittir. Başka kullanıcının (ya da scheduler'ın user_id=None) taraması
    # bu kullanıcıya "çalışıyor" ya da yabancı uyarılar olarak sızmaz (izolasyon).
    mine_running = st["is_running"] and st["user_id"] == user.id
    mine_last = st["last_user_id"] == user.id

    from .. import budget
    from ..watchlist import watchlist_count
    return ProviderStatusOut(
        providers=provider_status(),
        claude=settings.llm_available,  # "claude" alan adı geriye uyum; aktif LLM'i yansıtır
        scheduler_enabled=scheduler.is_enabled(),
        newsapi_quota=quota,
        is_running=mine_running,
        progress_done=st["progress_done"] if mine_running else 0,
        progress_total=st["progress_total"] if mine_running else 0,
        current_entity=st["current_entity"] if mine_running else None,
        step=st["step"] if mine_running else None,
        step_entity=st["step_entity"] if mine_running else None,
        step_count=st["step_count"] if mine_running else None,
        progress_fraction=st["progress_fraction"] if mine_running else 0.0,
        skipped_entity=st["skipped_entity"] if mine_running else None,
        last_completed_at=st["last_completed_at"] if mine_last else None,
        last_summary=st["last_summary"] if mine_last else None,
        refresh_limit=r_limit,
        refresh_used=r_used,
        refresh_is_admin=user.is_admin,
        # Arayüzdeki açıklama metni için iki ayar (sayılar koddan değil ayarlardan).
        refresh_limit_anon=settings.max_refresh_anon,
        refresh_limit_registered=settings.max_refresh_registered,
        refresh_resets_at=_refresh_resets_at(db, user, r_limit, r_used),
        budget_exceeded=budget.is_budget_exceeded(),
        cost_today_usd=round(budget.daily_cost_usd(), 4),
        daily_budget_usd=settings.daily_budget_usd,
        entity_limit=settings.entity_limit_for(user),
        entity_used=watchlist_count(db, user.id),
    )
