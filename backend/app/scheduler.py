"""APScheduler tabanlı saatlik yenileme — açık/kapalı bayrağıyla.

Zamanlayıcı bir arka plan thread'inde çalışır. `enabled()` durumu runtime'da
`/refresh` ucu üzerinden değiştirilebilir (in-memory bayrak).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import get_settings
from .refresh import run_refresh

logger = logging.getLogger("newsradar.scheduler")

_scheduler: BackgroundScheduler | None = None
_enabled: bool = False
_JOB_ID = "hourly_refresh"


def _job() -> None:
    if not _enabled:
        return
    try:
        run_refresh()
    except Exception:  # noqa: BLE001 — zamanlayıcı thread'i asla çökmesin
        logger.exception("Zamanlanmış yenileme başarısız")


def start() -> None:
    """Zamanlayıcıyı başlatır (config'e göre açık/kapalı). Uygulama açılışında çağrılır."""
    global _scheduler, _enabled
    if _scheduler is not None:
        return
    _enabled = get_settings().scheduler_enabled
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_job, "interval", hours=1, id=_JOB_ID, max_instances=1)
    _scheduler.start()
    logger.info("Zamanlayıcı başladı (aktif=%s)", _enabled)


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
