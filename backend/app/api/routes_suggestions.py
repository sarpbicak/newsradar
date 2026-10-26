"""Öneri uçları: GET /suggestions + POST /suggestions/{id}/dismiss + /add.

Öneriler co-mentioned şirketlerden biriktirilir (bkz. analysis/pipeline.py).
Filtreleme (izleme listesinde olanları, dismissed'ları, az anılanları eleme)
burada, LİSTELEME anında yapılır.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sqlalchemy import exists

from .errors import ApiError
from ..db.database import get_db
from ..db.models import Entity, Suggestion, SuggestionDismissal, User
from ..entity_names import company_keys, display_name_for, entity_keys
from ..watchlist import add_to_watchlist, can_add_entity, in_watchlist, user_entity_ids
from .routes_auth import get_current_user
from .routes_entities import _add_lock, duplicate_response, find_watchlist_duplicate
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
def list_suggestions(
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> list[SuggestionOut]:
    """KİŞİSEL öneriler: yalnızca KULLANICININ listesindeki entity'lerin haberlerinden
    çıkan co-mention'lar; kullanıcının zaten takip ettikleri + kişisel kapatılanlar hariç.

    İZOLASYON: öneri ancak kaynak entity'lerinden (source_entity_ids) en az biri
    kullanıcının listesindeyse gösterilir; kaynak adları da kullanıcının entity'leriyle
    sınırlıdır (başka kullanıcının neyi takip ettiği sızmaz).
    """
    my_ids = user_entity_ids(db, user.id)
    if not my_ids:
        return []
    # Kullanıcının entity'lerinin isim+query'leri (zaten takip edilenleri elemek için)
    # ve kaynak adı gösterimi için yalnızca kendi entity'leri.
    my_terms: set[str] = set()
    my_keys: set[str] = set()  # şirket anahtarları: "SpaceX" önerisi SPCX takipçisine çıkmasın
    name_by_id: dict[int, str] = {}
    for e in db.scalars(select(Entity).where(Entity.id.in_(my_ids))).all():
        my_keys |= entity_keys(e)
        my_terms.add(e.name.strip().lower())
        my_terms.add(e.query.strip().lower())
        if e.display_name:
            my_terms.add(e.display_name.strip().lower())
        name_by_id[e.id] = e.display_name or e.name  # kaynak adı kısa haliyle gösterilir

    dismissed = set(db.scalars(
        select(SuggestionDismissal.suggestion_id).where(SuggestionDismissal.user_id == user.id)
    ).all())

    rows = db.scalars(
        select(Suggestion)
        .where(Suggestion.dismissed.is_(False), Suggestion.mention_count >= MIN_MENTIONS)
        .order_by(Suggestion.mention_count.desc(), Suggestion.last_seen_at.desc())
    ).all()

    out: list[SuggestionOut] = []
    for s in rows:
        if s.id in dismissed:
            continue
        # Kaynak, kullanıcının takip ettiği en az bir entity'yi içermeli (kişisel alaka).
        if not (set(s.source_entity_ids or []) & my_ids):
            continue
        if _in_watchlist(s, my_terms) or (company_keys(s.name) & my_keys):
            continue
        out.append(_suggestion_out(db, s, name_by_id))
        if len(out) >= MAX_RESULTS:
            break
    return out


@router.post("/{suggestion_id}/dismiss", status_code=204)
def dismiss_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    """Öneriyi YALNIZCA bu kullanıcı için kapatır (KİŞİSEL — başkasını etkilemez)."""
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise ApiError(code="suggestion_not_found", status_code=404, detail="Öneri bulunamadı.")
    already = db.scalar(select(exists().where(
        SuggestionDismissal.user_id == user.id,
        SuggestionDismissal.suggestion_id == suggestion_id,
    )))
    if not already:
        db.add(SuggestionDismissal(user_id=user.id, suggestion_id=suggestion_id))
    record_event(db, user.id, "dismiss_suggestion", {"name": sug.name})


def _dismiss_for_user(db: Session, user_id: int, suggestion_id: int) -> None:
    """Öneriyi bu kullanıcı için kapat (idempotent; global DEĞİL)."""
    already = db.scalar(select(exists().where(
        SuggestionDismissal.user_id == user_id,
        SuggestionDismissal.suggestion_id == suggestion_id,
    )))
    if not already:
        db.add(SuggestionDismissal(user_id=user_id, suggestion_id=suggestion_id))


@router.post("/{suggestion_id}/add", response_model=EntityCardOut, status_code=201)
def add_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> EntityCardOut:
    """Öneriyi KULLANICININ listesine ekler (havuz-farkında) ve öneriyi KİŞİSEL kapatır.

    Tip seçimi: ticker VAR ve is_public=True + ABD ise ticker; aksi halde keyword.
    Entity havuzda varsa yalnızca listeye eklenir (yeni analiz yok).
    """
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise ApiError(code="suggestion_not_found", status_code=404, detail="Öneri bulunamadı.")

    # Kota yarışına karşı: create_entity ile AYNI kilit + commit-kilit-içinde deseni
    # (öneriyle ekleme de kişi-başı entity limitini eşzamanlı isteklerle aşamasın).
    with _add_lock:
        ok, limit = can_add_entity(db, user)
        if not ok:
            raise ApiError(code="watchlist_limit", params={"limit": limit},
                status_code=403,
                detail=f"En fazla {limit} şirket takip edebilirsiniz. Yeni eklemek için birini çıkarın.",
            )

        # ABD borsası + halka açık + İngilizce kaynak ise ticker; aksi halde keyword
        # + kaynak dili (Türk/Avrupa şirketleri Finnhub'da çalışmaz → keyword).
        etype, query, language = resolve_add_target(sug)

        # Aynı şirket BAŞKA bir kayıtla listede zaten varsa (birebir değil) → 409, eklenmez.
        # (Birebir aynı kayıt listedeyse eski davranış: kart sessizce döner.)
        dup, exact = find_watchlist_duplicate(db, user.id, sug.name, etype, query)
        if dup is not None and not exact:
            return duplicate_response(dup, exact)

        _dismiss_for_user(db, user.id, suggestion_id)  # yalnızca bu kullanıcı için kaldır

        # Havuzda varsa: yalnızca kullanıcının listesine ekle (yeni entity/analiz yok).
        existing = db.scalar(
            select(Entity).where(Entity.type == etype, Entity.query == query)
        )
        if existing is not None:
            if not in_watchlist(db, user.id, existing.id):
                add_to_watchlist(db, user.id, existing.id)
            record_event(db, user.id, "add_suggestion", {"entity_id": existing.id, "name": existing.name})
            db.commit()
            return entity_card(db, existing, user.language)

        entity = Entity(name=sug.name.strip(), display_name=display_name_for(sug.name),
                        type=etype, query=query, language=language)
        db.add(entity)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(Entity).where(Entity.type == etype, Entity.query == query)
            )
            if existing is None:
                raise ApiError(code="entity_add_failed", status_code=409, detail="Entity eklenemedi.")
            _dismiss_for_user(db, user.id, suggestion_id)
            if not in_watchlist(db, user.id, existing.id):
                add_to_watchlist(db, user.id, existing.id)
            record_event(db, user.id, "add_suggestion", {"entity_id": existing.id, "name": existing.name})
            db.commit()
            return entity_card(db, existing, user.language)

        add_to_watchlist(db, user.id, entity.id)
        record_event(db, user.id, "add_suggestion", {"entity_id": entity.id, "name": entity.name})
        db.commit()
        return entity_card(db, entity, user.language)
