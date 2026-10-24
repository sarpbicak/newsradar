"""Yenileme orkestrasyonu: çek → (ön-filtre + paralel) analiz et.

`/refresh` ucu ve zamanlayıcı işi doğrudan değil, YENİLEME KUYRUĞU üzerinden
(app/refresh_queue.py) çalıştırır: kuyruğun tek işçi thread'i işleri sırayla buradaki
`run_refresh`'e verir. Süreç durumu (is_running, ilerleme, kullanıcı başı son sonuç) ve
entity başı "en son ne zaman tazelendi" kaydı (kuyruk birleştirmesi için) modül içinde
tutulur ve `/status` ile okunur. Her adım kendi hatasını yönetir; tek bir kaynak/entity
hatası yenilemeyi çökertmez.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .analysis.claude_client import MissingAPIKeyError
from .analysis.llm import get_llm_provider
from .analysis.pipeline import analyze_all_async
from .analyst import refresh_analyst
from .db.database import session_scope
from .ingest import fetch_all
from .messages import msg, render, with_entity
from .prices import refresh_prices
from .quota import prune as prune_quota

logger = logging.getLogger("newsradar.refresh")

# Aynı anda tek taramanın çalışmasını garanti eden kilit. Sunucuda kuyruk işçisi alır
# (iş zaten sırayla gelir); CLI/eval gibi doğrudan run_refresh çağrılarına karşı da korur.
_refresh_lock = threading.Lock()


@dataclass
class RefreshSummary:
    fetched_new: int = 0
    prefiltered: int = 0
    analyzed: int = 0
    discarded: int = 0
    entity_assessments: int = 0
    # Sayaçların anlamı (banner bunları gösterir):
    #   fetched_new  — bu taramada veritabanına YENİ eklenen makale (URL-hash tekil)
    #   llm_articles — bu taramada LLM'e gidip yanıtı alınan makale (= analyzed + discarded);
    #                  önceki taramalardan kuyrukta kalanlar da dahil (entity başı tavan)
    #   analyzed     — bunlardan ilgili bulunup TUTULAN; discarded — ilgisiz bulunup elenen
    #   prefiltered  — LLM'e hiç gitmeden elenen (aynı haberin kopyası / ön-filtre)
    #   queued       — tarama sonunda hâlâ analiz bekleyen (sonraki yenilemede işlenir)
    #   expired      — lookback dışına düştüğü için bu taramada LLM'den çıkarılan
    llm_articles: int = 0
    expired: int = 0
    queued: int = 0
    assessments_skipped: int = 0
    # Kullanıcıya giden mesajlar: app.messages.msg(...) — kod + parametre, frontend çevirir.
    warnings: list[dict] = field(default_factory=list)  # gerçek sorunlar
    infos: list[dict] = field(default_factory=list)     # normal bilgi (tazelik/kota atlaması)
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
    # Adım bazlı ilerleme (UI: "NVIDIA için haberler çekiliyor…" + entity içinde dolan çubuk).
    # step: "prices" | "fetch" | "filter" | "analyze" | "assess" | "skipped" | "done"
    step: str | None = None
    step_entity: str | None = None
    step_count: int | None = None      # adımın makale sayısı (filter/analyze)
    entity_progress: dict = field(default_factory=dict)  # entity_id → 0..1 (kendi dilimi)
    skipped_entity: str | None = None  # "Tesla atlandı, yeni veri yok" — kısa süre gösterilir
    skipped_at: float = 0.0
    last_completed_at: datetime | None = None
    last_summary: RefreshSummary | None = None
    user_id: int | None = None        # şu an çalışan taramayı başlatan kullanıcı
    last_user_id: int | None = None   # son tamamlanan taramayı başlatan kullanıcı


_state = _State()
_state_lock = threading.Lock()

# KULLANICI BAŞI SON SONUÇ (kuyruk: herkes kendi son işinin sonucunu görür, başkasınınki
# onu ezmez). user_id → {status, summary (dict|None), finished_at (UTC), message}.
# status: done | merged | failed | budget | canceled. Bellekte; yeniden başlatmada sıfırlanır.
_results: dict[int, dict] = {}

# KUYRUK BİRLEŞTİRMESİ: entity_id → işlenmesinin BİTTİĞİ an (time.monotonic). HERHANGİ bir
# işte (kullanıcı ya da zamanlayıcı) entity bitince güncellenir. Sırada bekleyen iş başlarken
# kendi enqueued_at'inden sonra tazelenen entity'leri atlar (analiz havuzu ortak).
_entity_refreshed_at: dict[int, float] = {}

# Sonuç durumlarına karşılık gelen kısa kullanıcı mesajları (Türkçe; uzun tire yok).
RESULT_MESSAGES = {
    "done": "Yenileme tamamlandı.",
    "merged": ("Listenizdeki şirketler siz sırada beklerken başka bir yenilemede güncellendi, "
               "hakkınızdan düşülmedi."),
    "failed": "Yenileme beklenmeyen bir hatayla durdu, hakkınız iade edildi.",
    "budget": ("Günlük analiz bütçesi doldu, yenilemeniz başlatılmadı. Hakkınızdan düşülmedi, "
               "yarın tekrar deneyin."),
    "canceled": "Sıradaki yenilemeniz iptal edildi.",
}


def record_user_result(user_id: int | None, status: str, summary: RefreshSummary | None = None,
                       message: str | None = None) -> None:
    """Kullanıcının son iş sonucunu yazar (zamanlayıcı işi user_id=None → kaydedilmez)."""
    if user_id is None:
        return
    with _state_lock:
        _results[user_id] = {
            "status": status,
            "summary": asdict(summary) if summary else None,
            "finished_at": datetime.now(timezone.utc),
            "message": message or RESULT_MESSAGES.get(status, ""),
        }


def get_user_result(user_id: int) -> dict | None:
    """Kullanıcının son iş sonucunun kopyası (yoksa None)."""
    with _state_lock:
        r = _results.get(user_id)
        return dict(r) if r else None


def mark_entities_refreshed(entity_ids, not_before: float | None = None) -> None:
    """Entity'leri "şimdi tazelendi" diye işaretler (birleştirme kaydı).

    not_before verilirse o andan SONRA zaten işaretlenmiş entity'ler ellenmez (adım
    bildiriminden gelen gerçek bitiş zamanı, iş sonundaki toplu işaretle ötelenmesin)."""
    now = time.monotonic()
    with _state_lock:
        for eid in entity_ids:
            cur = _entity_refreshed_at.get(eid)
            if not_before is not None and cur is not None and cur >= not_before:
                continue
            _entity_refreshed_at[eid] = now


def refreshed_since(entity_ids, since: float) -> set[int]:
    """since (monotonic) anında ya da sonrasında işlenmesi biten entity id'leri."""
    with _state_lock:
        return {eid for eid in entity_ids if _entity_refreshed_at.get(eid, float("-inf")) >= since}


def get_state() -> dict:
    """/status için anlık durumun kopyası (thread-güvenli)."""
    with _state_lock:
        return {
            "is_running": _state.is_running,
            "progress_done": _state.progress_done,
            "progress_total": _state.progress_total,
            "current_entity": _state.current_entity,
            "step": _state.step,
            "step_entity": _state.step_entity,
            "step_count": _state.step_count,
            "progress_fraction": _fraction(),
            # Atlama notu yalnızca ~3 sn görünür, sonra akış devam eder.
            "skipped_entity": _state.skipped_entity
            if time.time() - _state.skipped_at < SKIP_NOTE_SECONDS else None,
            "last_completed_at": _state.last_completed_at,
            "last_summary": asdict(_state.last_summary) if _state.last_summary else None,
            "user_id": _state.user_id,
            "last_user_id": _state.last_user_id,
        }


def is_running() -> bool:
    with _state_lock:
        return _state.is_running


def _fraction() -> float:
    """Genel ilerleme 0..1 = entity dilimlerinin ortalaması (kilit altında çağrılır)."""
    p = _state.entity_progress
    return round(sum(p.values()) / len(p), 4) if p else 0.0


def _set_running(running: bool, total: int = 0, user_id: int | None = None,
                 entity_ids: list[int] | None = None) -> None:
    with _state_lock:
        _state.is_running = running
        if running:
            _state.progress_done = 0
            _state.progress_total = total
            _state.current_entity = None
            _state.user_id = user_id
            _state.step = _state.step_entity = _state.step_count = None
            _state.entity_progress = {i: 0.0 for i in (entity_ids or [])}
            _state.skipped_entity, _state.skipped_at = None, 0.0


# Entity dilimi içindeki adım konumları (çubuk 0'da takılmasın; adım adım dolsun).
_FETCH_START, _FETCH_DONE = 0.02, 0.15
SKIP_NOTE_SECONDS = 3


def _report_step(entity_id: int | None, name: str | None, step: str,
                 n: int | None = None, frac: float | None = None) -> None:
    """Adım bildirimi: metin (step/entity/count) + entity'nin kendi dilimindeki ilerleme."""
    with _state_lock:
        if step == "skipped":
            _state.skipped_entity, _state.skipped_at = name, time.time()
        elif step != "done":
            _state.step, _state.step_entity, _state.step_count = step, name, n
        if entity_id is not None and frac is not None:
            cur = _state.entity_progress.get(entity_id, 0.0)
            _state.entity_progress[entity_id] = max(cur, min(1.0, frac))
            # Entity dilimi doldu (done/skipped) → birleştirme kaydı: bu entity şimdi tazelendi.
            # Hattaki her bitiş yolu (kota/bütçe atlaması, entity hatası dahil) frac=1.0 bildirir.
            if frac >= 1.0:
                _entity_refreshed_at[entity_id] = time.monotonic()
        _state.progress_done = sum(1 for v in _state.entity_progress.values() if v >= 1.0)


def _on_fetch(entity_id: int, name: str, state: str) -> None:
    _report_step(entity_id, name, "fetch",
                 frac=_FETCH_START if state == "start" else _FETCH_DONE)


def _set_progress(done: int, total: int) -> None:
    with _state_lock:
        _state.progress_done = done
        _state.progress_total = total


def _set_current_entity(name: str | None) -> None:
    """Şu an analiz edilen şirket (UI 'X analiz ediliyor…' gösterir). Entity'ler
    eşzamanlı işlendiği için bu yaklaşık: en son başlayan entity'nin adı."""
    with _state_lock:
        _state.current_entity = name


def _record_completion(summary: RefreshSummary, status: str = "done") -> None:
    """Tarama bitti: genel son özet + başlatan kullanıcının kişisel son sonucu.
    status="failed" → özet kullanıcıya gösterilmez (yarım kalmış tarama)."""
    with _state_lock:
        uid = _state.user_id
        _state.last_completed_at = datetime.now(timezone.utc)
        _state.last_summary = summary
        _state.last_user_id = uid
        _state.user_id = None
        _state.current_entity = None
    record_user_result(uid, status, summary if status == "done" else None)


def _queued_count(entity_ids: set[int] | None) -> int:
    """Tarama sonunda hâlâ analiz bekleyen makale (aktif, kapsamdaki entity'ler)."""
    from sqlalchemy import func, select

    from .db.models import Article, Entity

    with session_scope() as s:
        q = (select(func.count()).select_from(Article).join(Entity, Entity.id == Article.entity_id)
             .where(Entity.active.is_(True), Article.analyzed.is_(False),
                    Article.prefiltered.is_(False), Article.expired.is_(False)))
        if entity_ids is not None:
            q = q.where(Article.entity_id.in_(entity_ids))
        return int(s.scalar(q) or 0)


# --------------------------- Çekirdek akış --------------------------- #
def run_refresh(
    lookback_hours: int | None = None,
    manual: bool = False,
    entity_ids: set[int] | None = None,
    user_id: int | None = None,
    _lock_held: bool = False,
) -> RefreshSummary:
    """İzleme listesi için çeker ve (anahtar varsa) analiz eder (senkron çekirdek).

    entity_ids verilirse YALNIZCA o entity'ler işlenir (kişisel elle yenileme —
    kullanıcının kendi listesi); None ise tüm aktif havuz (scheduler). user_id, /status'un
    ilerlemeyi kişiselleştirmesi için taşınır. Aynı anda tek refresh çalışır.
    _lock_held=True: kilidi ÇAĞIRAN aldı ve kendisi bırakır (kuyruk işçisi).
    """
    summary = RefreshSummary()

    if not _lock_held and not _refresh_lock.acquire(blocking=False):
        logger.info("Yenileme atlandı: zaten çalışıyor.")
        summary.warnings.append(msg("refresh_running"))
        return summary
    release_lock = not _lock_held
    failed = False

    # İlerleme toplamı için (scoped) aktif entity'leri baştan al (UI 0/Y gösterebilsin).
    try:
        with session_scope() as session:
            from sqlalchemy import select

            from .db.models import Entity

            q = select(Entity.id).where(Entity.active.is_(True))
            if entity_ids is not None:
                q = q.where(Entity.id.in_(entity_ids))
            scoped_ids = list(session.scalars(q).all())
    except Exception:  # noqa: BLE001
        scoped_ids = []

    _set_running(True, total=len(scoped_ids), user_id=user_id, entity_ids=scoped_ids)
    try:
        # 0) Fiyat + analist snapshot'ları (ticker entity'ler; ucuz, hata-toleranslı).
        _report_step(None, None, "prices")
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
            for r in fetch_all(session, lookback_hours, manual, entity_ids, on_entity=_on_fetch):
                summary.fetched_new += r.new_count
                summary.warnings.extend(with_entity(w, r.entity_name) for w in r.warnings)
                summary.infos.extend(with_entity(i, r.entity_name) for i in r.infos)
            prune_quota(session)  # eski api_call kayıtlarını temizle

        # 2) Analiz (ön-filtre + paralel). Anahtar yoksa çekme yine geçerli kalır.
        #    Sağlayıcı env'den seçilir (anthropic/openrouter) — geri dönülebilir. Model
        #    amaca göre: makale analizi ve entity değerlendirmesi ayrı istemciler.
        try:
            client = get_llm_provider("article")
            assess_client = get_llm_provider("assessment")
        except MissingAPIKeyError as exc:
            summary.warnings.append(msg("llm_key_missing", detail=str(exc)))
            return summary

        # SİSTEM BÜTÇE TAVANI: günlük USD bütçesi dolduysa YENİ analiz yapma.
        from .budget import is_budget_exceeded
        if is_budget_exceeded():
            summary.warnings.append(msg("budget_exceeded"))
            logger.warning("[budget] Günlük USD bütçesi dolu — analiz atlandı.")
            return summary

        # Kullanım çağrı başına llm_usage'a yazılıyor (budget.record_llm_call); burada yalnızca
        # sağlık kaydı için bu taramada başarılı çağrı olup olmadığını sayıyoruz.
        clients = [client] if assess_client is client else [client, assess_client]

        def _calls() -> int:
            return sum(getattr(c, "call_count", 0) or 0 for c in clients)

        base_calls = _calls()

        totals = asyncio.run(
            analyze_all_async(
                client, progress_cb=_set_progress, entity_cb=_set_current_entity,
                entity_ids=entity_ids, assess_client=assess_client, step_cb=_report_step,
            )
        )
        summary.prefiltered = totals.prefiltered
        summary.analyzed = totals.analyzed
        summary.discarded = totals.discarded
        summary.entity_assessments = totals.entity_assessments
        summary.llm_articles = totals.llm_articles
        summary.assessments_skipped = totals.assessments_skipped
        summary.queued = _queued_count(entity_ids)
        summary.expired = totals.expired
        summary.warnings.extend(totals.warnings)
        summary.quota_error = totals.quota_error

        calls_made = _calls() - base_calls

        # SAĞLIK: bu yenilemenin LLM sonucunu kaydet (admin paneli 'sistem sağlığı' için).
        # Kota hatası → 'quota'; en az bir başarılı çağrı olduysa → 'ok'. Hiç çağrı yoksa
        # (analiz edilecek bir şey yoktu) sağlık değişmez — son gerçek denemeyi yansıtır.
        from .health import record_llm_health
        if totals.quota_error:
            record_llm_health("quota", None, totals.quota_status_code)
        elif calls_made > 0:
            record_llm_health("ok")

        logger.info(
            "Yenileme tamam: yeni=%d llm_makale=%d tutulan=%d elenen=%d ön-filtre=%d "
            "kuyrukta=%d değerlendirme=%d atlanan_değerlendirme=%d",
            summary.fetched_new, summary.llm_articles, summary.analyzed, summary.discarded,
            summary.prefiltered, summary.queued, summary.entity_assessments,
            summary.assessments_skipped,
        )
        for w in summary.warnings:
            logger.warning("[yenileme uyarısı] %s", render(w))
        return summary
    except BaseException:
        failed = True  # kuyruk hakkı iade eder; kişisel sonuç "failed" yazılır
        raise
    finally:
        _record_completion(summary, "failed" if failed else "done")
        _set_running(False)
        if release_lock:
            _refresh_lock.release()


# ------------------- SAHTE TARAMA (YALNIZCA TEST/E2E) ------------------- #
def run_fake_refresh(entity_ids: set[int] | None, user_id: int | None,
                     seconds: float) -> RefreshSummary:
    """YALNIZCA TEST/E2E İÇİN: gerçek akış yerine ağ/LLM çağrısı YAPMAYAN sahte tarama.

    NEWSRADAR_FAKE_REFRESH_SECONDS > 0 iken kuyruk işçisi run_refresh yerine bunu çağırır.
    Her entity için gerçek akış gibi adım/ilerleme bildirir (UI "Yenileniyor i/N" görsün),
    entity başına seconds/len(ids) bekler, entity'yi tazelendi işaretler (birleştirme kaydı)
    ve sıfırlı bir RefreshSummary döner. Kilidi ÇAĞIRAN (kuyruk işçisi) tutar.
    Üretimde bu ayar 0 (kapalı) kalmalıdır.
    """
    from sqlalchemy import select

    from .db.models import Entity

    summary = RefreshSummary()
    failed = False
    try:
        with session_scope() as session:  # yalnızca yerel DB okuması (ağ yok)
            q = select(Entity.id, Entity.name).where(Entity.active.is_(True))
            if entity_ids is not None:
                q = q.where(Entity.id.in_(entity_ids))
            rows = [(i, n) for i, n in session.execute(q.order_by(Entity.id)).all()]
    except Exception:  # noqa: BLE001
        rows = []
    _set_running(True, total=len(rows), user_id=user_id, entity_ids=[i for i, _ in rows])
    try:
        per = seconds / len(rows) if rows else 0.0
        _report_step(None, None, "prices")
        for eid, name in rows:
            _set_current_entity(name)
            _report_step(eid, name, "fetch", frac=_FETCH_START)
            time.sleep(per / 2)
            _report_step(eid, name, "analyze", n=0, frac=0.5)
            time.sleep(per / 2)
            _report_step(eid, name, "done", frac=1.0)  # → birleştirme kaydı
        return summary
    except BaseException:
        failed = True
        raise
    finally:
        _record_completion(summary, "failed" if failed else "done")
        _set_running(False)
