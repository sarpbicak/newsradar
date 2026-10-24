"""APScheduler tabanlı saatlik yenileme — açık/kapalı bayrağıyla.

Zamanlayıcı bir arka plan thread'inde çalışır; yenileme işini yenileme kuyruğuna
(app/refresh_queue.py) bırakır. `enabled()` durumu runtime'da
`/refresh` ucu üzerinden değiştirilebilir (in-memory bayrak).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from . import refresh_queue
from .config import get_settings

logger = logging.getLogger("newsradar.scheduler")

_scheduler: BackgroundScheduler | None = None
_enabled: bool = False
_JOB_ID = "hourly_refresh"


def _job() -> None:
    """Zamanlanmış yenileme: doğrudan çalıştırmaz, KUYRUĞA en düşük öncelikle girer
    (kullanıcı işlerinin arkasında; sırada en fazla bir zamanlayıcı işi)."""
    if not _enabled:
        return
    try:
        if not refresh_queue.enqueue_scheduler():
            logger.info("Zamanlanmış yenileme atlandı: sırada zaten bir zamanlayıcı işi var.")
    except Exception:  # noqa: BLE001 — zamanlayıcı thread'i asla çökmesin
        logger.exception("Zamanlanmış yenileme kuyruğa alınamadı")


def _prune_ip_job() -> None:
    try:
        from .security import prune_ip_records
        prune_ip_records()
    except Exception:  # noqa: BLE001 — zamanlayıcı thread'i asla çökmesin
        logger.exception("IP kayıt temizliği başarısız")


def start() -> None:
    """Zamanlayıcıyı başlatır (config'e göre açık/kapalı). Uygulama açılışında çağrılır."""
    global _scheduler, _enabled
    if _scheduler is not None:
        return
    settings = get_settings()
    _enabled = settings.scheduler_enabled
    hours = settings.scheduler_hours
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_job, "interval", hours=hours, id=_JOB_ID, max_instances=1)
    # GİZLİLİK: IP saklama süresi temizliği — yenileme açık/kapalı olsun her gün çalışır.
    _scheduler.add_job(_prune_ip_job, "interval", hours=24, id="ip_prune", max_instances=1)
    _scheduler.start()
    logger.info("Zamanlayıcı başladı (aktif=%s, her %d saatte)", _enabled, hours)


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def set_enabled(value: bool) -> None:
    """Saatlik yenilemeyi runtime'da aç/kapat."""
    global _enabled
    _enabled = value
    logger.info("Zamanlayıcı aktif=%s", _enabled)


def is_enabled() -> bool:
    return _enabled
