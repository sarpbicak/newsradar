"""Anonim (misafir) kayıt temizliği — günlük zamanlayıcı işi.

Kurallar (yalnızca is_anonymous=True; kayıtlı hesaplara ASLA dokunulmaz):
- listesinde hiç şirket olmayan ve 30 günden uzun süredir görülmemiş misafir → silinir;
- listesinde şirket olan misafir 90 gün görülmezse silinir.
"Görülme" = last_active_at (hiç yoksa created_at). Sınır günü dahil DEĞİL: tam 30 gün önce
görülen kalır, 30 günden eskisi silinir.

Paylaşılan analiz havuzuna dokunulmaz: yalnızca kullanıcı satırı ve ona bağlı kişisel satırlar
(liste bağlantıları, olaylar, öneri gizlemeleri, e-posta token'ları) silinir. Entity'ler
silinmez; başka kimsenin listesinde değilse pasifleşir (admin silmesiyle aynı yol).

İlk çalıştırma DENEMEDİR (dry-run): hiçbir şey silinmez, silinecek sayı kaydedilir ve loglanır
(admin panelde görünür). Sonraki çalıştırmalar gerçekten siler. NEWSRADAR_ANON_CLEANUP=off
işi kapatır, dry-run her çalıştırmayı deneme yapar.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .db.database import session_scope
from .db.models import (
    EmailToken, Feedback, MaintenanceRun, SuggestionDismissal, UsageEvent, User, UserWatchlist,
)
from .watchlist import recompute_active

logger = logging.getLogger("newsradar.cleanup")

JOB = "anon_cleanup"
IDLE_DAYS_EMPTY = 30        # şirket eklememiş misafir
IDLE_DAYS_WITH_LIST = 90    # listesinde şirket olan misafir


def purge_user(db: Session, user: User) -> None:
    """Kullanıcıyı ve kişisel satırlarını siler; entity'ler havuzda kalır (gerekirse pasif).
    SQLite FK cascade'e güvenilmez (foreign_keys pragma kapalı olabilir) → açıkça silinir."""
    uid = user.id
    entity_ids = list(db.scalars(select(UserWatchlist.entity_id).where(UserWatchlist.user_id == uid)).all())
    db.execute(delete(UserWatchlist).where(UserWatchlist.user_id == uid))
    db.execute(delete(SuggestionDismissal).where(SuggestionDismissal.user_id == uid))
    db.execute(delete(UsageEvent).where(UsageEvent.user_id == uid))
    db.execute(delete(EmailToken).where(EmailToken.user_id == uid))
    # Geri bildirim SİLİNMEZ (kıymetli) — yalnızca kimlik düşer.
    db.execute(update(Feedback).where(Feedback.user_id == uid).values(user_id=None))
    db.delete(user)
    db.flush()
    for eid in entity_ids:
        recompute_active(db, eid)


def candidates(db: Session, now: datetime | None = None) -> list[tuple[int, bool]]:
    """Silinecek misafirler: [(user_id, listesinde_şirket_var_mı)]."""
    now = now or datetime.now(timezone.utc)
    seen = func.coalesce(User.last_active_at, User.created_at)
    has_list = exists().where(UserWatchlist.user_id == User.id)
    rows = db.execute(
        select(User.id, has_list.label("has_list")).where(
            User.is_anonymous.is_(True), User.is_admin.is_(False),
            or_(
                (~has_list) & (seen < now - timedelta(days=IDLE_DAYS_EMPTY)),
                has_list & (seen < now - timedelta(days=IDLE_DAYS_WITH_LIST)),
            ),
        )
    ).all()
    return [(uid, bool(h)) for uid, h in rows]


def run(dry_run: bool | None = None, now: datetime | None = None) -> dict:
    """Temizliği çalıştırır, sonucu kaydeder ve döner. dry_run=None → ilk çalıştırma deneme,
    sonrakiler gerçek (NEWSRADAR_ANON_CLEANUP=dry-run ise hep deneme)."""
    mode = get_settings().anon_cleanup
    with session_scope() as db:
        if dry_run is None:
            first = db.scalar(select(MaintenanceRun.id).where(MaintenanceRun.job == JOB).limit(1)) is None
            dry_run = first or mode == "dry-run"
        found = candidates(db, now)
        empty = sum(1 for _, h in found if not h)
        details = {"without_companies": empty, "with_companies": len(found) - empty,
                   "anon_total": db.scalar(select(func.count()).select_from(User).where(User.is_anonymous.is_(True))) or 0}
        if not dry_run:
            for uid, _ in found:
                user = db.get(User, uid)
                if user is not None:
                    purge_user(db, user)
        db.add(MaintenanceRun(job=JOB, ran_at=now or datetime.now(timezone.utc), dry_run=dry_run,
                              deleted=len(found), details=details))
    verb = "silinecek (deneme, hiçbir şey silinmedi)" if dry_run else "silindi"
    logger.info("[anon-temizlik] %d misafir %s: şirketsiz %d (>%d gün), şirketli %d (>%d gün); toplam misafir %d",
                len(found), verb, details["without_companies"], IDLE_DAYS_EMPTY,
                details["with_companies"], IDLE_DAYS_WITH_LIST, details["anon_total"])
    return {"dry_run": dry_run, "deleted": len(found), **details}


def last_run(db: Session) -> dict | None:
    # Kayıt sırası (id): saat geri alınsa / testte sabit zaman verilse de en son çalışma doğru.
    r = db.scalar(select(MaintenanceRun).where(MaintenanceRun.job == JOB).order_by(MaintenanceRun.id.desc()).limit(1))
    if r is None:
        return None
    return {"ran_at": r.ran_at, "dry_run": r.dry_run, "deleted": r.deleted, **(r.details or {})}
