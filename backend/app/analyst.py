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
from .db.models import AnalystSnapshot, Entity, PriceSnapshot
from .messages import msg, with_entity
from .provider_skip import is_skipped, mark_skip
from .providers import get_analyst_provider, get_target_provider

logger = logging.getLogger("newsradar.analyst")

MAX_ANALYST_HISTORY = 50  # entity başına saklanacak en fazla snapshot


def _latest_price(session: Session, entity_id: int) -> float | None:
    snap = session.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.entity_id == entity_id)
        .order_by(PriceSnapshot.fetched_at.desc())
    )
    return snap.price if snap else None


def refresh_analyst(entity_ids: set[int] | None = None) -> list[dict]:
    """Aktif ticker'lar için analist TAVSİYESİ (Finnhub) + HEDEF FİYAT (FMP) çekip
    tek snapshot'ta birleştirir. İki kaynak da hata-toleranslı; biri yoksa diğeri yazılır.

    entity_ids verilirse yalnızca o entity'ler (kişisel elle yenileme); None → tüm aktif.
    accuracy: hedef fiyat YALNIZCA FMP'den gelen gerçek analist verisidir; kaynak
    erişilemezse hedef None kalır (asla tahminle doldurulmaz)."""
    rec_provider = get_analyst_provider()   # Finnhub al/tut/sat
    target_provider = get_target_provider()  # FMP hedef fiyat
    warnings: list[dict] = []  # app.messages.msg(...)
    rec_on = rec_provider.is_available()
    target_on = target_provider.is_available()
    if not rec_on and not target_on:
        return warnings  # ikisi de yoksa sessizce atla

    with session_scope() as session:
        q = select(Entity).where(Entity.active.is_(True), Entity.type == "ticker")
        if entity_ids is not None:
            q = q.where(Entity.id.in_(entity_ids))
        tickers = session.scalars(q).all()
        for e in tickers:
            sb = b = h = s = ss = 0
            period = None
            th = tl = tm = tmed = tcons = None

            # 1) Tavsiye (al/tut/sat) — Finnhub.
            # Kalıcı/beklenen hatası cache'lenmiş sembol için sağlayıcıya hiç gidilmez.
            if rec_on and not is_skipped(session, rec_provider.name, e.query):
                try:
                    res = rec_provider.fetch(e)
                    if res.warning and res.expected:
                        mark_skip(session, rec_provider.name, e.query, res.warning)  # yalnızca log
                    elif res.warning:
                        warnings.append(with_entity(res.warning, e.name))
                    elif res.rating:
                        r = res.rating
                        sb, b, h, s, ss = r.strong_buy, r.buy, r.hold, r.sell, r.strong_sell
                        period = r.period
                except Exception as exc:  # noqa: BLE001
                    warnings.append(msg("provider_error", e.name, source="finnhub_analyst", error=exc))

            # 2) Hedef fiyat — FMP (gerçek analist konsensüsü; yoksa None kalır).
            if target_on and not is_skipped(session, target_provider.name, e.query):
                try:
                    tres = target_provider.fetch(e)
                    if tres.warning and tres.expected:
                        mark_skip(session, target_provider.name, e.query, tres.warning)  # yalnızca log
                    elif tres.warning:
                        warnings.append(with_entity(tres.warning, e.name))
                    elif tres.rating:
                        tr = tres.rating
                        th, tl, tm, tmed, tcons = (
                            tr.target_high, tr.target_low, tr.target_mean,
                            tr.target_median, tr.target_consensus,
                        )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(msg("provider_error", e.name, source="fmp_target", error=exc))

            # İki kaynaktan da hiçbir şey gelmediyse snapshot yazma.
            if (sb + b + h + s + ss) == 0 and tm is None:
                continue

            session.add(
                AnalystSnapshot(
                    entity_id=e.id,
                    target_high=th, target_low=tl, target_mean=tm,
                    target_median=tmed, target_consensus=tcons,
                    strong_buy=sb, buy=b, hold=h, sell=s, strong_sell=ss, period=period,
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
    """Analiz prompt'u için analist bağlamı: tavsiye + GERÇEK hedef fiyat (FMP) + upside.

    Tavsiye ya da hedef fiyattan en az biri varsa bağlam döner (yoksa None).
    upside_percent güncel fiyata göre hesaplanır — Claude'un ayrışmayı yorumlaması için."""
    with session_scope() as session:
        snap = latest_snapshot(session, entity_id)
        if snap is None:
            return None
        total = snap.strong_buy + snap.buy + snap.hold + snap.sell + snap.strong_sell
        has_target = snap.target_mean is not None
        if total == 0 and not has_target:
            return None

        price = _latest_price(session, entity_id)
        upside = None
        if has_target and price:
            upside = round((snap.target_mean - price) / price * 100, 1)

        return {
            "strong_buy": snap.strong_buy, "buy": snap.buy, "hold": snap.hold,
            "sell": snap.sell, "strong_sell": snap.strong_sell, "total": total,
            "period": snap.period,
            # GERÇEK analist hedefi (FMP). Yoksa None — Claude ÜRETMEZ.
            "target_mean": snap.target_mean,
            "target_high": snap.target_high,
            "target_low": snap.target_low,
            "current_price": price,
            "upside_percent": upside,
        }
