"""Analist verisi çekme + snapshot yazma + prompt bağlamı.

Yalnızca `type=ticker` entity'ler için. GERÇEK analist konsensüsü (Finnhub);
NewsRadar/Claude ÜRETMEZ, sadece saklar/aktarır. Hata-toleranslı: patlarsa
uyarı toplanır, yenileme devam eder.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db.database import session_scope
from .db.models import AnalystSnapshot, Entity
from .providers import get_analyst_provider

logger = logging.getLogger("newsradar.analyst")

MAX_ANALYST_HISTORY = 50  # entity başına saklanacak en fazla snapshot


def refresh_analyst() -> list[str]:
    """Tüm aktif ticker entity'ler için analist konsensüsünü çeker ve snapshot yazar."""
    provider = get_analyst_provider()
    warnings: list[str] = []
    if not provider.is_available():
        return warnings  # anahtar yoksa sessizce atla

    with session_scope() as session:
        tickers = session.scalars(
            select(Entity).where(Entity.active.is_(True), Entity.type == "ticker")
        ).all()
        for e in tickers:
            try:
                res = provider.fetch(e)
            except Exception as exc:  # noqa: BLE001 — tek entity hatası yenilemeyi çökertmesin
                warnings.append(f"[{e.name}] analist beklenmeyen hata: {exc}")
                continue
            if res.warning:
                warnings.append(f"[{e.name}] {res.warning}")
                continue
            r = res.rating
            if r is None:
                continue
            session.add(
                AnalystSnapshot(
                    entity_id=e.id,
                    target_high=r.target_high, target_low=r.target_low,
                    target_mean=r.target_mean, target_median=r.target_median,
                    strong_buy=r.strong_buy, buy=r.buy, hold=r.hold,
                    sell=r.sell, strong_sell=r.strong_sell, period=r.period,
                )
            )
            session.flush()
            _prune(session, e.id)
    return warnings


def _prune(session: Session, entity_id: int) -> None:
    stale = session.scalars(
        select(AnalystSnapshot.id)
        .where(AnalystSnapshot.entity_id == entity_id)
        .order_by(AnalystSnapshot.fetched_at.desc())
        .offset(MAX_ANALYST_HISTORY)
    ).all()
    if stale:
        session.execute(delete(AnalystSnapshot).where(AnalystSnapshot.id.in_(stale)))


def latest_snapshot(session: Session, entity_id: int) -> AnalystSnapshot | None:
    return session.scalar(
        select(AnalystSnapshot)
        .where(AnalystSnapshot.entity_id == entity_id)
        .order_by(AnalystSnapshot.fetched_at.desc())
    )


def analyst_context_for(entity_id: int) -> dict | None:
    """Analiz prompt'u için analist konsensüsü bağlamı (yoksa None)."""
    with session_scope() as session:
        snap = latest_snapshot(session, entity_id)
        if snap is None:
            return None
        total = snap.strong_buy + snap.buy + snap.hold + snap.sell + snap.strong_sell
        if total == 0:
            return None
        return {
            "strong_buy": snap.strong_buy, "buy": snap.buy, "hold": snap.hold,
            "sell": snap.sell, "strong_sell": snap.strong_sell, "total": total,
            "period": snap.period,
            "target_mean": snap.target_mean,  # şimdilik None
        }
