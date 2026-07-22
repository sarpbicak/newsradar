"""Yenileme ucu: POST /refresh — çek + analiz et; zamanlayıcı aç/kapat bayrağı."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .. import scheduler
from ..providers import provider_status
from ..refresh import run_refresh
from .schemas import ProviderStatusOut, RefreshOut

router = APIRouter(tags=["refresh"])


@router.post("/refresh", response_model=RefreshOut)
def refresh(
    hours: int | None = Query(None, description="Geriye dönük pencere (saat)"),
    scheduler_enabled: bool | None = Query(
        None, description="Saatlik otomatik yenilemeyi aç/kapat"
    ),
) -> RefreshOut:
    """Elle yenileme tetikler; opsiyonel olarak zamanlayıcı bayrağını değiştirir."""
    if scheduler_enabled is not None:
        scheduler.set_enabled(scheduler_enabled)

    summary = run_refresh(hours)
    return RefreshOut(
        fetched_new=summary.fetched_new,
        analyzed=summary.analyzed,
        discarded=summary.discarded,
        entity_assessments=summary.entity_assessments,
        warnings=summary.warnings,
        scheduler_enabled=scheduler.is_enabled(),
    )


@router.get("/status", response_model=ProviderStatusOut)
def status() -> ProviderStatusOut:
    """Sağlayıcı anahtarı durumu + Claude + zamanlayıcı (UI uyarıları için)."""
    from ..config import get_settings

    return ProviderStatusOut(
        providers=provider_status(),
        claude=get_settings().claude_available,
        scheduler_enabled=scheduler.is_enabled(),
    )
