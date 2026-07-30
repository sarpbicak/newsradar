"""İzleme listesi CRUD uçları: GET/POST/DELETE /entities."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Entity, User
from .routes_auth import get_current_user
from .schemas import EntityCardOut, EntityCreate
from .serializers import entity_card
from .usage import record_event

router = APIRouter(prefix="/entities", tags=["entities"])


# Kademeli düzen (Katman 1): skoru ≥ bu eşik olan kartlar aday; en yüksek 3'ü "bugün önemli".
TIER1_MIN_SCORE = 2
TIER1_MAX_CARDS = 3


@router.get("", response_model=list[EntityCardOut])
def list_entities(db: Session = Depends(get_db)) -> list[EntityCardOut]:
    entities = db.scalars(select(Entity).order_by(Entity.created_at)).all()
    cards = [entity_card(db, e) for e in entities]
    # Katman 1 seçimi global: tüm kartlar kurulduktan sonra en yüksek skorlu 3 aday
    # (skor ≥ eşik) tier=1 alır. Eşitlikte en son güncellenen öne geçer.
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
    entity = Entity(
        name=payload.name, type=payload.type, query=payload.query, language=payload.language
    )
    db.add(entity)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu tip+query zaten izleme listesinde.")
    record_event(db, user.id, "add_entity", {"entity_id": entity.id, "name": entity.name})
    return entity_card(db, entity)


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity bulunamadı.")
    record_event(db, user.id, "remove_entity", {"entity_id": entity.id, "name": entity.name})
    db.delete(entity)
