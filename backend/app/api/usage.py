"""Kullanım eventi kaydı — 'kim ne yaptı' takibi (usage_events).

Veri ORTAK; yalnızca eylemler kullanıcıya bağlanır. record_event mevcut session'a
event ekler (route'un get_db bağımlılığı commit eder). Hata-toleranslı: loglama
başarısız olsa bile ASIL işlem etkilenmez.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..db.models import USAGE_EVENT_TYPES, UsageEvent

logger = logging.getLogger("newsradar.usage")


def record_event(
    db: Session, user_id: int, event_type: str, detail: dict | None = None
) -> None:
    """Bir kullanım eventi ekler. Geçersiz tip/DB hatası ASIL işlemi bozmaz."""
    if event_type not in USAGE_EVENT_TYPES:
        logger.warning("Bilinmeyen usage event tipi: %s", event_type)
        return
    try:
        db.add(UsageEvent(user_id=user_id, event_type=event_type, detail=detail))
        db.flush()
    except Exception:  # noqa: BLE001 — takip, asıl işlemi asla engellemez
        logger.exception("Usage event yazılamadı (atlandı): %s", event_type)
