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

from .analysis.claude_client import MissingAPIKeyError
from .analysis.llm import get_llm_provider
from .analysis.pipeline import analyze_all_async
from .analyst import refresh_analyst
from .db.database import session_scope
from .ingest import fetch_all
from .prices import refresh_prices
from .quota import prune as prune_quota

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
    warnings: list[str] = field(default_factory=list)  # gerçek sorunlar
    infos: list[str] = field(default_factory=list)     # normal bilgi (tazelik/kota atlaması)
    quota_error: bool = False   # sağlayıcı kalıcı kota/bakiye hatası → analiz erken durdu


# --------------------------- Süreç durumu --------------------------- #
# İlerleme KİŞİSEL: elle yenilemeyi hangi kullanıcı başlattıysa (user_id) durum ona
# aittir; /status yalnızca o kullanıcıya is_running/ilerleme/özet gösterir (başka
# kullanıcı, başkasının taramasının sayısını/uyarılarını görmesin — izolasyon).
@dataclass
class _State:
    is_running: bool = False
    progress_done: int = 0
    progress_total: int = 0
    current_entity: str | None = None  # şu an analiz edilen şirket adı (yaklaşık: en son başlayan)
    last_completed_at: datetime | None = None
    last_summary: RefreshSummary | None = None
    user_id: int | None = None        # şu an çalışan taramayı başlatan kullanıcı
    last_user_id: int | None = None   # son tamamlanan taramayı başlatan kullanıcı


_state = _State()
_state_lock = threading.Lock()


def get_state() -> dict:
    """/status için anlık durumun kopyası (thread-güvenli)."""
    with _state_lock:
        return {
            "is_running": _state.is_running,
            "progress_done": _state.progress_done,
            "progress_total": _state.progress_total,
            "current_entity": _state.current_entity,
            "last_completed_at": _state.last_completed_at,
            "last_summary": asdict(_state.last_summary) if _state.last_summary else None,
            "user_id": _state.user_id,
            "last_user_id": _state.last_user_id,
        }


def is_running() -> bool:
    with _state_lock:
        return _state.is_running


def _set_running(running: bool, total: int = 0, user_id: int | None = None) -> None:
    with _state_lock:
        _state.is_running = running
        if running:
            _state.progress_done = 0
            _state.progress_total = total
            _state.current_entity = None
            _state.user_id = user_id


def _set_progress(done: int, total: int) -> None:
    with _state_lock:
        _state.progress_done = done
        _state.progress_total = total


def _set_current_entity(name: str | None) -> None:
    """Şu an analiz edilen şirket (UI 'X analiz ediliyor…' gösterir). Entity'ler
    eşzamanlı işlendiği için bu yaklaşık: en son başlayan entity'nin adı."""
    with _state_lock:
        _state.current_entity = name


def _record_completion(summary: RefreshSummary) -> None:
    with _state_lock:
        _state.last_completed_at = datetime.now(timezone.utc)
        _state.last_summary = summary
        _state.last_user_id = _state.user_id
        _state.user_id = None
        _state.current_entity = None


# --------------------------- Çekirdek akış --------------------------- #
def run_refresh(
    lookback_hours: int | None = None,
    manual: bool = False,
    entity_ids: set[int] | None = None,
    user_id: int | None = None,
) -> RefreshSummary:
    """İzleme listesi için çeker ve (anahtar varsa) analiz eder (senkron çekirdek).

    entity_ids verilirse YALNIZCA o entity'ler işlenir (kişisel elle yenileme —
    kullanıcının kendi listesi); None ise tüm aktif havuz (scheduler). user_id, /status'un
    ilerlemeyi kişiselleştirmesi için taşınır. Aynı anda tek refresh çalışır.
    """
    summary = RefreshSummary()

    if not _refresh_lock.acquire(blocking=False):
        logger.info("Yenileme atlandı: zaten çalışıyor.")
        summary.warnings.append("refresh already running")
        return summary

    # İlerleme toplamı için (scoped) aktif entity sayısını baştan al (UI 0/Y gösterebilsin).
    try:
        with session_scope() as session:
            from sqlalchemy import func, select

            from .db.models import Entity

            q = select(func.count()).select_from(Entity).where(Entity.active.is_(True))
            if entity_ids is not None:
                q = q.where(Entity.id.in_(entity_ids))
            total = session.scalar(q) or 0
    except Exception:  # noqa: BLE001
        total = 0

    _set_running(True, total=total, user_id=user_id)
    try:
        # 0) Fiyat + analist snapshot'ları (ticker entity'ler; ucuz, hata-toleranslı).
        try:
            summary.warnings.extend(refresh_prices(entity_ids))
        except Exception as exc:  # noqa: BLE001 — fiyat hatası yenilemeyi çökertmesin
            logger.warning("Fiyat çekme başarısız (atlandı): %s", exc)
        try:
            summary.warnings.extend(refresh_analyst(entity_ids))
        except Exception as exc:  # noqa: BLE001 — analist hatası yenilemeyi çökertmesin
            logger.warning("Analist çekme başarısız (atlandı): %s", exc)

        # 1) Çekme (Claude gerektirmez). manual: elle Yenile'de kota-akıllı davran.
        with session_scope() as session:
            for r in fetch_all(session, lookback_hours, manual, entity_ids):
                summary.fetched_new += r.new_count
                summary.warnings.extend(f"[{r.entity_name}] {w}" for w in r.warnings)
                summary.infos.extend(f"[{r.entity_name}] {i}" for i in r.infos)
            prune_quota(session)  # eski api_call kayıtlarını temizle

        # 2) Analiz (ön-filtre + paralel). Anahtar yoksa çekme yine geçerli kalır.
        #    Sağlayıcı env'den seçilir (nvidia/anthropic) — geri dönülebilir.
        try:
            client = get_llm_provider()
        except MissingAPIKeyError as exc:
            summary.warnings.append(str(exc))
            return summary

        # SİSTEM BÜTÇE TAVANI: günlük token dolduysa YENİ analiz yapma (maliyet güvencesi).
        from .budget import is_budget_exceeded, record_llm_usage
        if is_budget_exceeded():
            summary.warnings.append(
                "Günlük analiz kapasitesi doldu — yeni analiz durduruldu, yarın tekrar deneyin."
            )
            logger.warning("[budget] Günlük token tavanı dolu — analiz atlandı.")
            return summary

        # Bu taramanın token deltasını ölçmek için başlangıç anlık değeri.
        base_p = getattr(client, "total_prompt_tokens", 0) or 0
        base_c = getattr(client, "total_completion_tokens", 0) or 0
        base_calls = getattr(client, "call_count", 0) or 0

        totals = asyncio.run(
            analyze_all_async(
                client, progress_cb=_set_progress, entity_cb=_set_current_entity,
                entity_ids=entity_ids,
            )
        )
        summary.prefiltered = totals.prefiltered
        summary.analyzed = totals.analyzed
        summary.discarded = totals.discarded
        summary.entity_assessments = totals.entity_assessments
        summary.warnings.extend(totals.warnings)
        summary.quota_error = totals.quota_error

        # Kullanımı kaydet (maliyet takibi + günlük bütçe sayacı).
        dp = (getattr(client, "total_prompt_tokens", 0) or 0) - base_p
        dc = (getattr(client, "total_completion_tokens", 0) or 0) - base_c
        calls_made = (getattr(client, "call_count", 0) or 0) - base_calls
        record_llm_usage(dp, dc, calls_made)

        # SAĞLIK: bu yenilemenin LLM sonucunu kaydet (admin paneli 'sistem sağlığı' için).
        # Kota hatası → 'quota'; en az bir başarılı çağrı olduysa → 'ok'. Hiç çağrı yoksa
        # (analiz edilecek bir şey yoktu) sağlık değişmez — son gerçek denemeyi yansıtır.
        from .health import record_llm_health
        if totals.quota_error:
            record_llm_health("quota", None, totals.quota_status_code)
        elif calls_made > 0:
            record_llm_health("ok")

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


def start_background_refresh(
    lookback_hours: int | None = None,
    manual: bool = True,
    entity_ids: set[int] | None = None,
    user_id: int | None = None,
) -> bool:
    """Yenilemeyi arka plan thread'inde başlatır (elle Yenile → manual=True).

    entity_ids: kişisel elle yenilemede kullanıcının kendi entity id'leri (None → tüm havuz).
    Zaten çalışıyorsa False döner.
    """
    if is_running():
        return False
    thread = threading.Thread(
        target=run_refresh, args=(lookback_hours, manual, entity_ids, user_id),
        name="refresh", daemon=True,
    )
    thread.start()
    return True
