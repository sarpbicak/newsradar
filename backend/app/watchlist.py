"""Kişisel izleme listesi servisi — entity ORTAK havuz, "kim takip ediyor" kişisel.

Tüm route'lar bu yardımcıları kullanır; böylece izolasyon ve `entity.active`
bakımı tek yerde toplanır (kopyala-yapıştır tutarsızlığı olmaz).

İZOLASYON: bir kullanıcının listesi/görünümü BAŞKA kullanıcıya sızmamalı — buradaki
sorgular daima user_id ile filtrelenir.
"""

from __future__ import annotations

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from .db.models import Entity, User, UserWatchlist


def user_entity_ids(db: Session, user_id: int) -> set[int]:
    """Kullanıcının izleme listesindeki entity id kümesi."""
    rows = db.scalars(
        select(UserWatchlist.entity_id).where(UserWatchlist.user_id == user_id)
    ).all()
    return set(rows)


def in_watchlist(db: Session, user_id: int, entity_id: int) -> bool:
    """entity kullanıcının listesinde mi (detay erişim izni için)."""
    return db.scalar(
        select(
            exists().where(
                UserWatchlist.user_id == user_id,
                UserWatchlist.entity_id == entity_id,
            )
        )
    ) or False


def watchlist_count(db: Session, user_id: int) -> int:
    """Kullanıcının listesindeki entity sayısı (kota kontrolü için)."""
    return db.scalar(
        select(func.count()).select_from(UserWatchlist).where(UserWatchlist.user_id == user_id)
    ) or 0


def can_add_entity(db: Session, user) -> tuple[bool, int]:
    """Kullanıcı yeni entity ekleyebilir mi? Admin limitsiz. (uygun_mu, limit) döner."""
    from .config import get_settings

    limit = get_settings().max_entities_per_user
    if getattr(user, "is_admin", False) or limit <= 0:
        return True, limit
    return watchlist_count(db, user.id) < limit, limit


def _entity_in_any_watchlist(db: Session, entity_id: int) -> bool:
    return db.scalar(
        select(exists().where(UserWatchlist.entity_id == entity_id))
    ) or False


def recompute_active(db: Session, entity_id: int) -> None:
    """entity, en az bir kullanıcının listesindeyse aktif; hiçbirinde değilse pasif.

    Pasif entity SİLİNMEZ (veri havuzda kalır); yalnızca yenileme/analiz onu atlar.
    """
    entity = db.get(Entity, entity_id)
    if entity is None:
        return
    active = _entity_in_any_watchlist(db, entity_id)
    if entity.active != active:
        entity.active = active


def add_to_watchlist(db: Session, user_id: int, entity_id: int) -> bool:
    """Kullanıcının listesine entity ekler (idempotent). entity'yi aktifleştirir.

    Zaten varsa False, yeni eklendiyse True döner.
    """
    if in_watchlist(db, user_id, entity_id):
        return False
    db.add(UserWatchlist(user_id=user_id, entity_id=entity_id))
    entity = db.get(Entity, entity_id)
    if entity is not None and not entity.active:
        entity.active = True
    db.flush()
    return True


def remove_from_watchlist(db: Session, user_id: int, entity_id: int) -> bool:
    """Kullanıcının listesinden entity'yi çıkarır. Başka kimsede yoksa entity pasif olur.

    Satır varsa True, yoksa False döner. entity SİLİNMEZ.
    """
    result = db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == user_id,
            UserWatchlist.entity_id == entity_id,
        )
    )
    if result.rowcount == 0:
        return False
    db.flush()
    recompute_active(db, entity_id)
    return True


def backfill_watchlist_to_admin(db: Session) -> int:
    """BİR KEZLİK migration: mevcut ORTAK listeyi admin'e devreder.

    Koşullar (hepsi gerekli): user_watchlist boş + en az bir AKTİF entity var +
    bir admin kullanıcı var. Böylece pre-watchlist DB'sindeki tüm entity'ler
    (Tesla, NVIDIA, …) admin'in listesine geçer; yeni kullanıcılar boş başlar.

    Güvenli/idempotent: watchlist doluysa hiç çalışmaz. Ayrıca yalnızca AKTİF
    entity'leri taşır — sonradan herkes listesini boşaltıp entity'ler pasifleşse
    bile (bkz. recompute_active) tekrar tetiklenmez (taşınacak aktif entity kalmaz).
    Döndürülen: admin'e eklenen entity sayısı.
    """
    already = db.scalar(select(func.count()).select_from(UserWatchlist)) or 0
    if already:
        return 0
    entity_ids = db.scalars(select(Entity.id).where(Entity.active.is_(True))).all()
    if not entity_ids:
        return 0
    admin = db.scalar(
        select(User).where(User.is_admin.is_(True)).order_by(User.created_at).limit(1)
    )
    if admin is None:
        return 0
    for eid in entity_ids:
        db.add(UserWatchlist(user_id=admin.id, entity_id=eid))
    db.flush()
    return len(entity_ids)
