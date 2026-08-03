"""Admin uçları: kullanım paneli. Yalnızca is_admin kullanıcılar (require_admin).

Veri ORTAK; bu uçlar yalnızca 'kim ne yaptı' özetini gösterir (usage_events).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Entity, UsageEvent, User, UserWatchlist
from .routes_auth import require_admin
from .schemas import (
    AdminEventOut,
    AdminStatsOut,
    AdminUserDetail,
    AdminUserRow,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _start_of_today() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _count(db: Session, user_id: int, event_type: str | None = None) -> int:
    q = select(func.count()).select_from(UsageEvent).where(UsageEvent.user_id == user_id)
    if event_type:
        q = q.where(UsageEvent.event_type == event_type)
    return db.scalar(q) or 0


def _entity_name(ev_detail) -> str | None:
    if isinstance(ev_detail, dict):
        return ev_detail.get("name") or (
            f"#{ev_detail['entity_id']}" if ev_detail.get("entity_id") else None
        )
    return None


def _top_entities(db: Session, user_id: int | None = None, limit: int = 5) -> list[dict]:
    """En çok view_entity alan şirketler (detail.name'e göre). user_id verilirse o kullanıcı."""
    q = select(UsageEvent.detail).where(UsageEvent.event_type == "view_entity")
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    counts: dict[str, int] = {}
    for (detail,) in db.execute(q).all():
        name = _entity_name(detail)
        if name:
            counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"name": n, "count": c} for n, c in ranked]


@router.get("/users", response_model=list[AdminUserRow])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserRow]:
    """Kullanıcı listesi + özet sayaçlar (giriş/yenileme/toplam) + son aktiflik."""
    users = db.scalars(select(User).order_by(User.created_at)).all()
    rows: list[AdminUserRow] = []
    for u in users:
        # Son aktiflik: artık her istekte tazelenen kolon birincil kaynak; kolon henüz
        # dolmamışsa (migration öncesi eski kayıt) event geçmişinin en yenisine düş.
        last_active = u.last_active_at or db.scalar(
            select(func.max(UsageEvent.created_at)).where(UsageEvent.user_id == u.id)
        )
        rows.append(AdminUserRow(
            id=u.id, username=u.username, is_admin=u.is_admin,
            created_at=u.created_at, last_login_at=u.last_login_at,
            login_count=_count(db, u.id, "login"),
            refresh_count=_count(db, u.id, "refresh"),
            total_events=_count(db, u.id),
            last_active_at=last_active,
        ))
    return rows


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def user_detail(user_id: int, db: Session = Depends(get_db)) -> AdminUserDetail:
    """Tek kullanıcının detaylı kullanımı: eylem dökümü + en çok baktığı şirketler + son eylemler."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    # Eylem tipine göre adet.
    rows = db.execute(
        select(UsageEvent.event_type, func.count())
        .where(UsageEvent.user_id == user_id)
        .group_by(UsageEvent.event_type)
    ).all()
    event_counts = {et: c for et, c in rows}

    recent = db.scalars(
        select(UsageEvent)
        .where(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.created_at.desc())
        .limit(40)
    ).all()

    # Kullanıcının izleme listesi (kim neyi takip ediyor).
    wl_rows = db.execute(
        select(Entity.name, Entity.type, Entity.query)
        .join(UserWatchlist, UserWatchlist.entity_id == Entity.id)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.added_at)
    ).all()
    watchlist = [{"name": n, "type": t, "query": q} for n, t, q in wl_rows]

    return AdminUserDetail(
        user=UserOut(
            id=user.id, username=user.username, is_admin=user.is_admin,
            created_at=user.created_at, last_login_at=user.last_login_at,
            guide_dismissed=user.guide_dismissed, tutorial_done=user.tutorial_done,
        ),
        event_counts=event_counts,
        top_entities=_top_entities(db, user_id),
        recent_events=[
            AdminEventOut(event_type=e.event_type, detail=e.detail, created_at=e.created_at)
            for e in recent
        ],
        watchlist=watchlist,
        watchlist_size=len(watchlist),
    )


@router.get("/stats", response_model=AdminStatsOut)
def stats(db: Session = Depends(get_db)) -> AdminStatsOut:
    """Genel istatistikler: toplam kullanıcı, bugün aktif, bugünkü yenileme, popüler şirketler."""
    today = _start_of_today()
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_today = db.scalar(
        select(func.count(func.distinct(UsageEvent.user_id)))
        .where(UsageEvent.created_at >= today)
    ) or 0
    refreshes_today = db.scalar(
        select(func.count()).select_from(UsageEvent)
        .where(UsageEvent.event_type == "refresh", UsageEvent.created_at >= today)
    ) or 0

    # En çok takip edilen şirketler (kaç kullanıcının watchlist'inde) + toplam benzersiz.
    followed = db.execute(
        select(Entity.name, Entity.type, func.count(UserWatchlist.user_id).label("followers"))
        .join(UserWatchlist, UserWatchlist.entity_id == Entity.id)
        .group_by(Entity.id)
        .order_by(func.count(UserWatchlist.user_id).desc())
        .limit(10)
    ).all()
    most_followed = [{"name": n, "type": t, "followers": f} for n, t, f in followed]
    total_entities = db.scalar(
        select(func.count(func.distinct(UserWatchlist.entity_id)))
    ) or 0

    return AdminStatsOut(
        total_users=total_users,
        active_today=active_today,
        refreshes_today=refreshes_today,
        top_entities=_top_entities(db, None, limit=8),
        most_followed=most_followed,
        total_entities=total_entities,
    )
