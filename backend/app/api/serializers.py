"""DB modellerini API yanıt modellerine çeviren yardımcılar."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Article, Entity, EntityAnalysis, PriceSnapshot
from .schemas import (
    AnalysisOut,
    ArticleOut,
    DeltaOut,
    EntityCardOut,
    PreviousAnalysisOut,
    PricePointOut,
    RiskPointOut,
)


def _latest_analysis(session: Session, entity_id: int) -> EntityAnalysis | None:
    return session.scalar(
        select(EntityAnalysis)
        .where(EntityAnalysis.entity_id == entity_id)
        .order_by(EntityAnalysis.created_at.desc())
    )


def _previous_analysis(session: Session, entity_id: int) -> EntityAnalysis | None:
    """Son değerlendirmeden bir öncekini döner (yoksa None → yeterli geçmiş yok)."""
    return session.scalar(
        select(EntityAnalysis)
        .where(EntityAnalysis.entity_id == entity_id)
        .order_by(EntityAnalysis.created_at.desc())
        .offset(1)
        .limit(1)
    )


def _previous_out(prev: EntityAnalysis | None) -> PreviousAnalysisOut | None:
    if prev is None:
        return None
    return PreviousAnalysisOut(
        risk_score=prev.risk_score,
        stance=prev.stance,
        sentiment_trend=prev.sentiment_trend,
        avg_sentiment=prev.avg_sentiment,
        created_at=prev.created_at,
    )


def _delta_out(
    latest: EntityAnalysis | None, prev: EntityAnalysis | None
) -> DeltaOut | None:
    """İki snapshot arasındaki değişim. Biri yoksa None (sessiz 'yeterli geçmiş yok')."""
    if latest is None or prev is None:
        return None
    sentiment_delta = None
    if latest.avg_sentiment is not None and prev.avg_sentiment is not None:
        sentiment_delta = round(latest.avg_sentiment - prev.avg_sentiment, 3)
    stance_changed = latest.stance != prev.stance
    return DeltaOut(
        risk_delta=latest.risk_score - prev.risk_score,
        stance_changed=stance_changed,
        previous_stance=prev.stance if stance_changed else None,
        sentiment_delta=sentiment_delta,
    )


def risk_history(session: Session, entity_id: int, limit: int = 30) -> list[RiskPointOut]:
    """Son ~N değerlendirmenin risk skoru zaman serisi (eski → yeni)."""
    rows = session.scalars(
        select(EntityAnalysis)
        .where(EntityAnalysis.entity_id == entity_id)
        .order_by(EntityAnalysis.created_at.desc())
        .limit(limit)
    ).all()
    return [
        RiskPointOut(created_at=r.created_at, risk_score=r.risk_score, stance=r.stance)
        for r in reversed(rows)  # kronolojik: eski → yeni
    ]


def price_history(session: Session, entity_id: int, limit: int = 30) -> list[PricePointOut]:
    """Son ~N fiyat snapshot'ı (eski → yeni). Ticker olmayan entity'de boş liste."""
    rows = session.scalars(
        select(PriceSnapshot)
        .where(PriceSnapshot.entity_id == entity_id)
        .order_by(PriceSnapshot.fetched_at.desc())
        .limit(limit)
    ).all()
    return [PricePointOut(fetched_at=r.fetched_at, price=r.price) for r in reversed(rows)]


def analysis_out(a: EntityAnalysis | None) -> AnalysisOut | None:
    if a is None:
        return None
    return AnalysisOut(
        risk_score=a.risk_score,
        sentiment_trend=a.sentiment_trend,
        top_drivers=a.top_drivers or [],
        summary=a.summary,
        stance=a.stance,
        conviction=a.conviction,
        what_to_verify=a.what_to_verify or [],
        invalidation=a.invalidation,
        articles_considered=a.articles_considered,
        created_at=a.created_at,
    )


def entity_card(session: Session, entity: Entity) -> EntityCardOut:
    """Overview kartı için entity özetini toplar."""
    article_count = session.scalar(
        select(func.count()).select_from(Article).where(Article.entity_id == entity.id)
    ) or 0
    analyzed_count = session.scalar(
        select(func.count()).select_from(Article).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    ) or 0
    avg_sentiment = session.scalar(
        select(func.avg(Article.sentiment)).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    )

    # En sık risk bayrakları (analiz edilmiş makalelerden).
    flag_rows = session.scalars(
        select(Article.risk_flags).where(
            Article.entity_id == entity.id, Article.analyzed.is_(True)
        )
    ).all()
    counter: Counter[str] = Counter()
    for flags in flag_rows:
        for f in (flags or []):
            counter[f] += 1
    top_flags = [f for f, _ in counter.most_common(4)]

    latest = _latest_analysis(session, entity.id)
    previous = _previous_analysis(session, entity.id)

    # Fiyat: yalnızca ticker entity'lerde (keyword'de None kalır).
    price_snap = None
    if entity.type == "ticker":
        price_snap = session.scalar(
            select(PriceSnapshot)
            .where(PriceSnapshot.entity_id == entity.id)
            .order_by(PriceSnapshot.fetched_at.desc())
        )

    return EntityCardOut(
        id=entity.id,
        name=entity.name,
        type=entity.type,
        query=entity.query,
        active=entity.active,
        article_count=article_count,
        analyzed_count=analyzed_count,
        avg_sentiment=round(avg_sentiment, 3) if avg_sentiment is not None else None,
        top_flags=top_flags,
        last_updated=latest.created_at if latest else None,
        analysis=analysis_out(latest),
        previous_analysis=_previous_out(previous),
        delta=_delta_out(latest, previous),
        price=price_snap.price if price_snap else None,
        change_percent=price_snap.change_percent if price_snap else None,
        price_updated_at=price_snap.fetched_at if price_snap else None,
    )


def article_out(a: Article) -> ArticleOut:
    return ArticleOut(
        id=a.id,
        url=a.url,
        title=a.title,
        source=a.source,
        published_at=a.published_at,
        provider=a.provider,
        analyzed=a.analyzed,
        sentiment=a.sentiment,
        event_type=a.event_type,
        risk_flags=a.risk_flags,
        impact_horizon=a.impact_horizon,
        relevance=a.relevance,
        rationale=a.rationale,
    )
