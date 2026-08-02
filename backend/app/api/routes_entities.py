"""Kişisel izleme listesi uçları: GET/POST/DELETE /entities.

İZOLASYON: tüm uçlar YALNIZCA giriş yapan kullanıcının watchlist'iyle çalışır.
entity'ler ortak havuzda; ekleme/çıkarma yalnızca kullanıcının kendi listesini
değiştirir (havuzdaki entity silinmez, başka kullanıcıları etkilemez).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Entity, User
from ..watchlist import (
    add_to_watchlist,
    can_add_entity,
    in_watchlist,
    remove_from_watchlist,
    user_entity_ids,
)
from .routes_auth import get_current_user
from .schemas import EntityCardOut, EntityCreate
from .serializers import entity_card
from .usage import record_event

router = APIRouter(prefix="/entities", tags=["entities"])


# Kademeli düzen (Katman 1): skoru ≥ bu eşik olan kartlar aday; en yüksek 3'ü "bugün önemli".
TIER1_MIN_SCORE = 2
TIER1_MAX_CARDS = 3
# Az şirket varken kademe uygulama: hepsini büyük kart yap (sayfa boş görünmesin).
FEW_ENTITIES_THRESHOLD = 4


@router.get("", response_model=list[EntityCardOut])
def list_entities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EntityCardOut]:
    """YALNIZCA kullanıcının izleme listesindeki entity'ler (ortak havuzdaki analizle)."""
    ids = user_entity_ids(db, user.id)
    if not ids:
        return []
    entities = db.scalars(
        select(Entity).where(Entity.id.in_(ids)).order_by(Entity.created_at)
    ).all()
    cards = [entity_card(db, e) for e in entities]
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
        key=lambda c: (c.priority_score, c.last_updated or datetime.min),
        reverse=True,
    )
    for c in candidates[:TIER1_MAX_CARDS]:
        c.tier = 1
    return cards


@router.post("", response_model=EntityCardOut, status_code=201)
def create_entity(
    payload: EntityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntityCardOut:
    """Şirketi kullanıcının listesine ekler (HAVUZ-FARKINDA).

    - Entity havuzda VARSA (başkası eklemiş) → yalnızca watchlist'e satır ekle;
      yeni analiz YAPMA, mevcut analizi anında göster (bedava, hızlı).
    - YOKSA → yeni entity oluştur + listeye ekle; sıradaki yenilemede analiz edilir.
    """
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
        if in_watchlist(db, user.id, existing.id):
            raise HTTPException(status_code=409, detail="Bu şirket zaten izleme listenizde.")
        add_to_watchlist(db, user.id, existing.id)
        record_event(db, user.id, "add_entity",
                     {"entity_id": existing.id, "name": existing.name, "pool_hit": True})
        return entity_card(db, existing)

    entity = Entity(
        name=payload.name, type=payload.type, query=payload.query, language=payload.language
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
        return entity_card(db, existing)

    add_to_watchlist(db, user.id, entity.id)
    record_event(db, user.id, "add_entity", {"entity_id": entity.id, "name": entity.name})
    return entity_card(db, entity)


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
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
