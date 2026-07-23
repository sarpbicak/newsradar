"""Yenileme orkestrasyonu: çek → (ön-filtre + paralel) analiz et.

`/refresh` ucu (arka planda) ve saatlik zamanlayıcı bunu çağırır. Süreç durumu
(is_running, ilerleme, son tamamlanma) modül içinde tutulur ve `/status` ile okunur.
Her adım kendi hatasını yönetir; tek bir kaynak/entity hatası yenilemeyi çökertmez.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .analysis.claude_client import ClaudeClient, MissingAPIKeyError
from .analysis.pipeline import analyze_all_async
from .db.database import session_scope
from .ingest import fetch_all
from .prices import refresh_prices

logger = logging.getLogger("newsradar.refresh")

# Elle 'Yenile' ile saatlik zamanlayıcının aynı anda çalışmasını engelleyen kilit.
_refresh_lock = threading.Lock()


@dataclass
class RefreshSummary:
    fetched_new: int = 0
    prefiltered: int = 0
    analyzed: int = 0
    discarded: int = 0
    entity_assessments: int = 0
    warnings: list[str] = field(default_factory=list)


# --------------------------- Süreç durumu --------------------------- #
@dataclass
class _State:
    is_running: bool = False
    progress_done: int = 0
    progress_total: int = 0
    last_completed_at: datetime | None = None
    last_summary: RefreshSummary | None = None


_state = _State()
_state_lock = threading.Lock()


def get_state() -> dict:
    """/status için anlık durumun kopyası (thread-güvenli)."""
    with _state_lock:
        return {
            "is_running": _state.is_running,
            "progress_done": _state.progress_done,
            "progress_total": _state.progress_total,
            "last_completed_at": _state.last_completed_at,
            "last_summary": asdict(_state.last_summary) if _state.last_summary else None,
        }


def is_running() -> bool:
    with _state_lock:
        return _state.is_running


def _set_running(running: bool, total: int = 0) -> None:
    with _state_lock:
        _state.is_running = running
        if running:
            _state.progress_done = 0
            _state.progress_total = total


def _set_progress(done: int, total: int) -> None:
    with _state_lock:
        _state.progress_done = done
        _state.progress_total = total


def _record_completion(summary: RefreshSummary) -> None:
    with _state_lock:
        _state.last_completed_at = datetime.now(timezone.utc)
        _state.last_summary = summary


# --------------------------- Çekirdek akış --------------------------- #
def run_refresh(lookback_hours: int | None = None) -> RefreshSummary:
    """Tüm izleme listesi için çeker ve (anahtar varsa) analiz eder (senkron çekirdek).

    Aynı anda yalnızca tek bir refresh çalışır; biri sürerken ikincisi beklemeden
    'refresh already running' uyarısıyla döner.
    """
    summary = RefreshSummary()

    if not _refresh_lock.acquire(blocking=False):
        logger.info("Yenileme atlandı: zaten çalışıyor.")
        summary.warnings.append("refresh already running")
        return summary

    # İlerleme toplamı için aktif entity sayısını baştan al (UI 0/Y gösterebilsin).
    try:
        with session_scope() as session:
            from sqlalchemy import func, select

            from .db.models import Entity

            total = session.scalar(
                select(func.count()).select_from(Entity).where(Entity.active.is_(True))
            ) or 0
    except Exception:  # noqa: BLE001
        total = 0

    _set_running(True, total=total)
    try:
        # 0) Fiyat snapshot'ları (ticker entity'ler; ucuz, hata-toleranslı).
        try:
            summary.warnings.extend(refresh_prices())
        except Exception as exc:  # noqa: BLE001 — fiyat hatası yenilemeyi çökertmesin
            logger.warning("Fiyat çekme başarısız (atlandı): %s", exc)

        # 1) Çekme (Claude gerektirmez).
        with session_scope() as session:
            for r in fetch_all(session, lookback_hours):
                summary.fetched_new += r.new_count
                summary.warnings.extend(f"[{r.entity_name}] {w}" for w in r.warnings)

        # 2) Analiz (ön-filtre + paralel). Anahtar yoksa çekme yine geçerli kalır.
        try:
            client = ClaudeClient()
        except MissingAPIKeyError as exc:
            summary.warnings.append(str(exc))
            return summary

        totals = asyncio.run(analyze_all_async(client, progress_cb=_set_progress))
        summary.prefiltered = totals.prefiltered
        summary.analyzed = totals.analyzed
        summary.discarded = totals.discarded
        summary.entity_assessments = totals.entity_assessments
        summary.warnings.extend(totals.warnings)

        logger.info(
            "Yenileme tamam: yeni=%d ön-filtre=%d analiz=%d elenen=%d değerlendirme=%d",
            summary.fetched_new, summary.prefiltered, summary.analyzed,
            summary.discarded, summary.entity_assessments,
        )
        return summary
    finally:
        _record_completion(summary)
        _set_running(False)
        _refresh_lock.release()


def start_background_refresh(lookback_hours: int | None = None) -> bool:
    """Yenilemeyi arka plan thread'inde başlatır. Zaten çalışıyorsa False döner."""
    if is_running():
        return False
    thread = threading.Thread(
        target=run_refresh, args=(lookback_hours,), name="refresh", daemon=True
    )
    thread.start()
    return True
