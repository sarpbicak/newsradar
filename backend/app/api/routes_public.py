"""Oturum GEREKTİRMEYEN uçlar — landing sayfası (/) için.

Landing'e gelen ziyaretçinin henüz oturumu yoktur; burada anonim oturum açmak her ziyarette
bir kullanıcı üretir (MAX_USERS kotasını tüketir). Bu uçlar yalnızca TOPLAM sayılar ve seed
listesindeki örnek şirketi verir — kimsenin özel verisi (kendi eklediği şirket, kullanıcı
bilgisi) dönmez. Yanıtlar 5 dk önbelleklenebilir (CloudFront/tarayıcı).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Article, EntityAnalysis
from .routes_how import build_how_it_works
from .schemas import HowItWorksOut, PublicStatsOut

router = APIRouter(prefix="/public", tags=["public"])

LANGUAGES = ["tr", "en"]   # arayüz + AI değerlendirmesi dilleri
CACHE = "public, max-age=300"


@router.get("/stats", response_model=PublicStatsOut)
def public_stats(response: Response, db: Session = Depends(get_db, scope="function")) -> PublicStatsOut:
    """Gerçek toplamlar (uydurma/şişirme yok): AI'ın analiz ettiği haber, üretilen AI
    değerlendirmesi (entity_analyses), haberlerdeki farklı kaynak sayısı, desteklenen diller."""
    analyzed = db.scalar(select(func.count()).select_from(Article).where(Article.analyzed.is_(True))) or 0
    assessments = db.scalar(select(func.count()).select_from(EntityAnalysis)) or 0
    sources = db.scalar(
        select(func.count(func.distinct(func.lower(func.trim(Article.source))))).where(func.trim(Article.source) != "")
    ) or 0
    response.headers["Cache-Control"] = CACHE
    return PublicStatsOut(articles_analyzed=analyzed, assessments=assessments, news_sources=sources, languages=LANGUAGES)


@router.get("/how-it-works", response_model=HowItWorksOut)
def public_how_it_works(response: Response, lang: str = Query("en", pattern="^(tr|en)$"),
                        db: Session = Depends(get_db, scope="function")) -> HowItWorksOut:
    response.headers["Cache-Control"] = CACHE
    return build_how_it_works(db, lang)
