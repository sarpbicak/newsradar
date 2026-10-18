"""Sistem-geneli LLM maliyet güvencesi: günlük USD bütçesi + çağrı başına maliyet takibi.

Herkese açık sitede asıl koruma budur — tanımadığın kullanıcılar sahibin Claude
faturasını yakmasın. Her LLM çağrısı (model, input/output/cache token'ları, USD) llm_usage
tablosuna bir satır olarak yazılır; maliyet model fiyat tablosundan hesaplanır
(analysis/model_specs.py). Günlük (UTC) toplam NEWSRADAR_DAILY_BUDGET_USD'ye ulaşınca yeni
analiz DURUR (scheduler ve tarama ortası dahil). Admin paneli harcamayı buradan okur.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .analysis.model_specs import cost_usd, long_prompt_threshold
from .config import get_settings
from .db.database import session_scope
from .db.models import LlmUsage

logger = logging.getLogger("newsradar.budget")

_unpriced_warned: set[str] = set()


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def record_llm_call(
    model: str,
    purpose: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Tek bir LLM çağrısının kullanımını + USD maliyetini kaydet; maliyeti döndürür.

    Hata-toleranslı: kayıt başarısız olsa bile LLM yanıtı kullanılır (yalnızca loglanır)."""
    inp, out = int(input_tokens or 0), int(output_tokens or 0)
    cw, cr = int(cache_creation_tokens or 0), int(cache_read_tokens or 0)
    cost = cost_usd(model, inp, out, cw, cr)
    if cost is None:
        cost = 0.0
        if model not in _unpriced_warned:
            _unpriced_warned.add(model)
            logger.warning("[budget] '%s' fiyat tablosunda yok — maliyeti 0 sayılıyor "
                           "(USD bütçesi bu modeli SINIRLAMAZ).", model)
    threshold = long_prompt_threshold(model)
    prompt = inp + cw + cr
    if threshold and prompt > threshold:
        logger.error("[budget] %s prompt %d token > %d eşiği — bu çağrı YÜKSEK fiyat "
                     "kademesinden faturalandı ($%.4f).", model, prompt, threshold, cost)
    try:
        with session_scope() as s:
            s.add(LlmUsage(
                model=model, purpose=purpose,
                prompt_tokens=inp, completion_tokens=out,
                cache_creation_tokens=cw, cache_read_tokens=cr,
                total_tokens=inp + out + cw + cr, calls=1, cost_usd=cost,
            ))
    except Exception:  # noqa: BLE001 — kayıt hatası LLM sonucunu bozmasın
        logger.exception("[budget] LLM kullanımı yazılamadı (atlandı): %s", model)
    return cost


def cost_since(dt: datetime) -> float:
    with session_scope() as s:
        return float(s.scalar(
            select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0))
            .where(LlmUsage.created_at >= dt)
        ) or 0.0)


def daily_cost_usd() -> float:
    """Bugün (UTC) harcanan toplam USD."""
    return cost_since(_start_of_today_utc())


def tokens_since(dt: datetime) -> int:
    with session_scope() as s:
        return int(s.scalar(
            select(func.coalesce(func.sum(LlmUsage.total_tokens), 0))
            .where(LlmUsage.created_at >= dt)
        ) or 0)


def daily_tokens_used() -> int:
    """Bugün (UTC) kullanılan toplam token (bilgi amaçlı; bütçe USD'dir)."""
    return tokens_since(_start_of_today_utc())


def budget_remaining_usd() -> float | None:
    """Günlük kalan USD (sınırsızsa None). Negatif olmaz."""
    budget = get_settings().daily_budget_usd
    if budget <= 0:
        return None
    return max(0.0, budget - daily_cost_usd())


def is_budget_exceeded() -> bool:
    """Günlük USD bütçesi doldu mu? Sınırsızsa (0) asla."""
    budget = get_settings().daily_budget_usd
    if budget <= 0:
        return False
    return daily_cost_usd() >= budget


def usage_breakdown(dt: datetime) -> list[dict]:
    """dt'den beri model başına kırılım (çağrı, token'lar, USD) — admin paneli.
    Eski tarama-başı satırlar (model=None) 'eski kayıt' olarak gruplanır."""
    with session_scope() as s:
        rows = s.execute(
            select(
                LlmUsage.model,
                func.coalesce(func.sum(LlmUsage.calls), 0),
                func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
                func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_creation_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_read_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cost_usd), 0.0),
            )
            .where(LlmUsage.created_at >= dt)
            .group_by(LlmUsage.model)
            .order_by(func.sum(LlmUsage.cost_usd).desc())
        ).all()
    out = []
    for model, calls, inp, outp, cw, cr, cost in rows:
        out.append({
            "model": model or "legacy", "calls": int(calls),
            "input_tokens": int(inp), "output_tokens": int(outp),
            "cache_creation_tokens": int(cw), "cache_read_tokens": int(cr),
            "cost_usd": round(float(cost), 4),
            "cache_hit_rate": _hit_rate(int(inp), int(cw), int(cr)),
        })
    return out


def _hit_rate(inp: int, cw: int, cr: int) -> float | None:
    denom = inp + cw + cr
    return round(cr / denom, 3) if denom else None


def cache_hit_rate(dt: datetime) -> float | None:
    """Girdi token'larının ne kadarı önbellekten okundu (cache_read / tüm girdi)."""
    with session_scope() as s:
        inp, cw, cr = s.execute(
            select(
                func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_creation_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_read_tokens), 0),
            ).where(LlmUsage.created_at >= dt, LlmUsage.model.is_not(None))
        ).one()
    return _hit_rate(int(inp), int(cw), int(cr))


def days_ago(n: int) -> datetime:
    return _start_of_today_utc() - timedelta(days=n)
