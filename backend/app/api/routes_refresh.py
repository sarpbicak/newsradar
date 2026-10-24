"""Yenileme uçları: POST /refresh (kuyruğa al) + DELETE /refresh (sıradakini iptal) +
GET /status (süreç + kuyruk durumu dahil)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import scheduler
from ..config import get_settings
from ..db.database import get_db
from ..db.models import UsageEvent, User
from ..providers import provider_status
from ..quota import newsapi_usage
from .. import refresh_queue
from ..refresh import get_user_result
from ..watchlist import user_entity_ids
from .routes_auth import get_current_user
from .schemas import NewsApiQuotaOut, ProviderStatusOut, RefreshAck

router = APIRouter(tags=["refresh"])


def _refresh_window(db: Session, user: User):
    """Son 24 saatteki elle yenileme olayları (rolling pencere) için sorgu koşulları."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        UsageEvent.user_id == user.id,
        UsageEvent.event_type == "refresh",
        UsageEvent.created_at >= since,
    )


def _refresh_quota(db: Session, user: User) -> tuple[bool, int, int]:
    """Kullanıcının elle yenileme kotası (rolling 24s). Admin muaf.

    (uygun_mu, limit, kullanılan) döner. limit=0 → sınırsız.
    """
    limit = get_settings().refresh_limit_for(user)
    if limit <= 0:  # 0 = sınırsız (admin)
        return True, limit, 0
    used = db.scalar(select(func.count()).select_from(UsageEvent).where(*_refresh_window(db, user))) or 0
    return used < limit, limit, used


def _refresh_resets_at(db: Session, user: User, limit: int, used: int) -> datetime | None:
    """Hak dolduysa bir hakkın geri geleceği an: penceredeki en eski yenileme + 24 saat."""
    if limit <= 0 or used < limit:
        return None
    oldest = db.scalar(select(func.min(UsageEvent.created_at)).where(*_refresh_window(db, user)))
    if oldest is None:
        return None
    if oldest.tzinfo is None:  # SQLite naive datetime döndürür (UTC yazılır)
        oldest = oldest.replace(tzinfo=timezone.utc)
    return oldest + timedelta(hours=24)


# Kuyruk onay mesajları (Türkçe, kısa; uzun tire yok).
_MSG_STARTED = "Yenileme başlatıldı."
_MSG_RUNNING = "Yenilemeniz zaten çalışıyor."
_MSG_EMPTY = "İzleme listeniz boş, önce bir şirket ekleyin."
_MSG_QUEUE_FULL = "Yenileme sırası şu an dolu, birkaç dakika sonra tekrar deneyin."
_MSG_BUDGET = "Günlük analiz bütçesi doldu, yenileme şu an başlatılamıyor. Yarın tekrar deneyin."


def _msg_queued(pos: int | None, already: bool) -> str:
    head = "Yenilemeniz zaten sırada" if already else "Yenilemeniz sıraya alındı"
    return f"{head}: sıranız {pos}." if pos else f"{head}."


def _ack_existing(view: dict) -> RefreshAck | None:
    """Kullanıcının etkin (çalışan/sıradaki) işi varsa onun durumunu döner (yeni iş yok)."""
    if view["running"]:
        return RefreshAck(accepted=True, started=False, queued=False, is_running=True,
                          reason="running", message=_MSG_RUNNING)
    if view["queued"]:
        return RefreshAck(accepted=True, started=False, queued=True,
                          queue_position=view["queue_position"], is_running=False,
                          reason="queued", message=_msg_queued(view["queue_position"], True))
    return None


@router.post("/refresh", response_model=RefreshAck)
def refresh(
    hours: int | None = Query(None, description="Geriye dönük pencere (saat)"),
    scheduler_enabled: bool | None = Query(
        None, description="Saatlik otomatik yenilemeyi aç/kapat"
    ),
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> RefreshAck:
    """Yenilemeyi KUYRUĞA alır ve hemen döner (tarama 1-2 dk sürebilir).

    Sıra boşsa iş hemen başlar (started=true); değilse sıraya girer (queued=true,
    queue_position). Frontend /status'u yoklayarak takip eder. Kullanıcı başı en fazla 1
    etkin iş: ikinci istek mevcut işin durumunu döner. Hak (UsageEvent) sıraya girerken
    DEĞİL, iş gerçekten başlarken düşülür (kuyruk işçisi); zamanlayıcı işi kaydedilmez.
    """
    if scheduler_enabled is not None:
        scheduler.set_enabled(scheduler_enabled)

    # KİŞİSEL elle yenileme: yalnızca kullanıcının KENDİ listesindeki entity'leri işle
    # (ortak havuzun tamamını değil — ilerleme "1/1" doğru olsun, kota adil olsun).
    # Havuzun geri kalanını scheduler zaten 6 saatte bir tazeliyor.
    my_ids = user_entity_ids(db, user.id)
    if not my_ids:
        return RefreshAck(accepted=False, started=False, is_running=False,
                          reason="empty", message=_MSG_EMPTY)

    # Zaten etkin işi varsa (çalışan/sıradaki) onu döndür: kota ve bütçe kontrolünden ÖNCE,
    # yoksa hakkı az kullanıcı kendi çalışan işi için 429 görürdü.
    existing = _ack_existing(refresh_queue.snapshot(user.id))
    if existing:
        return existing

    # Kişi başı günlük elle yenileme kotası (admin muaf). Hak dolduysa sıraya bile girmez.
    ok, limit, used = _refresh_quota(db, user)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(f"Günlük yenileme limitine ulaştınız ({used}/{limit}). "
                    "Otomatik güncelleme arka planda 6 saatte bir çalışıyor."),
        )

    from .. import budget
    if budget.is_budget_exceeded():
        return RefreshAck(accepted=False, started=False, is_running=False,
                          reason="budget", message=_MSG_BUDGET)

    outcome, view = refresh_queue.enqueue_user(user.id, my_ids, hours)
    if outcome == "started":
        return RefreshAck(accepted=True, started=True, queued=False, is_running=True,
                          message=_MSG_STARTED)
    if outcome == "queued":
        return RefreshAck(accepted=True, started=False, queued=True,
                          queue_position=view["queue_position"], is_running=False,
                          message=_msg_queued(view["queue_position"], False))
    if outcome == "queue_full":
        return RefreshAck(accepted=False, started=False, is_running=False,
                          reason="queue_full", message=_MSG_QUEUE_FULL)
    # running / already_queued: snapshot ile enqueue arasında (aynı kullanıcının eşzamanlı
    # isteği) iş eklendi → mevcut işi döndür.
    if outcome == "already_queued":
        return RefreshAck(accepted=True, started=False, queued=True,
                          queue_position=view["queue_position"], is_running=False,
                          reason="queued", message=_msg_queued(view["queue_position"], True))
    return RefreshAck(accepted=True, started=False, queued=False, is_running=True,
                      reason="running", message=_MSG_RUNNING)


@router.delete("/refresh", status_code=204)
def cancel_refresh(user: User = Depends(get_current_user)) -> Response:
    """Kullanıcının SIRADAKİ yenilemesini iptal eder (hak henüz düşülmemişti).

    204: iptal edildi · 409: işi zaten çalışıyor (durdurulamaz) · 404: etkin işi yok."""
    outcome = refresh_queue.cancel_user(user.id)
    if outcome == "running":
        raise HTTPException(status_code=409, detail="Yenilemeniz zaten çalışıyor, iptal edilemez.")
    if outcome == "none":
        raise HTTPException(status_code=404, detail="Sırada bekleyen bir yenilemeniz yok.")
    return Response(status_code=204)


@router.get("/status", response_model=ProviderStatusOut)
def status(
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(get_current_user),
) -> ProviderStatusOut:
    """Sağlayıcı/LLM/zamanlayıcı + yenileme süreci + NewsAPI kotası + KİŞİSEL yenileme kotası."""
    view = refresh_queue.snapshot(user.id)  # süreç + kuyruk, tek kilit altında (boşluk yok)
    st = view["state"]
    settings = get_settings()
    quota = None
    if settings.newsapi_available:
        quota = NewsApiQuotaOut(**newsapi_usage(db))
    _ok, r_limit, r_used = _refresh_quota(db, user)

    # KİŞİSEL durum: is_running/ilerleme/son özet YALNIZCA bu kullanıcının başlattığı
    # taramaya aittir. Başka kullanıcının (ya da scheduler'ın user_id=None) taraması
    # bu kullanıcıya "çalışıyor" ya da yabancı uyarılar olarak sızmaz (izolasyon).
    # Son sonuç kullanıcı başı tutulur: başkasının işi bitince kendi sonucu ezilmez.
    mine_running = view["running"]
    last = get_user_result(user.id)
    if last is None and st["last_user_id"] == user.id:
        # Geriye uyum: kişisel sonuç kaydı yoksa genel son tarama bu kullanıcınınsa onu göster.
        last = {"status": "done", "summary": st["last_summary"],
                "finished_at": st["last_completed_at"], "message": None}
    last = last or {}
    fresh_data = last.get("status") in ("done", "merged")

    from .. import budget
    from ..watchlist import watchlist_count
    return ProviderStatusOut(
        providers=provider_status(),
        claude=settings.llm_available,  # "claude" alan adı geriye uyum; aktif LLM'i yansıtır
        scheduler_enabled=scheduler.is_enabled(),
        newsapi_quota=quota,
        is_running=mine_running,
        progress_done=st["progress_done"] if mine_running else 0,
        progress_total=st["progress_total"] if mine_running else 0,
        current_entity=st["current_entity"] if mine_running else None,
        step=st["step"] if mine_running else None,
        step_entity=st["step_entity"] if mine_running else None,
        step_count=st["step_count"] if mine_running else None,
        progress_fraction=st["progress_fraction"] if mine_running else 0.0,
        skipped_entity=st["skipped_entity"] if mine_running else None,
        last_completed_at=last.get("finished_at") if fresh_data else None,
        last_summary=last.get("summary") if last.get("status") == "done" else None,
        last_result_status=last.get("status"),
        last_result_message=last.get("message"),
        last_result_at=last.get("finished_at"),
        queued=view["queued"],
        queue_position=view["queue_position"],
        queue_length=view["queue_length"],
        refresh_limit=r_limit,
        refresh_used=r_used,
        refresh_is_admin=user.is_admin,
        # Arayüzdeki açıklama metni için iki ayar (sayılar koddan değil ayarlardan).
        refresh_limit_anon=settings.max_refresh_anon,
        refresh_limit_registered=settings.max_refresh_registered,
        refresh_resets_at=_refresh_resets_at(db, user, r_limit, r_used),
        budget_exceeded=budget.is_budget_exceeded(),
        cost_today_usd=round(budget.daily_cost_usd(), 4),
        daily_budget_usd=settings.daily_budget_usd,
        entity_limit=settings.entity_limit_for(user),
        entity_used=watchlist_count(db, user.id),
    )
