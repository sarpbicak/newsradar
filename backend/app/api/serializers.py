"""DB modellerini API yanıt modellerine çeviren yardımcılar."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Article, Entity, EntityAnalysis
from .schemas import AnalysisOut, ArticleOut, EntityCardOut


def _latest_analysis(session: Session, entity_id: int) -> EntityAnalysis | None:
    return session.scalar(
        select(EntityAnalysis)
        .where(EntityAnalysis.entity_id == entity_id)
        .order_by(EntityAnalysis.created_at.desc())
    )


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
