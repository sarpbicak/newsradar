"""Sistem-geneli LLM maliyet güvencesi: günlük token bütçesi + maliyet takibi.

Herkese açık sitede asıl koruma budur — tanımadığın kullanıcılar sahibin OpenRouter
faturasını yakmasın. Günlük toplam token tavana ulaşınca yeni analiz DURUR (scheduler
dahil). Kullanım llm_usage tablosuna yazılır; admin panelinde tahmini maliyet gösterilir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from .config import get_settings
from .db.database import session_scope
from .db.models import LlmUsage

logger = logging.getLogger("newsradar.budget")


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def daily_tokens_used() -> int:
    """Bugün (UTC) kullanılan toplam LLM token sayısı."""
    with session_scope() as s:
        return int(s.scalar(
            select(func.coalesce(func.sum(LlmUsage.total_tokens), 0))
            .where(LlmUsage.created_at >= _start_of_today_utc())
        ) or 0)


def tokens_since(dt: datetime) -> int:
    with session_scope() as s:
        return int(s.scalar(
            select(func.coalesce(func.sum(LlmUsage.total_tokens), 0))
            .where(LlmUsage.created_at >= dt)
        ) or 0)


def record_llm_usage(prompt_tokens: int, completion_tokens: int, calls: int = 0) -> None:
    """Bir taramanın token kullanımını kaydet (delta). 0/negatif ise yazma."""
    total = int(prompt_tokens) + int(completion_tokens)
    if total <= 0:
        return
    with session_scope() as s:
        s.add(LlmUsage(
            prompt_tokens=int(prompt_tokens), completion_tokens=int(completion_tokens),
            total_tokens=total, calls=int(calls),
        ))
    logger.info("[budget] +%d token kaydedildi (bugün toplam=%d/%s)",
                total, daily_tokens_used(), get_settings().daily_token_budget or "∞")


def budget_remaining() -> int | None:
    """Günlük kalan token (sınırsızsa None). Negatif olmaz (0'da durur)."""
    budget = get_settings().daily_token_budget
    if budget <= 0:
        return None
    return max(0, budget - daily_tokens_used())


def is_budget_exceeded(extra: int = 0) -> bool:
    """Günlük token bütçesi (extra dahil) aşıldı mı? Sınırsızsa asla."""
    budget = get_settings().daily_token_budget
    if budget <= 0:
        return False
    return (daily_tokens_used() + max(0, extra)) >= budget


def estimated_cost_usd(tokens: int) -> float:
    """Kaba maliyet: token × birim fiyat (1M başına USD)."""
    return round(tokens / 1_000_000 * get_settings().token_unit_cost_usd, 2)
