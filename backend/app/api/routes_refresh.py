"""Yenileme uçları: POST /refresh (asenkron) + GET /status (süreç durumu dahil)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import scheduler
from ..db.database import get_db
from ..db.models import User
from ..providers import provider_status
from ..quota import newsapi_usage
from ..refresh import get_state, start_background_refresh
from .routes_auth import get_current_user
from .schemas import NewsApiQuotaOut, ProviderStatusOut, RefreshAck
from .usage import record_event

router = APIRouter(tags=["refresh"])


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

    started = start_background_refresh(hours)
    if started:
        record_event(db, user.id, "refresh", None)
    return RefreshAck(
        started=started,
        is_running=True,
        message="Yenileme başlatıldı." if started else "Yenileme zaten çalışıyor.",
    )


@router.get("/status", response_model=ProviderStatusOut)
def status(db: Session = Depends(get_db)) -> ProviderStatusOut:
    """Sağlayıcı/Claude/zamanlayıcı + yenileme süreci + NewsAPI kotası."""
    from ..config import get_settings

    st = get_state()
    settings = get_settings()
    quota = None
    if settings.newsapi_available:
        quota = NewsApiQuotaOut(**newsapi_usage(db))
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
    )
