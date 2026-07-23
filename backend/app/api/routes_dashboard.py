"""Dashboard ucu: GET /entities/{id}/dashboard — toplu sonuç + son analiz edilmiş makaleler."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Article, Entity
from .schemas import DashboardOut
from .serializers import article_out, entity_card, risk_history

router = APIRouter(tags=["dashboard"])


@router.get("/entities/{entity_id}/dashboard", response_model=DashboardOut)
def entity_dashboard(
    entity_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> DashboardOut:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity bulunamadı.")

    articles = db.scalars(
        select(Article)
        .where(Article.entity_id == entity_id, Article.prefiltered.is_(False))
        .order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
        .limit(limit)
    ).all()

    return DashboardOut(
        entity=entity_card(db, entity),
        articles=[article_out(a) for a in articles],
        risk_history=risk_history(db, entity_id, limit=30),
    )
