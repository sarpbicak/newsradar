"""LLM sağlık takibi — sorun kullanıcıdan önce admin panelinde görünsün.

Her yenileme sonunda bir sağlık olayı yazılır ('ok' | 'quota' | 'error'). Admin paneli
son olayı (son çağrı başarılı mıydı) ve son 24 saatteki kota hatası sayısını gösterir.
Böylece OpenRouter kota/bakiye sorunu kullanıcı fark etmeden önce tespit edilir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db.database import session_scope
from .db.models import LlmHealthEvent

logger = logging.getLogger("newsradar.health")

_VALID_KINDS = ("ok", "quota", "error")


def record_llm_health(kind: str, detail: str | None = None, status_code: int | None = None) -> None:
    """Bir yenilemenin LLM sonucunu kaydet. kind: 'ok' | 'quota' | 'error'."""
    if kind not in _VALID_KINDS:
        kind = "error"
    try:
        with session_scope() as s:
            s.add(LlmHealthEvent(
                kind=kind,
                status_code=status_code,
                detail=(detail or "")[:500] or None,
            ))
    except Exception:  # noqa: BLE001 — sağlık kaydı asıl akışı çökertmesin
        logger.exception("[health] LLM sağlık olayı yazılamadı (atlandı).")


def health_snapshot() -> dict:
    """Admin paneli için: son olay (kind/at) + son 24 saatteki kota hatası sayısı +
    en son başarılı çağrı zamanı. Hiç olay yoksa alanlar None/0."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since_24h = now - timedelta(hours=24)
    with session_scope() as s:
        last = s.scalars(
            select(LlmHealthEvent).order_by(LlmHealthEvent.created_at.desc()).limit(1)
        ).first()
        quota_24h = int(s.scalar(
            select(func.count()).select_from(LlmHealthEvent)
            .where(LlmHealthEvent.kind == "quota", LlmHealthEvent.created_at >= since_24h)
        ) or 0)
        errors_24h = int(s.scalar(
            select(func.count()).select_from(LlmHealthEvent)
            .where(LlmHealthEvent.kind == "error", LlmHealthEvent.created_at >= since_24h)
        ) or 0)
        last_ok = s.scalar(
            select(func.max(LlmHealthEvent.created_at)).where(LlmHealthEvent.kind == "ok")
        )
        return {
            "last_kind": last.kind if last else None,
            "last_at": last.created_at if last else None,
            "last_status_code": last.status_code if last else None,
            "last_detail": last.detail if last else None,
            "last_ok_at": last_ok,
            "quota_errors_24h": quota_24h,
            "errors_24h": errors_24h,
        }
