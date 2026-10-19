"""API kota takibi — rolling 24 saat (özellikle NewsAPI ücretsiz katman ~100/gün).

Her gerçek çağrı `api_calls` tablosuna yazılır; son 24 saatteki çağrılar sayılır.
%80'de uyarı, dolunca çekme atlanır ve kullanıcıya anlaşılır mesaj gösterilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import ApiCall

WINDOW_HOURS = 24
WARN_RATIO = 0.8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_call(session: Session, provider: str = "newsapi") -> None:
    """Gerçek bir API çağrısını kaydeder (kotadan düşer)."""
    session.add(ApiCall(provider=provider, called_at=_now()))


def prune(session: Session) -> None:
    """24 saatten eski çağrı kayıtlarını siler (tablo şişmesin)."""
    cutoff = _now() - timedelta(hours=WINDOW_HOURS)
    session.execute(delete(ApiCall).where(ApiCall.called_at < cutoff))


def _window_calls(session: Session, provider: str) -> list[datetime]:
    cutoff = _now() - timedelta(hours=WINDOW_HOURS)
    return list(
        session.scalars(
            select(ApiCall.called_at)
            .where(ApiCall.provider == provider, ApiCall.called_at >= cutoff)
            .order_by(ApiCall.called_at)
        ).all()
    )


def newsapi_usage(session: Session) -> dict:
    """Son 24 saatteki NewsAPI kullanımı + durum (uyarı/dolu/sıfırlanma süresi)."""
    limit = get_settings().newsapi_daily_limit
    calls = _window_calls(session, "newsapi")
    used = len(calls)
    remaining = max(0, limit - used)
    exhausted = used >= limit
    warn = used >= int(limit * WARN_RATIO)

    # En eski çağrı 24 saati doldurunca bir slot açılır → "N saat sonra sıfırlanır".
    reset_in_hours = 0.0
    if calls:
        reset_at = calls[0] + timedelta(hours=WINDOW_HOURS)
        reset_in_hours = max(0.0, round((reset_at - _now()).total_seconds() / 3600, 1))

    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "exhausted": exhausted,
        "warn": warn,
        "reset_in_hours": reset_in_hours,
    }
