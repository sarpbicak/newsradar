"""Kalıcı ve BEKLENEN sağlayıcı hatalarının cache'i (24 saat).

FMP ücretsiz katmanın 403'ü ya da ABD dışı bir sembol için "veri yok" her taramada aynı
sonucu verir. Bunları her yenilemede yeniden denemek hem kotayı yakar hem de kullanıcıya
anlamsız uyarı birikir. Sağlayıcı sonucu `expected=True` ise sembol SKIP_HOURS boyunca
atlanır; olay yalnızca sunucu (admin) logunda görünür.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .db.models import ProviderSkip
from .messages import render

logger = logging.getLogger("newsradar.providers")

SKIP_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(provider: str, symbol: str) -> str:
    return f"{provider}:{(symbol or '').strip().upper()}"


def is_skipped(session: Session, provider: str, symbol: str) -> bool:
    row = session.get(ProviderSkip, _key(provider, symbol))
    return row is not None and row.until > _now()


def mark_skip(session: Session, provider: str, symbol: str, warning: dict,
              hours: int = SKIP_HOURS) -> None:
    """Sembolü `hours` boyunca atla + admin loguna yaz (kullanıcıya uyarı YOK)."""
    key = _key(provider, symbol)
    row = session.get(ProviderSkip, key)
    if row is None:
        row = ProviderSkip(key=key)
        session.add(row)
    row.until = _now() + timedelta(hours=hours)
    row.code = (warning or {}).get("code", "unknown")
    row.status = (warning or {}).get("params", {}).get("status")
    row.updated_at = _now()
    logger.info("[provider-skip] %s — beklenen/kalıcı durum, %d saat tekrar denenmeyecek: %s",
                key, hours, render(warning) if warning else "-")
