"""İzleme listesi CRUD uçları: GET/POST/DELETE /entities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Entity
from .schemas import EntityCardOut, EntityCreate
from .serializers import entity_card

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=list[EntityCardOut])
def list_entities(db: Session = Depends(get_db)) -> list[EntityCardOut]:
    entities = db.scalars(select(Entity).order_by(Entity.created_at)).all()
    return [entity_card(db, e) for e in entities]


@router.post("", response_model=EntityCardOut, status_code=201)
def create_entity(payload: EntityCreate, db: Session = Depends(get_db)) -> EntityCardOut:
    entity = Entity(name=payload.name, type=payload.type, query=payload.query)
    db.add(entity)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu tip+query zaten izleme listesinde.")
    return entity_card(db, entity)


@router.delete("/{entity_id}", status_code=204)
def delete_entity(entity_id: int, db: Session = Depends(get_db)) -> None:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity bulunamadı.")
    db.delete(entity)
