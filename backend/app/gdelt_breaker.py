"""GDELT devre kesici: GDELT 429 (ya da "limit requests") dönünce NEWSRADAR_GDELT_BLOCK_HOURS
(varsayılan 6) boyunca GDELT'e HİÇ istek atılmaz.

GDELT sunucu IP'mizi engellediğinde tek ve bekletilmiş bir istek bile 429 alıyor; her
yenilemede yeniden denemek süreyi uzatır, engeli tazeler ve kullanıcıya her seferinde uyarı
biriktirirdi. Devre açıkken GDELT kullanan şirketler (anahtar kelimeli, ABD dışı) mevcut
haberleriyle kalır; kartta tek bir sakin not görünür (news_paused), yenileme özetinde uyarı
çıkmaz. Admin panelinde durum (son 429, devre açık mı, ne zamana kadar) görünür.

Durum DB'de (provider_skips, anahtar "gdelt:*") → süreç yeniden başlasa da korunur (deploy
sonrası ilk istek yine 429 almasın). Süreç içinde bellekte de tutulur: aynı taramadaki diğer
şirketler, satır yazılmadan önce de istek atmaz.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import get_settings
from .db.database import session_scope
from .db.models import ProviderSkip

logger = logging.getLogger("newsradar.providers")

KEY = "gdelt:*"
CODE = "gdelt_blocked"
_open_until: list[datetime | None] = [None]   # bellek (süreç içi)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def block_hours() -> float:
    return max(0.0, get_settings().gdelt_block_hours)


def open_in_memory() -> bool:
    until = _open_until[0]
    return until is not None and until > _now()


def trip_memory() -> datetime:
    """429 görüldü: bu süreçte hemen devreyi aç (DB'ye ingest yazar: persist)."""
    until = _now() + timedelta(hours=block_hours())
    _open_until[0] = until
    return until


def persist(session: Session, status: int | None = 429) -> datetime:
    """Devreyi DB'ye yaz (son 429 zamanı = updated_at). Bellekteki süre de aynı olur."""
    until = _open_until[0] if open_in_memory() else trip_memory()
    row = session.get(ProviderSkip, KEY)
    if row is None:
        row = ProviderSkip(key=KEY)
        session.add(row)
    row.until = until
    row.code = CODE
    row.status = status
    row.updated_at = _now()
    logger.warning("[gdelt] hız sınırı/engel (HTTP %s) → %.1f saat GDELT'e istek atılmayacak (%s'e kadar)",
                   status, block_hours(), until.isoformat(timespec="minutes"))
    return until


def is_open(session: Session | None = None) -> bool:
    """Devre açık mı (bellek ya da DB)? DB'deki açık devre belleğe de alınır."""
    if open_in_memory():
        return True

    def _check(s: Session) -> bool:
        row = s.get(ProviderSkip, KEY)
        if row is not None and row.code == CODE and row.until > _now():
            _open_until[0] = row.until
            return True
        return False

    if session is not None:
        return _check(session)
    with session_scope() as s:
        return _check(s)


def snapshot() -> dict:
    """Admin paneli: {open, until, last_429_at}. Hiç 429 alınmadıysa open=False, zamanlar None."""
    with session_scope() as s:
        row = s.get(ProviderSkip, KEY)
        if row is None or row.code != CODE:
            return {"open": open_in_memory(), "until": _open_until[0], "last_429_at": None}
        return {"open": row.until > _now(), "until": row.until, "last_429_at": row.updated_at}


def reset_memory() -> None:
    """Testler için."""
    _open_until[0] = None
