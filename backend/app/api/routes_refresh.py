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
from ..refresh import get_state, start_background_refresh
from .routes_auth import get_current_user
from .schemas import NewsApiQuotaOut, ProviderStatusOut, RefreshAck
from .usage import record_event

router = APIRouter(tags=["refresh"])


def _refresh_quota(db: Session, user: User) -> tuple[bool, int, int]:
    """Kullanıcının elle yenileme kotası (rolling 24s). Admin muaf.

    (uygun_mu, limit, kullanılan) döner. limit=0 → sınırsız.
    """
    limit = get_settings().max_refresh_per_day
    if user.is_admin or limit <= 0:
        return True, limit, 0
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    used = db.scalar(
        select(func.count()).select_from(UsageEvent).where(
            UsageEvent.user_id == user.id,
            UsageEvent.event_type == "refresh",
            UsageEvent.created_at >= since,
        )
    ) or 0
    return used < limit, limit, used


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

    # Kişi başı günlük elle yenileme kotası (admin muaf). Zaten çalışan bir
    # yenileme kota harcamaz (started=False → event yok); yalnızca YENİ başlatma sayılır.
    ok, limit, used = _refresh_quota(db, user)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(f"Günlük yenileme limitine ulaştınız ({used}/{limit}). "
                    "Otomatik güncelleme arka planda 6 saatte bir çalışıyor."),
        )

    started = start_background_refresh(hours)
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
    return ProviderStatusOut(
        providers=provider_status(),
        claude=settings.llm_available,  # "claude" alan adı geriye uyum; aktif LLM'i yansıtır
        scheduler_enabled=scheduler.is_enabled(),
        newsapi_quota=quota,
        is_running=st["is_running"],
        progress_done=st["progress_done"],
        progress_total=st["progress_total"],
        last_completed_at=st["last_completed_at"],
        last_summary=st["last_summary"],
        refresh_limit=r_limit,
        refresh_used=r_used,
        refresh_is_admin=user.is_admin,
    )
