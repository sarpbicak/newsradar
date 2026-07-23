"""Fiyat çekme + snapshot yazma + prompt bağlamı.

Yalnızca `type=ticker` entity'ler için çalışır. Ucuz (tek /quote çağrısı) ve
hata-toleranslı: bir sağlayıcı patlarsa uyarı toplanır, yenileme devam eder.

ÖNEMLİ: Fiyat verisi TAHMİN için değil — haberin fiyata yansıyıp yansımadığını
görmek için. Hedef fiyat / teknik sinyal ÜRETİLMEZ.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db.database import session_scope
from .db.models import Entity, PriceSnapshot
from .providers import get_price_provider

logger = logging.getLogger("newsradar.prices")

MAX_PRICE_HISTORY = 100   # entity başına saklanacak en fazla fiyat snapshot'ı
WEEK_WINDOW_DAYS = 7      # "son ~hafta değişimi" için pencere


def refresh_prices() -> list[str]:
    """Tüm aktif ticker entity'ler için güncel fiyatı çeker ve snapshot yazar."""
    provider = get_price_provider()
    warnings: list[str] = []
    if not provider.is_available():
        return warnings  # anahtar yoksa sessizce atla (haber tarafı zaten uyarıyor)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        tickers = session.scalars(
            select(Entity).where(Entity.active.is_(True), Entity.type == "ticker")
        ).all()
        for e in tickers:
            try:
                res = provider.quote(e)
            except Exception as exc:  # noqa: BLE001 — tek entity hatası yenilemeyi çökertmesin
                warnings.append(f"[{e.name}] fiyat beklenmeyen hata: {exc}")
                continue
            if res.warning:
                warnings.append(f"[{e.name}] {res.warning}")
                continue
            q = res.quote
            if q is None:
                continue
            session.add(
                PriceSnapshot(
                    entity_id=e.id, price=q.price, change_percent=q.change_percent,
                    previous_close=q.previous_close, day_high=q.day_high,
                    day_low=q.day_low, fetched_at=now,
                )
            )
            session.flush()
            _prune(session, e.id)
    return warnings


def _prune(session: Session, entity_id: int) -> None:
    """Entity başına en yeni MAX_PRICE_HISTORY dışındaki eski snapshot'ları siler."""
    stale = session.scalars(
        select(PriceSnapshot.id)
        .where(PriceSnapshot.entity_id == entity_id)
        .order_by(PriceSnapshot.fetched_at.desc())
        .offset(MAX_PRICE_HISTORY)
    ).all()
    if stale:
        session.execute(delete(PriceSnapshot).where(PriceSnapshot.id.in_(stale)))


def latest_snapshot(session: Session, entity_id: int) -> PriceSnapshot | None:
    return session.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.entity_id == entity_id)
        .order_by(PriceSnapshot.fetched_at.desc())
    )


def price_context_for(entity_id: int) -> dict | None:
    """Analiz prompt'u için fiyat bağlamı: güncel fiyat, günlük % ve ~haftalık %.

    Haftalık %: son 7 gün içindeki en eski snapshot'a göre hesaplanır (kendi
    verimizden; ekstra API çağrısı yok). Yeterli geçmiş yoksa None.
    """
    with session_scope() as session:
        latest = latest_snapshot(session, entity_id)
        if latest is None:
            return None
        ctx: dict = {"price": latest.price, "change_percent": latest.change_percent}
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=WEEK_WINDOW_DAYS)
        old = session.scalar(
            select(PriceSnapshot)
            .where(PriceSnapshot.entity_id == entity_id, PriceSnapshot.fetched_at >= cutoff)
            .order_by(PriceSnapshot.fetched_at.asc())
        )
        if old and old.price and latest.price and old.id != latest.id:
            ctx["week_change_percent"] = round((latest.price - old.price) / old.price * 100, 2)
        return ctx
