"""Öneri uçları: GET /suggestions + POST /suggestions/{id}/dismiss + /add.

Öneriler co-mentioned şirketlerden biriktirilir (bkz. analysis/pipeline.py).
Filtreleme (izleme listesinde olanları, dismissed'ları, az anılanları eleme)
burada, LİSTELEME anında yapılır.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Entity, Suggestion, User
from .routes_auth import get_current_user
from .schemas import EntityCardOut, SuggestionOut
from .serializers import entity_card
from .usage import record_event

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

MIN_MENTIONS = 3   # bu sayının altındaki öneriler gösterilmez (gürültü filtresi)
MAX_RESULTS = 10

# ABD borsası sinyalleri (Finnhub ücretsiz katmanı yalnızca bunları kapsar).
_US_COUNTRIES = {"us", "usa", "united states", "u.s.", "u.s.a.", "america"}
_US_EXCHANGES = ("nasdaq", "nyse", "new york", "amex", "cboe", "bats")


def _is_us_listed(sug: Suggestion) -> bool:
    """Öneri ABD borsasında işlem gören halka açık bir şirket mi?

    Ticker yalnızca EMİN olunca seçilir: halka açık + ABD ülke/borsa sinyali +
    kaynak dili İngilizce + sembol mevcut. Aksi/belirsiz → keyword (güvenli).
    """
    if not sug.is_public or not sug.ticker:
        return False
    if (sug.source_language or "en") != "en":
        return False  # ABD-dışı dilden gelen mention → keyword
    country = (sug.country or "").strip().lower()
    exchange = (sug.exchange or "").strip().lower()
    us_country = country in _US_COUNTRIES
    us_exchange = any(x in exchange for x in _US_EXCHANGES)
    # ABD sinyali YOKSA (country/exchange boş ya da farklı) emin değiliz → keyword.
    return us_country or us_exchange


def resolve_add_target(sug: Suggestion) -> tuple[str, str, str]:
    """Bu öneri eklenirse (type, query, language) ne olacağını döndürür.

    add ucu ve liste gösterimi AYNI mantığı kullanır (sürpriz olmasın).
    """
    if _is_us_listed(sug):
        return "ticker", sug.ticker.strip().upper(), "en"
    return "keyword", sug.name.strip(), (sug.source_language or "en")


def _watchlist_terms(db: Session) -> set[str]:
    """İzleme listesindeki tüm isim ve query'lerin lowercase kümesi (eşleşme için)."""
    terms: set[str] = set()
    for name, query in db.execute(select(Entity.name, Entity.query)).all():
        terms.add(name.strip().lower())
        terms.add(query.strip().lower())
    return terms


def _in_watchlist(sug: Suggestion, terms: set[str]) -> bool:
    if sug.name.strip().lower() in terms:
        return True
    if sug.ticker and sug.ticker.strip().lower() in terms:
        return True
    return False


def _suggestion_out(db: Session, sug: Suggestion, name_by_id: dict[int, str]) -> SuggestionOut:
    names = [name_by_id[i] for i in (sug.source_entity_ids or []) if i in name_by_id]
    add_type, _query, add_lang = resolve_add_target(sug)
    return SuggestionOut(
        id=sug.id,
        name=sug.name,
        ticker=sug.ticker,
        is_public=sug.is_public,
        mention_count=sug.mention_count,
        why_relevant=sug.why_relevant,
        source_entity_names=names,
        last_seen_at=sug.last_seen_at,
        add_as_type=add_type,
        add_as_language=add_lang if add_type == "keyword" else None,
    )


@router.get("", response_model=list[SuggestionOut])
def list_suggestions(db: Session = Depends(get_db)) -> list[SuggestionOut]:
    """Filtrelenmiş öneriler: dismissed değil, ≥3 anılma, izleme listesinde yok."""
    terms = _watchlist_terms(db)
    name_by_id = {e.id: e.name for e in db.scalars(select(Entity)).all()}

    rows = db.scalars(
        select(Suggestion)
        .where(Suggestion.dismissed.is_(False), Suggestion.mention_count >= MIN_MENTIONS)
        .order_by(Suggestion.mention_count.desc(), Suggestion.last_seen_at.desc())
    ).all()

    out: list[SuggestionOut] = []
    for s in rows:
        if _in_watchlist(s, terms):
            continue
        out.append(_suggestion_out(db, s, name_by_id))
        if len(out) >= MAX_RESULTS:
            break
    return out


@router.post("/{suggestion_id}/dismiss", status_code=204)
def dismiss_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Öneri bulunamadı.")
    sug.dismissed = True
    record_event(db, user.id, "dismiss_suggestion", {"name": sug.name})


@router.post("/{suggestion_id}/add", response_model=EntityCardOut, status_code=201)
def add_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntityCardOut:
    """Öneriyi izleme listesine entity olarak ekler ve öneriyi dismiss eder.

    Tip seçimi: ticker VAR ve is_public=True ise ticker; aksi halde keyword.
    """
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Öneri bulunamadı.")

    # ABD borsası + halka açık + İngilizce kaynak ise ticker; aksi halde keyword
    # + kaynak dili (Türk/Avrupa şirketleri Finnhub'da çalışmaz → keyword).
    etype, query, language = resolve_add_target(sug)

    sug.dismissed = True  # her durumda öneriyi kaldır

    # Zaten varsa mevcut entity'yi döndür (çakışmayı tolere et).
    existing = db.scalar(
        select(Entity).where(Entity.type == etype, Entity.query == query)
    )
    if existing is not None:
        return entity_card(db, existing)

    entity = Entity(name=sug.name.strip(), type=etype, query=query, language=language)
    db.add(entity)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Yarış durumunda: dismiss'i tekrar uygula ve mevcut olanı döndür.
        again = db.get(Suggestion, suggestion_id)
        if again:
            again.dismissed = True
        existing = db.scalar(
            select(Entity).where(Entity.type == etype, Entity.query == query)
        )
        if existing is not None:
            return entity_card(db, existing)
        raise HTTPException(status_code=409, detail="Entity eklenemedi.")
    record_event(db, user.id, "add_suggestion", {"entity_id": entity.id, "name": entity.name})
    return entity_card(db, entity)
