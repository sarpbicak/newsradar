"""'Nasıl çalışır?' anlatımı için GERÇEK örnek veri: GET /how-it-works (oturumlu) ve
GET /public/how-it-works (landing, oturumsuz — routes_public).

Uydurma veri yok — örnek şirketin son haber başlıkları, AI etiketleri (makale duygusu /
LLM'in elediği alakasızlar), haftalık makale sayısı, kaynaklar ve gerçek kartı DB'den gelir.

Gizlilik: örnek şirket YALNIZCA varsayılan (seed) listeden seçilir — bir kullanıcının kendi
eklediği (belki özel) şirket başkalarına gösterilmez. Öncelik NVIDIA; yoksa son 7 günde
kullanıcının dilinde analizi olan, fiyatı ve analist hedefi olan bir ticker.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Article, DiscardedArticle, Entity, EntityAnalysis, User
from ..seed import DEFAULT_WATCHLIST
from .routes_auth import get_current_user
from .schemas import HowItWorksOut, HowHeadlineOut
from .serializers import entity_card

router = APIRouter(tags=["how-it-works"])

PREFERRED = "NVDA"
FRESH_DAYS = 7
_PROVIDER_NAMES = {"finnhub": "Finnhub", "newsapi": "NewsAPI"}


def _label(sentiment: float | None) -> str:
    s = sentiment or 0.0
    return "positive" if s > 0.1 else "negative" if s < -0.1 else "neutral"


def _pick_entity(db: Session, language: str) -> Entity | None:
    queries = [q for _, _, q in DEFAULT_WATCHLIST]
    since = datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS)
    rows = db.execute(
        select(Entity, func.max(EntityAnalysis.created_at))
        .join(EntityAnalysis, EntityAnalysis.entity_id == Entity.id)
        .where(Entity.query.in_(queries), EntityAnalysis.language == language,
               EntityAnalysis.created_at >= since)
        .group_by(Entity.id)
    ).all()
    if not rows:
        return None
    # NVIDIA → ticker → en güncel analiz
    rows.sort(key=lambda r: (r[0].query != PREFERRED, r[0].type != "ticker", -(r[1].timestamp())))
    return rows[0][0]


@router.get("/how-it-works", response_model=HowItWorksOut)
def how_it_works(db: Session = Depends(get_db, scope="function"), user: User = Depends(get_current_user)) -> HowItWorksOut:
    return build_how_it_works(db, getattr(user, "language", "tr") or "tr")


def build_how_it_works(db: Session, lang: str) -> HowItWorksOut:
    """Kullanıcıdan bağımsız: yalnızca dil. Landing sayfası da (oturumsuz) bunu kullanır —
    örnek şirket seed listesinden seçildiği için kimsenin özel verisi görünmez."""
    entity = _pick_entity(db, lang)
    if entity is None:
        return HowItWorksOut(available=False)

    analyzed = db.scalars(
        select(Article)
        .where(Article.entity_id == entity.id, Article.analyzed.is_(True))
        .order_by(Article.published_at.desc().nullslast())
        .limit(30)
    ).all()
    # Görsel için gerçek çeşitlilik: en yeni olumlu + en yeni olumsuz + en yeni diğer,
    # ve LLM'in elediği en yeni alakasız makale (varsa).
    picked: list[Article] = []
    for want in ("positive", "negative"):
        a = next((x for x in analyzed if _label(x.sentiment) == want and x not in picked), None)
        if a:
            picked.append(a)
    for a in analyzed:
        if len(picked) >= 3:
            break
        if a not in picked:
            picked.append(a)
    heads = [
        HowHeadlineOut(title=a.title, source=a.source, label=_label(a.sentiment),
                       published_at=a.published_at)
        for a in picked
    ]
    junk = db.scalar(
        select(DiscardedArticle).where(DiscardedArticle.entity_id == entity.id)
        .order_by(DiscardedArticle.created_at.desc()).limit(1)
    )
    if junk:
        heads.append(HowHeadlineOut(title=junk.title, source=junk.source, label="irrelevant",
                                    published_at=junk.published_at))
    heads.sort(key=lambda h: h.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    week = datetime.now(timezone.utc) - timedelta(days=7)
    n_week = (db.scalar(select(func.count()).select_from(Article).where(
        Article.entity_id == entity.id, Article.fetched_at >= week)) or 0) + \
        (db.scalar(select(func.count()).select_from(DiscardedArticle).where(
            DiscardedArticle.entity_id == entity.id, DiscardedArticle.fetched_at >= week)) or 0)
    providers = sorted({
        _PROVIDER_NAMES.get((p or "").split(":")[0], p) for p in db.scalars(
            select(Article.provider).where(Article.entity_id == entity.id, Article.fetched_at >= week)
            .distinct()) if p
    })
    return HowItWorksOut(
        available=True,
        entity=entity_card(db, entity, lang),
        headlines=heads[:4],
        articles_week=n_week,
        providers=providers,
    )
