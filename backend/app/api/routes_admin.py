"""Admin uçları: kullanım paneli. Yalnızca is_admin kullanıcılar (require_admin).

Veri ORTAK; bu uçlar yalnızca 'kim ne yaptı' özetini gösterir (usage_events).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import re
import unicodedata

from .errors import ApiError
from .. import visits
from ..anon_cleanup import last_run as anon_cleanup_last_run, purge_user
from ..db.database import get_db
from ..entity_names import display_name_for
from ..db.models import (
    Entity,
    Feedback,
    UsageEvent,
    User,
    UserWatchlist,
)
from .routes_auth import hash_password, require_admin
from .routes_feedback import device_from_user_agent
from .. import gdelt_breaker
from .schemas import (
    AdminEntityRow,
    DisplayNameIn,
    AdminEventOut,
    AdminFeedbackOut,
    AdminGdeltOut,
    AdminHealthOut,
    AdminStatsOut,
    AdminUserDetail,
    AdminUserRow,
    PasswordResetOut,
    UserOut,
)
from .usage import record_event

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _start_of_today() -> datetime:
    now = datetime.now(timezone.utc)
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
def list_users(db: Session = Depends(get_db, scope="function")) -> list[AdminUserRow]:
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
            id=u.id, username=u.username, email=u.email, is_admin=u.is_admin,
            created_at=u.created_at, last_login_at=u.last_login_at,
            login_count=_count(db, u.id, "login"),
            refresh_count=_count(db, u.id, "refresh"),
            total_events=_count(db, u.id),
            last_active_at=last_active,
        ))
    return rows


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def user_detail(user_id: int, db: Session = Depends(get_db, scope="function")) -> AdminUserDetail:
    """Tek kullanıcının detaylı kullanımı: eylem dökümü + en çok baktığı şirketler + son eylemler."""
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(code="user_not_found", status_code=404, detail="Kullanıcı bulunamadı.")

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
        select(Entity.name, Entity.display_name, Entity.type, Entity.query)
        .join(UserWatchlist, UserWatchlist.entity_id == Entity.id)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.added_at)
    ).all()
    watchlist = [{"name": n, "display_name": dn, "type": t, "query": q} for n, dn, t, q in wl_rows]

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


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    """Kullanıcıyı ve ona bağlı TÜM verileri siler (yalnızca admin).

    - Admin KENDİ hesabını silemez (403) — son admin kilitlenmesini önler.
    - Silinen veriler: watchlist satırları, usage_events, suggestion_dismissals, user.
    - Entity'ler: watchlist satırı silinince başka kullanıcıda yoksa PASİF olur
      (recompute_active), havuzda kalır (silinmez).
    - Silme, admin'in usage_events'ine 'delete_user' olarak kaydedilir (kim kimi sildi).
    SQLite FK cascade'e güvenmeyip bağlı satırları AÇIKÇA sileriz (foreign_keys pragma
    açık olmayabilir).
    """
    if user_id == admin.id:
        raise ApiError(code="cannot_delete_self", status_code=403, detail="Kendi hesabınızı silemezsiniz.")
    target = db.get(User, user_id)
    if target is None:
        raise ApiError(code="user_not_found", status_code=404, detail="Kullanıcı bulunamadı.")
    username = target.username

    # Bağlı kişisel satırlar açıkça silinir, entity'ler havuzda kalır (gerekirse pasif) —
    # misafir temizliğiyle aynı yol (app/anon_cleanup.purge_user).
    purge_user(db, target)

    # Kim kimi sildi — admin'in kaydına yaz (silinen kullanıcının olayları gitti).
    record_event(db, admin.id, "delete_user", {"deleted_id": user_id, "username": username})


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> PasswordResetOut:
    """Kullanıcının şifresini GEÇİCİ bir şifreyle sıfırlar (yalnızca admin).

    Geçici şifre üretilir, hash'lenip saklanır ve düz metni YALNIZCA bu yanıtta döner
    (admin kullanıcıya iletir). Şifre değiştiği için kullanıcının mevcut token'ları
    geçersizleşir (token imzası pwhash'e bağlı) → yeniden giriş gerekir. LOGLANMAZ.
    """
    target = db.get(User, user_id)
    if target is None:
        raise ApiError(code="user_not_found", status_code=404, detail="Kullanıcı bulunamadı.")
    temp = secrets.token_urlsafe(9)  # ~12 karakter, min 8 şartını karşılar
    target.password_hash = hash_password(temp)
    record_event(db, admin.id, "password_reset",
                 {"target_id": user_id, "username": target.username})
    return PasswordResetOut(username=target.username, temp_password=temp)


@router.get("/stats", response_model=AdminStatsOut)
def stats(db: Session = Depends(get_db, scope="function")) -> AdminStatsOut:
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
        select(Entity.name, Entity.display_name, Entity.type,
               func.count(UserWatchlist.user_id).label("followers"))
        .join(UserWatchlist, UserWatchlist.entity_id == Entity.id)
        .group_by(Entity.id)
        .order_by(func.count(UserWatchlist.user_id).desc())
        .limit(10)
    ).all()
    most_followed = [{"name": n, "display_name": dn, "type": t, "followers": f}
                     for n, dn, t, f in followed]
    total_entities = db.scalar(
        select(func.count(func.distinct(UserWatchlist.entity_id)))
    ) or 0

    from ..config import get_settings
    from datetime import timedelta

    from .. import budget as _budget
    from ..health import health_snapshot
    week_ago = _start_of_today() - timedelta(days=7)
    month_ago = _start_of_today() - timedelta(days=30)
    unread_feedback = db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.is_read.is_(False))
    ) or 0
    return AdminStatsOut(
        total_users=total_users,
        max_users=get_settings().max_users,
        active_today=active_today,
        refreshes_today=refreshes_today,
        top_entities=_top_entities(db, None, limit=8),
        most_followed=most_followed,
        total_entities=total_entities,
        tokens_today=_budget.daily_tokens_used(),
        tokens_week=_budget.tokens_since(week_ago),
        tokens_month=_budget.tokens_since(month_ago),
        cost_today_usd=round(_budget.daily_cost_usd(), 4),
        cost_week_usd=round(_budget.cost_since(week_ago), 4),
        cost_month_usd=round(_budget.cost_since(month_ago), 4),
        daily_budget_usd=get_settings().daily_budget_usd,
        budget_exceeded=_budget.is_budget_exceeded(),
        cache_hit_rate_7d=_budget.cache_hit_rate(week_ago),
        model_breakdown=_budget.usage_breakdown(month_ago),
        unread_feedback=unread_feedback,
        health=AdminHealthOut(**health_snapshot()),
        gdelt=AdminGdeltOut(**gdelt_breaker.snapshot()),
    )


@router.get("/feedback", response_model=list[AdminFeedbackOut])
def list_feedback(db: Session = Depends(get_db, scope="function")) -> list[AdminFeedbackOut]:
    """Tüm geri bildirimler — OKUNMAMIŞLAR önce, sonra en yeni üstte.

    Gönderen kullanıcı adı/anon durumu User join'iyle çözülür (silinmiş/anon → None).
    """
    rows = db.execute(
        select(Feedback, User.username, User.is_anonymous)
        .outerjoin(User, User.id == Feedback.user_id)
        .order_by(Feedback.is_read.asc(), Feedback.created_at.desc())
    ).all()
    out: list[AdminFeedbackOut] = []
    for fb, username, is_anon in rows:
        # Anon kullanıcı adı sentetik ("anon:...") — panelde gösterme, "anonim" say.
        anon = bool(is_anon) or (username or "").startswith("anon:")
        out.append(AdminFeedbackOut(
            id=fb.id,
            message=fb.message,
            contact=fb.contact,
            username=None if (anon or username is None) else username,
            is_anonymous=anon or username is None,
            device=device_from_user_agent(fb.user_agent),
            user_agent=fb.user_agent,
            is_read=fb.is_read,
            created_at=fb.created_at,
        ))
    return out


@router.delete("/feedback/{feedback_id}", status_code=204)
def delete_feedback(
    feedback_id: int,
    db: Session = Depends(get_db, scope="function"),
    admin: User = Depends(require_admin),
) -> None:
    """Bir geri bildirimi KALICI olarak siler (yalnızca admin; arayüz onay sorar).

    Gizlilik metni 'istenince silinir' der — talep gelince admin buradan siler. Denetim
    için admin'in usage_events'ine 'delete_feedback' yazılır; mesaj/iletişim içeriği
    kayda GEÇMEZ (yalnızca id)."""
    fb = db.get(Feedback, feedback_id)
    if fb is None:
        raise ApiError(code="feedback_not_found", status_code=404, detail="Geri bildirim bulunamadı.")
    db.delete(fb)
    record_event(db, admin.id, "delete_feedback", {"feedback_id": feedback_id})


@router.post("/feedback/{feedback_id}/read", status_code=204)
def mark_feedback_read(feedback_id: int, db: Session = Depends(get_db, scope="function")) -> None:
    """Bir geri bildirimi okundu işaretle (idempotent)."""
    fb = db.get(Feedback, feedback_id)
    if fb is None:
        raise ApiError(code="feedback_not_found", status_code=404, detail="Geri bildirim bulunamadı.")
    fb.is_read = True


@router.get("/visits")
def visit_stats(db: Session = Depends(get_db, scope="function")) -> dict:
    """Ziyaretler (son 30 gün, çerezsiz sayaç): günlük benzersiz ziyaretçi + görüntüleme,
    en çok gelen 5 kaynak, landing → uygulama geçiş oranı."""
    return visits.stats(db, days=30)


@router.get("/maintenance")
def maintenance(db: Session = Depends(get_db, scope="function")) -> dict:
    """Bakım işlerinin son çalışması (misafir temizliği: ne zaman, deneme mi, kaç kayıt)."""
    return {"anon_cleanup": anon_cleanup_last_run(db)}


DISPLAY_NAME_MAX = 60  # kart başlığına sığan makul üst sınır (kolon 200)


def _entity_row(e: Entity, followers: int) -> AdminEntityRow:
    return AdminEntityRow(id=e.id, name=e.name, display_name=e.display_name, auto_display_name=display_name_for(e.name),
                          type=e.type, query=e.query, followers=followers, active=e.active)


@router.get("/entities", response_model=list[AdminEntityRow])
def list_entities(db: Session = Depends(get_db, scope="function")) -> list[AdminEntityRow]:
    """Havuzdaki şirketler (en çok takip edilen önce) — görünen adı düzenlemek için."""
    followers = dict(db.execute(select(UserWatchlist.entity_id, func.count()).group_by(UserWatchlist.entity_id)).all())
    rows = [_entity_row(e, followers.get(e.id, 0)) for e in db.scalars(select(Entity))]
    return sorted(rows, key=lambda r: (-r.followers, (r.display_name or r.name).casefold()))


@router.patch("/entities/{entity_id}/display-name", response_model=AdminEntityRow)
def set_display_name(entity_id: int, payload: DisplayNameIn, admin: User = Depends(require_admin),
                     db: Session = Depends(get_db, scope="function")) -> AdminEntityRow:
    """Yalnızca görünen adı değiştirir (ham ad, sembol, analizler aynı kalır). Boş → otomatik ad
    (entity_names.display_name_for; o da yoksa None = ham ad gösterilir). Boşluklar sadeleşir;
    en fazla 60 karakter; kontrol karakteri yasak."""
    e = db.get(Entity, entity_id)
    if e is None:
        raise ApiError(code="company_not_found", status_code=404, detail="Şirket bulunamadı.")
    raw = re.sub(r"\s+", " ", (payload.display_name or "")).strip()
    if any(unicodedata.category(c).startswith("C") for c in raw):
        raise ApiError(code="display_name_control", status_code=422, detail="Görünen ad kontrol karakteri içeremez.")
    if len(raw) > DISPLAY_NAME_MAX:
        raise ApiError(code="display_name_too_long", params={"max": DISPLAY_NAME_MAX}, status_code=422, detail=f"Görünen ad en fazla {DISPLAY_NAME_MAX} karakter olabilir.")
    old = e.display_name
    e.display_name = raw or display_name_for(e.name)
    record_event(db, admin.id, "rename_entity", {"entity_id": e.id, "from": old, "to": e.display_name, "auto": not raw})
    db.flush()
    followers = db.scalar(select(func.count()).select_from(UserWatchlist).where(UserWatchlist.entity_id == e.id)) or 0
    return _entity_row(e, followers)
