"""Yenileme orkestrasyonu: çek → analiz et (tek akış).

`/refresh` ucu ve saatlik zamanlayıcı bunu çağırır. Her adım kendi hatasını
yönetir; tek bir kaynak/entity hatası tüm yenilemeyi çökertmez.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from .analysis.claude_client import ClaudeClient, MissingAPIKeyError
from .analysis.pipeline import analyze_all
from .db.database import session_scope
from .ingest import fetch_all

logger = logging.getLogger("newsradar.refresh")

# Elle 'Yenile' ile saatlik zamanlayıcının aynı anda yazmasını engelleyen kilit.
# Bir refresh sürerken ikincisi beklemeden 'zaten çalışıyor' deyip çıkar.
_refresh_lock = threading.Lock()


@dataclass
class RefreshSummary:
    fetched_new: int = 0
    analyzed: int = 0
    discarded: int = 0
    entity_assessments: int = 0
    warnings: list[str] = field(default_factory=list)


def run_refresh(lookback_hours: int | None = None) -> RefreshSummary:
    """Tüm izleme listesi için haber çeker ve (anahtar varsa) analiz eder.

    Aynı anda yalnızca tek bir refresh çalışır; biri sürerken ikincisi
    beklemeden 'refresh already running' uyarısıyla döner (çakışan yazma yok).
    """
    summary = RefreshSummary()

    # Bloke etmeden kilidi dene: meşgulse hemen çık.
    if not _refresh_lock.acquire(blocking=False):
        logger.info("Yenileme atlandı: zaten çalışıyor.")
        summary.warnings.append("refresh already running")
        return summary

    try:
        # 1) Çekme (Claude gerektirmez).
        with session_scope() as session:
            for r in fetch_all(session, lookback_hours):
                summary.fetched_new += r.new_count
                summary.warnings.extend(f"[{r.entity_name}] {w}" for w in r.warnings)

        # 2) Analiz (Claude gerektirir; anahtar yoksa çekme yine geçerli kalır).
        try:
            client = ClaudeClient()
        except MissingAPIKeyError as exc:
            summary.warnings.append(str(exc))
            return summary

        with session_scope() as session:
            for r in analyze_all(session, client):
                summary.analyzed += r.analyzed
                summary.discarded += r.discarded
                summary.entity_assessments += 1 if r.entity_assessment else 0
                summary.warnings.extend(f"[{r.entity_name}] {w}" for w in r.warnings)

        logger.info(
            "Yenileme tamam: yeni=%d analiz=%d elenen=%d değerlendirme=%d",
            summary.fetched_new, summary.analyzed, summary.discarded, summary.entity_assessments,
        )
        return summary
    finally:
        _refresh_lock.release()
