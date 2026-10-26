"""Oturum GEREKTİRMEYEN uçlar — landing sayfası (/) için.

Landing'e gelen ziyaretçinin henüz oturumu yoktur; burada anonim oturum açmak her ziyarette
bir kullanıcı üretir (MAX_USERS kotasını tüketir). Bu uçlar yalnızca TOPLAM sayılar ve seed
listesindeki örnek şirketi verir — kimsenin özel verisi (kendi eklediği şirket, kullanıcı
bilgisi) dönmez. Yanıtlar 5 dk önbelleklenebilir (CloudFront/tarayıcı).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import visits
from ..config import get_settings
from ..security import get_client_ip
from .routes_auth import get_current_user
from ..db.database import get_db
from ..db.models import Article, EntityAnalysis
from .routes_how import build_how_it_works
from .schemas import HowItWorksOut, PublicStatsOut
from ..languages import UI_LANGUAGES

router = APIRouter(prefix="/public", tags=["public"])

LANGUAGES = list(UI_LANGUAGES)   # arayüz + AI değerlendirmesi dilleri
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
def public_how_it_works(response: Response, lang: str = Query("en", pattern="^(tr|en|de)$"),
                        db: Session = Depends(get_db, scope="function")) -> HowItWorksOut:
    response.headers["Cache-Control"] = CACHE
    return build_how_it_works(db, lang)


@router.get("/features")
def public_features(response: Response) -> dict:
    """Arayüzün açıp kapattığı özellikler. email: doğrulama/şifre sıfırlama postaları gerçekten
    gidiyor mu — production'da console arka ucu (gönderim yok) iken "Şifremi unuttum" ve
    "E-postanı doğrula" gizlenir; yerelde console ile de açıktır (bağlantı log'da/stderr'de)."""
    s = get_settings()
    response.headers["Cache-Control"] = CACHE
    return {"email": s.email_backend == "ses" or s.trusted_proxy != "caddy"}


class PageViewIn(BaseModel):
    page: str = Field(max_length=10)                     # landing | app | detail
    referrer: str | None = Field(default=None, max_length=500)


@router.post("/pv", status_code=204)
def page_view(payload: PageViewIn, request: Request, authorization: str | None = Header(default=None),
              db: Session = Depends(get_db, scope="function")) -> Response:
    """Çerezsiz sayfa görüntüleme sayacı (app.visits). Oturum isteğe bağlı: admin token'ı ile
    gelen ziyaret sayılmaz. Ham IP/UA saklanmaz; yanıt her durumda 204 (içerik yok)."""
    is_admin = False
    if authorization:
        try:
            is_admin = get_current_user(authorization=authorization, db=db).is_admin
        except HTTPException:
            pass  # geçersiz/süresi dolmuş token → sıradan ziyaretçi
    visits.record_view(db, payload.page, payload.referrer, get_client_ip(request),
                       request.headers.get("user-agent", ""), is_admin=is_admin)
    return Response(status_code=204)
