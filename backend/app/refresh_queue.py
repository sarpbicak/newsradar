"""Yenileme kuyruğu: süreç içi, tek işçi thread'i, işler sırayla çalışır.

Site herkese açık: aynı anda tek tarama çalışabildiği için (ortak analiz havuzu, LLM
bütçesi, SQLite) başka kullanıcıya "meşgul, sonra dene" demek yerine istek SIRAYA girer.

  * İş = {job_id, user_id (zamanlayıcı: None), entity_ids (zamanlayıcı: None = tüm aktif
    havuz), enqueued_at, priority}. Kullanıcı işleri FIFO; zamanlayıcı işi en düşük
    öncelikli (her zaman kullanıcı işlerinin arkasında) ve sırada en fazla BİR tane olur.
  * Sınırlar: sırada en fazla NEWSRADAR_REFRESH_QUEUE_MAX kullanıcı işi; kullanıcı başı
    en fazla 1 etkin iş (sırada ya da çalışan). İkinci istek mevcut işin durumunu döner.
  * Birleştirme: iş BAŞLARKEN, kendi enqueued_at'inden sonra (başka bir işte) tazelenmiş
    entity'ler düşülür; run_refresh yalnızca kalanları alır. Hiçbiri kalmadıysa iş hemen
    "merged" biter (kullanıcı için tamamlandı sayılır, hak DÜŞÜLMEZ: onun için bir şey
    çalışmadı).
  * Kota: "refresh" UsageEvent iş GERÇEKTEN başlarken (işçide, kendi session_scope'uyla)
    yazılır, sıraya girerken değil. Çalışma beklenmeyen hatayla düşerse olay silinir (iade).
    Sıradaki iş iptal edilirse zaten yazılmamıştır, iade edilecek bir şey yok.
  * Bütçe: her iş başlamadan önce günlük LLM bütçesine bakılır; doluysa o iş ve sıradaki
    TÜM işler "budget" sonucuyla biter (hak düşülmez).

KALICILIK: kuyruk ve "çalışıyor" durumu YALNIZCA bellekte tutulur (DB'de/uygulama durumu
tablosunda hiçbir "çalışıyor" işareti yok). Yeniden başlatmada kuyruk kaybolur (kabul
edilebilir) ve açılışta temizlenecek kalıcı bir işaret de yoktur. Tek uvicorn süreci
(--workers 1) varsayılır; birden çok süreçte her birinin kendi kuyruğu olurdu.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from dataclasses import dataclass

from . import refresh
from .config import get_settings

logger = logging.getLogger("newsradar.refresh_queue")

PRIORITY_USER = 0
PRIORITY_SCHEDULER = 1  # en düşük: kullanıcı işlerinin önüne asla geçmez


@dataclass
class Job:
    job_id: int
    user_id: int | None              # None → zamanlayıcı işi
    entity_ids: frozenset[int] | None  # None → tüm aktif havuz (zamanlayıcı)
    enqueued_at: float               # time.monotonic() — birleştirme karşılaştırması için
    priority: int
    lookback_hours: int | None = None
    manual: bool = True


# Tüm kuyruk durumu bu koşul değişkeninin (RLock) altında değişir. Kilit sırası her
# zaman kuyruk → refresh._state_lock (snapshot ve claim aynı sırayla alır; kilitlenme yok).
_cv = threading.Condition()
_waiting: list[Job] = []          # (priority, job_id) sıralı bekleyen işler
_running: Job | None = None       # işçinin üstlendiği (çalışan ya da başlamakta olan) iş
_ids = itertools.count(1)
_worker: threading.Thread | None = None


# --------------------------- Yardımcılar --------------------------- #
def _sort_waiting() -> None:
    _waiting.sort(key=lambda j: (j.priority, j.job_id))


def _claim_locked(job: Job) -> None:
    """İşi üstlen: "çalışıyor" durumunu BURADA, kilit altında ve senkron kur.

    POST /refresh yanıtı döndüğü an (ya da sıradaki iş öne geçtiği an) /status zaten
    "çalışıyor" görür; arada "ne sırada ne çalışıyor" boşluğu olmaz."""
    global _running
    _running = job
    ids = sorted(job.entity_ids) if job.entity_ids is not None else []
    refresh._set_running(True, total=len(ids), user_id=job.user_id, entity_ids=ids)
    _cv.notify_all()


def _view_locked(user_id: int) -> dict:
    """Kullanıcının kuyruk görünümü. queue_position 1 tabanlı, bekleyenler arasında;
    zamanlayıcı işi sıranın sonunda durduğu için hiçbir kullanıcının önünde sayılmaz.
    queue_length = bekleyen KULLANICI işi sayısı (zamanlayıcı işi hariç)."""
    pos = None
    for i, j in enumerate(_waiting):
        if j.user_id == user_id:
            pos = i + 1
            break
    st = refresh.get_state()
    return {
        "running": bool(st["is_running"] and st["user_id"] == user_id),
        "queued": pos is not None,
        "queue_position": pos,
        "queue_length": sum(1 for j in _waiting if j.user_id is not None),
        "state": st,
    }


def snapshot(user_id: int) -> dict:
    """/status için TEK seferde tutarlı görünüm: süreç durumu + kuyruk konumu.

    İkisi aynı kilit altında okunur; iş sıradan çıkıp çalışmaya geçerken okuyan istek
    ikisini birden "yok" göremez."""
    with _cv:
        return _view_locked(user_id)


def ensure_worker() -> None:
    """İşçi thread'ini (daemon) gerekiyorsa başlatır. Açılışta ve ilk işte çağrılır."""
    global _worker
    with _cv:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="refresh-queue", daemon=True)
        _worker.start()


# --------------------------- Kuyruğa alma / iptal --------------------------- #
def enqueue_user(user_id: int, entity_ids: set[int],
                 lookback_hours: int | None = None) -> tuple[str, dict]:
    """Kullanıcı işini sıraya alır. (sonuç, görünüm) döner; sonuç:

      "started"        → sıra boştu, iş hemen üstlenildi (çalışıyor)
      "queued"         → sıraya girdi (görünümde queue_position)
      "running"        → kullanıcının zaten çalışan bir işi var (yeni iş eklenmedi)
      "already_queued" → kullanıcının zaten sırada bir işi var (yeni iş eklenmedi)
      "queue_full"     → sıra dolu, iş eklenmedi
    """
    ensure_worker()
    with _cv:
        if _running is not None and _running.user_id == user_id:
            return "running", _view_locked(user_id)
        if any(j.user_id == user_id for j in _waiting):
            return "already_queued", _view_locked(user_id)
        n_users = sum(1 for j in _waiting if j.user_id is not None)
        if n_users >= get_settings().refresh_queue_max:
            return "queue_full", _view_locked(user_id)
        job = Job(job_id=next(_ids), user_id=user_id, entity_ids=frozenset(entity_ids),
                  enqueued_at=time.monotonic(), priority=PRIORITY_USER,
                  lookback_hours=lookback_hours, manual=True)
        if _running is None and not _waiting:
            _claim_locked(job)
            return "started", _view_locked(user_id)
        _waiting.append(job)
        _sort_waiting()
        _cv.notify_all()
        return "queued", _view_locked(user_id)


def enqueue_scheduler() -> bool:
    """Zamanlayıcı işini (en düşük öncelik) sıraya alır. Sırada zaten bir zamanlayıcı
    işi varsa eklemez (False). Çalışan bir zamanlayıcı işinin arkasına bir tane girebilir."""
    ensure_worker()
    with _cv:
        if any(j.user_id is None for j in _waiting):
            return False
        job = Job(job_id=next(_ids), user_id=None, entity_ids=None,
                  enqueued_at=time.monotonic(), priority=PRIORITY_SCHEDULER, manual=False)
        if _running is None and not _waiting:
            _claim_locked(job)
        else:
            _waiting.append(job)
            _sort_waiting()
            _cv.notify_all()
        return True


def cancel_user(user_id: int) -> str:
    """Kullanıcının SIRADAKİ işini iptal eder: "canceled" | "running" | "none".

    Sıradaki işte hak henüz düşülmediği için iade edilecek bir şey yoktur."""
    with _cv:
        for j in _waiting:
            if j.user_id == user_id:
                _waiting.remove(j)
                refresh.record_user_result(user_id, "canceled")
                _cv.notify_all()
                return "canceled"
        if _running is not None and _running.user_id == user_id:
            return "running"
        return "none"


# --------------------------- İşçi --------------------------- #
def _worker_loop() -> None:
    """Tek işçi: üstlenilen işi çalıştırır, bitince sıradakini AYNI kilit bölümünde üstlenir."""
    global _running
    while True:
        with _cv:
            while _running is None:
                if _waiting:
                    _claim_locked(_waiting.pop(0))
                    break
                _cv.wait()
            job = _running
        try:
            _execute(job)
        except Exception:  # noqa: BLE001 — işçi thread'i asla ölmesin
            logger.exception("Kuyruk işi beklenmeyen hata (job=%s)", job.job_id)
            refresh._set_running(False)
        finally:
            with _cv:
                _running = None
                if _waiting:
                    _claim_locked(_waiting.pop(0))


def _budget_exceeded() -> bool:
    from . import budget
    try:
        return budget.is_budget_exceeded()
    except Exception:  # noqa: BLE001 — bütçe okunamadıysa işi engelleme (analiz kendi bakar)
        logger.exception("Bütçe kontrolü başarısız (atlandı)")
        return False


def _active_pool_ids() -> set[int]:
    from sqlalchemy import select

    from .db.database import session_scope
    from .db.models import Entity

    with session_scope() as s:
        return set(s.scalars(select(Entity.id).where(Entity.active.is_(True))).all())


def _record_quota_event(user_id: int) -> int | None:
    """Elle yenileme hakkını iş BAŞLARKEN düş (kendi oturumu, hemen commit)."""
    from .db.database import session_scope
    from .db.models import UsageEvent

    try:
        with session_scope() as s:
            ev = UsageEvent(user_id=user_id, event_type="refresh", detail=None)
            s.add(ev)
            s.flush()
            return ev.id
    except Exception:  # noqa: BLE001 — takip, taramayı engellemez
        logger.exception("Yenileme hakkı kaydı yazılamadı (user=%s)", user_id)
        return None


def _refund_quota_event(event_id: int | None) -> None:
    """Başarısız taramanın başta yazılan hak olayını sil (iade)."""
    if event_id is None:
        return
    from .db.database import session_scope
    from .db.models import UsageEvent

    try:
        with session_scope() as s:
            ev = s.get(UsageEvent, event_id)
            if ev is not None:
                s.delete(ev)
    except Exception:  # noqa: BLE001
        logger.exception("Yenileme hakkı iadesi başarısız (event=%s)", event_id)


def _end_all_budget(job: Job) -> None:
    """Bütçe dolu: bu iş ve sıradaki TÜM işler "budget" sonucuyla biter (hak düşülmez)."""
    with _cv:
        dropped = list(_waiting)
        _waiting.clear()
        for j in [job, *dropped]:
            refresh.record_user_result(j.user_id, "budget")
        refresh._set_running(False)
    logger.warning("[budget] Günlük bütçe dolu: iş %s ve sıradaki %d iş başlatılmadı.",
                   job.job_id, len(dropped))


def _execute(job: Job) -> None:
    """Üstlenilen işi çalıştırır: bütçe → birleştirme → hak düş → tarama (gerçek/sahte)."""
    uid = job.user_id
    if _budget_exceeded():
        _end_all_budget(job)
        return

    # Birleştirme: sırada beklerken başka bir işte tazelenen entity'leri düş.
    scope = set(job.entity_ids) if job.entity_ids is not None else _active_pool_ids()
    fresh = refresh.refreshed_since(scope, job.enqueued_at)
    remaining = scope - fresh
    if not remaining:
        refresh.record_user_result(uid, "merged")
        refresh._set_running(False)
        logger.info("Kuyruk işi %s birleşti: %d entity zaten tazelendi.", job.job_id, len(fresh))
        return
    # Zamanlayıcı işinde hiçbir şey düşülmediyse eski davranış (None = tüm aktif havuz).
    run_ids = remaining if (job.entity_ids is not None or fresh) else None
    if fresh:
        # İlerleme toplamı kalan entity sayısını göstersin ("0/1", üstlenmedeki "0/2" değil).
        refresh._set_running(True, total=len(remaining), user_id=uid, entity_ids=sorted(remaining))

    event_id = _record_quota_event(uid) if uid is not None else None
    started_at = time.monotonic()
    try:
        # Kilit: CLI/eval gibi doğrudan run_refresh çağrısıyla çakışmasın (sunucuda boştur).
        with refresh._refresh_lock:
            fake = get_settings().fake_refresh_seconds
            if fake > 0:
                # YALNIZCA TEST/E2E: ağ/LLM yok (NEWSRADAR_FAKE_REFRESH_SECONDS).
                refresh.run_fake_refresh(run_ids, uid, fake)
            else:
                refresh.run_refresh(job.lookback_hours, job.manual, run_ids, uid, _lock_held=True)
    except Exception:  # noqa: BLE001
        logger.exception("Yenileme işi başarısız (job=%s, user=%s); hak iade ediliyor.",
                         job.job_id, uid)
        _refund_quota_event(event_id)
        refresh.record_user_result(uid, "failed")
        refresh._set_running(False)
        return
    # Erken dönen yollar (ör. LLM anahtarı yok) entity'leri adım adım bitirmez; tarama
    # hatasız bittiyse kapsamdaki entity'ler tazelenmiş sayılır (adımda işaretlenenler ellenmez).
    refresh.mark_entities_refreshed(remaining, not_before=started_at)
