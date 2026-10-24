"""Kişisel izleme listesi uçları: GET/POST/DELETE /entities.

İZOLASYON: tüm uçlar YALNIZCA giriş yapan kullanıcının watchlist'iyle çalışır.
entity'ler ortak havuzda; ekleme/çıkarma yalnızca kullanıcının kendi listesini
değiştirir (havuzdaki entity silinmez, başka kullanıcıları etkilemez).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Entity, User
from ..entity_names import company_keys, display_name_for, entity_keys
from ..watchlist import (
    add_to_watchlist,
    can_add_entity,
    in_watchlist,
    remove_from_watchlist,
    user_entity_ids,
)
from .routes_auth import get_current_user
from .schemas import EntityCardOut, EntityCreate
from .serializers import content_language, entity_card
from .usage import record_event

router = APIRouter(prefix="/entities", tags=["entities"])

# YARIŞ KORUMASI (register'daki _register_lock ile aynı gerekçe): kota sayımı +
# watchlist insert + commit ATOMİK değildi → eşzamanlı N ekleme kişi-başı entity
# limitini aşabiliyordu (test edildi: anon limit=3 iken 10 eşzamanlı istek → 10 satır).
# Kritik bölüm kilit altında ve commit KİLİT İÇİNDE yapılır ki sonraki thread taze
# (commit'lenmiş) sayıyı görsün. uvicorn tek-process çok-thread → threading.Lock yeter.
_add_lock = threading.Lock()


# Kademeli düzen (Katman 1): skoru ≥ bu eşik olan kartlar aday; en yüksek 3'ü "bugün önemli".
TIER1_MIN_SCORE = 2
TIER1_MAX_CARDS = 3
# Az şirket varken kademe uygulama: hepsini büyük kart yap (sayfa boş görünmesin).
FEW_ENTITIES_THRESHOLD = 4


def find_watchlist_duplicate(db: Session, user_id: int, name: str, type_: str,
                             query: str) -> tuple[Entity | None, bool]:
    """Kullanıcının listesinde bu şirketin ZATEN olup olmadığı: (entity, birebir_mi).

    Birebir = aynı (type, query). Değilse aynı şirketin başka kaydı (ticker "Space
    Exploration Technologies" ↔ keyword "SpaceX"): entity_names.company_keys kesişimi."""
    ids = user_entity_ids(db, user_id)
    if not ids:
        return None, False
    mine = db.scalars(select(Entity).where(Entity.id.in_(ids)).order_by(Entity.created_at)).all()
    for e in mine:
        if e.type == type_ and e.query == query:
            return e, True
    keys = company_keys(name, type_, query, display_name_for(name))
    for e in mine:
        if keys & entity_keys(e):
            return e, False
    return None, False


def duplicate_response(existing: Entity, exact: bool) -> JSONResponse:
    """409 — şirket zaten listede. `detail` düz metin kalır (mevcut arayüz onu gösterir);
    makine-okur alanlar: code ("already_in_watchlist" | "duplicate_entity") + duplicate_of."""
    label = existing.display_name or existing.name
    return JSONResponse(status_code=409, content={
        "detail": f"Bu şirket zaten listende: {label}",
        "code": "already_in_watchlist" if exact else "duplicate_entity",
        "duplicate_of": {
            "id": existing.id, "name": existing.name, "display_name": existing.display_name,
            "type": existing.type, "query": existing.query,
        },
    })


def _daily_new_entity_ok(db: Session, user: User) -> bool:
    """Sistem geneli GÜNLÜK yeni-entity ekleme sınırı (biri havuza 500 şirket ekleyip
    kotayı yakmasın). Admin muaf. Yalnızca YENİ entity oluşturmayı sınırlar; mevcut
    havuz entity'sini listeye eklemek serbest (yeni maliyet yok)."""
    cap = get_settings().daily_entity_add_cap
    if cap <= 0 or getattr(user, "is_admin", False):
        return True
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    n = db.scalar(
        select(func.count()).select_from(Entity).where(Entity.created_at >= since)
    ) or 0
    return n < cap


@router.get("", response_model=list[EntityCardOut])
def list_entities(
    lang: str | None = Query(None, description="AI içeriği dili (tr|en); yoksa kullanıcının dili"),
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> list[EntityCardOut]:
    """YALNIZCA kullanıcının izleme listesindeki entity'ler (ortak havuzdaki analizle)."""
    ids = user_entity_ids(db, user.id)
    if not ids:
        return []
    entities = db.scalars(
        select(Entity).where(Entity.id.in_(ids)).order_by(Entity.created_at)
    ).all()
    language = content_language(user, lang)
    cards = [entity_card(db, e, language) for e in entities]
    # AZ ŞİRKET (≤ eşik): kademe uygulama — hepsi büyük kart (tier=1). 1 şirket varken
    # "Bugün önemli" boş kalıp sayfa boş görünmesin. Liste büyüdükçe kademeye geçilir.
    if len(cards) <= FEW_ENTITIES_THRESHOLD:
        for c in cards:
            c.tier = 1
        return cards
    # FAZLA ŞİRKET: Katman 1 seçimi — skoru ≥ eşik olan en yüksek 3 aday tier=1 alır.
    # Eşitlikte en son güncellenen öne geçer. Kalanlar tier=2 (sıkışık liste).
    candidates = [c for c in cards if c.priority_score >= TIER1_MIN_SCORE]
    candidates.sort(
        key=lambda c: (c.priority_score, c.last_updated or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    for c in candidates[:TIER1_MAX_CARDS]:
        c.tier = 1
    return cards


@router.post("", response_model=EntityCardOut, status_code=201)
def create_entity(
    payload: EntityCreate,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> EntityCardOut:
    """Şirketi kullanıcının listesine ekler (HAVUZ-FARKINDA).

    - Entity havuzda VARSA (başkası eklemiş) → yalnızca watchlist'e satır ekle;
      yeni analiz YAPMA, mevcut analizi anında göster (bedava, hızlı).
    - YOKSA → yeni entity oluştur + listeye ekle; sıradaki yenilemede analiz edilir.
    """
    # KRİTİK BÖLÜM (yarış-güvenli): kota kontrolü + watchlist ekleme + commit tek kilit
    # altında; commit KİLİT İÇİNDE ki bir sonraki eşzamanlı ekleme taze sayıyı görsün.
    with _add_lock:
        # MÜKERRER: aynı şirket listede zaten varsa (birebir ya da başka kayıtla — ör.
        # SPCX ticker'ı varken "SpaceX" keyword'ü) ekleme YAPILMAZ, 409 + duplicate_of döner.
        # Mevcut mükerrerler silinmez/birleştirilmez; yalnızca yenisi engellenir.
        dup, exact = find_watchlist_duplicate(db, user.id, payload.name, payload.type, payload.query)
        if dup is not None:
            return duplicate_response(dup, exact)

        ok, limit = can_add_entity(db, user)
        if not ok:
            raise HTTPException(
                status_code=403,
                detail=f"En fazla {limit} şirket takip edebilirsiniz. Yeni eklemek için birini çıkarın.",
            )

        existing = db.scalar(
            select(Entity).where(Entity.type == payload.type, Entity.query == payload.query)
        )
        if existing is not None:
            add_to_watchlist(db, user.id, existing.id)
            record_event(db, user.id, "add_entity",
                         {"entity_id": existing.id, "name": existing.name, "pool_hit": True})
            db.commit()
            return entity_card(db, existing, user.language)

        # YENİ entity (havuzda yok) → sistem-geneli günlük ekleme sınırını uygula.
        if not _daily_new_entity_ok(db, user):
            raise HTTPException(
                status_code=429,
                detail="Bugün için yeni şirket ekleme sınırı doldu, yarın tekrar deneyin.",
            )

        entity = Entity(
            name=payload.name, display_name=display_name_for(payload.name),
            type=payload.type, query=payload.query, language=payload.language,
        )
        db.add(entity)
        try:
            db.flush()
        except IntegrityError:
            # Yarış: başka istek aynı entity'yi oluşturdu → mevcut olana ekle.
            db.rollback()
            existing = db.scalar(
                select(Entity).where(Entity.type == payload.type, Entity.query == payload.query)
            )
            if existing is None:
                raise HTTPException(status_code=409, detail="Şirket eklenemedi.")
            if not in_watchlist(db, user.id, existing.id):
                add_to_watchlist(db, user.id, existing.id)
            record_event(db, user.id, "add_entity", {"entity_id": existing.id, "name": existing.name})
            db.commit()
            return entity_card(db, existing, user.language)

        add_to_watchlist(db, user.id, entity.id)
        record_event(db, user.id, "add_entity", {"entity_id": entity.id, "name": entity.name})
        db.commit()
        return entity_card(db, entity, user.language)


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    """Şirketi YALNIZCA kullanıcının listesinden çıkarır (havuzdan silmez).

    entity başka kullanıcılarda varsa havuzda kalır; hiç kimsede yoksa pasif olur
    (recompute_active) — silinmez, veri başkası tekrar eklerse hazır durur.
    """
    if not remove_from_watchlist(db, user.id, entity_id):
        raise HTTPException(status_code=404, detail="Bu şirket izleme listenizde değil.")
    entity = db.get(Entity, entity_id)
    name = entity.name if entity else None
    record_event(db, user.id, "remove_entity", {"entity_id": entity_id, "name": name})
