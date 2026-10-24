"""Dashboard ucu: GET /entities/{id}/dashboard — toplu sonuç + son analiz edilmiş makaleler."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Article, Entity, User
from ..watchlist import in_watchlist
from .routes_auth import get_current_user
from .schemas import ArticleStatusOut, DashboardOut
from .serializers import analyst_history, article_out, content_language, entity_card, price_history, risk_history
from .usage import record_event

router = APIRouter(tags=["dashboard"])


@router.get("/entities/{entity_id}/dashboard", response_model=DashboardOut)
def entity_dashboard(
    entity_id: int,
    limit: int = Query(50, ge=1, le=200),
    lang: str | None = Query(None, description="AI içeriği dili (tr|en); yoksa kullanıcının dili"),
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    entity = db.get(Entity, entity_id)
    # İZOLASYON: kullanıcının kendi listesinde OLMAYAN entity'nin detayına erişemez.
    # Var olmayan gibi 404 (varlığını bile sızdırma — başkasının takip ettiği ortaya çıkmasın).
    if entity is None or not in_watchlist(db, user.id, entity_id):
        raise HTTPException(status_code=404, detail="Entity bulunamadı.")
    record_event(db, user.id, "view_entity", {"entity_id": entity.id, "name": entity.name})

    articles = db.scalars(
        select(Article)
        .where(Article.entity_id == entity_id, Article.prefiltered.is_(False))
        .order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
        .limit(limit)
    ).all()

    # Makale durum sayacı — TÜM makaleler üzerinden (gösterilen `limit` değil), böylece
    # 'çekildi ama analiz edilmedi' takılması bir bakışta görünür.
    def _count(*conds) -> int:
        return db.scalar(
            select(func.count()).select_from(Article).where(Article.entity_id == entity_id, *conds)
        ) or 0

    status = ArticleStatusOut(
        total=_count(),
        analyzed=_count(Article.analyzed.is_(True)),
        prefiltered=_count(Article.prefiltered.is_(True)),
        pending=_count(Article.analyzed.is_(False), Article.prefiltered.is_(False),
                       Article.expired.is_(False)),
        expired=_count(Article.analyzed.is_(False), Article.expired.is_(True)),
    )

    language = content_language(user, lang)
    return DashboardOut(
        entity=entity_card(db, entity, language),
        articles=[article_out(a) for a in articles],
        article_status=status,
        # Grafik aralıkları 7/30/90 gün/tümü: fiyat snapshot'ları tarama başına (günde birkaç
        # tane) olduğundan daha geniş pencere; frontend günlüğe indirir.
        risk_history=risk_history(db, entity_id, limit=90, language=language),
        price_history=price_history(db, entity_id, limit=400),
        analyst_history=analyst_history(db, entity_id) if entity.type == "ticker" else [],
    )
