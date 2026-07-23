"""Claude analiz hattı — ucuz ön-filtre + entity başına tavan + paralel çağrı.

Akış (analyze_all_async):
  1. ÖN-FİLTRE (ucuz, Claude'suz): entity adı/ticker'ı başlık+açıklamada hiç
     geçmeyen makaleler DB'de `prefiltered=True` işaretlenir ve hiç gönderilmez.
  2. TAVAN: entity başına en fazla `max_articles_per_entity` makale (en yeniler
     öncelikli); artanı bir sonraki yenilemeye kalır (analyzed=False).
  3. PARALEL analiz: makaleler `batch_size`'lik gruplar halinde, aynı anda
     `analysis_concurrency` çağrı (asyncio.Semaphore) ile Claude'a gönderilir.
     DB erişimi tek bir asyncio kilidiyle serileştirilir (SQLite 'locked' önlenir);
     ağ çağrıları paraleldir.
  4. Makale sonuçları yazılır (relevance < eşik → elenir), sonra entity-başı
     toplu değerlendirme üretilir.

Dayanıklılık: bir batch/entity hata verirse loglanır ve gerisi devam eder.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import session_scope
from ..db.models import Article, Entity, EntityAnalysis, Suggestion
from ..prices import price_context_for
from .claude_client import ClaudeClient, ClaudeError
from .prompts import (
    SYSTEM_PROMPT,
    build_article_batch_prompt,
    build_entity_prompt,
)
from .schemas import (
    ARTICLE_ANALYSIS_TOOL,
    ENTITY_ANALYSIS_TOOL,
    RELEVANCE_THRESHOLD,
    sanitize_article_analysis,
    sanitize_entity_analysis,
)

logger = logging.getLogger("newsradar.analysis")

AGGREGATE_LOOKBACK = 20  # entity değerlendirmesinde kaç son makale bağlam olarak verilir
MAX_ANALYSIS_HISTORY = 100  # entity başına saklanacak en fazla değerlendirme kaydı
SUGGESTION_TTL_DAYS = 30    # bu süreden eski + az anılan öneriler temizlenir


def _suggestion_key(name: str, ticker: str | None) -> str:
    """Öneri tekilleştirme anahtarı: ticker varsa ona, yoksa isme göre."""
    if ticker:
        return f"t:{ticker.strip().upper()}"
    return f"n:{name.strip().lower()}"


def _accumulate_suggestions(
    session: Session, entity_id: int, source_language: str, co_list: list[dict], rationale: str
) -> None:
    """Co-mentioned şirketleri suggestions tablosuna yaz/güncelle (upsert).

    source_language: co-mention'ın geldiği entity'nin dili — keyword olarak
    eklenecekse bu dil miras alınır (ilk görülende sabitlenir).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for c in co_list:
        key = _suggestion_key(c["name"], c["ticker"])
        sug = session.scalar(select(Suggestion).where(Suggestion.norm_key == key))
        if sug is None:
            session.add(
                Suggestion(
                    name=c["name"], ticker=c["ticker"], is_public=c["is_public"],
                    country=c.get("country"), exchange=c.get("exchange"),
                    source_language=source_language or "en",
                    norm_key=key, mention_count=1, source_entity_ids=[entity_id],
                    sample_rationale=rationale or None, first_seen_at=now, last_seen_at=now,
                )
            )
            # autoflush=False: aynı session'da sonraki aynı-şirket aramaları bunu
            # bulabilsin diye hemen flush et (yoksa mükerrer insert → unique hatası).
            session.flush()
        else:
            sug.mention_count += 1
            sug.last_seen_at = now
            if rationale:
                sug.sample_rationale = rationale
            # Eksik bilgiyi sonradan öğrenilirse doldur.
            if not sug.ticker and c["ticker"]:
                sug.ticker = c["ticker"]
            if sug.is_public is None and c["is_public"] is not None:
                sug.is_public = c["is_public"]
            if not sug.country and c.get("country"):
                sug.country = c["country"]
            if not sug.exchange and c.get("exchange"):
                sug.exchange = c["exchange"]
            ids = list(sug.source_entity_ids or [])
            if entity_id not in ids:
                ids.append(entity_id)
                sug.source_entity_ids = ids  # yeni liste ata → değişiklik algılansın


def prune_stale_suggestions() -> int:
    """30 günden beri görülmemiş ve hâlâ az anılan (<3) önerileri temizler."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=SUGGESTION_TTL_DAYS)
    with session_scope() as session:
        stale = session.scalars(
            select(Suggestion.id).where(
                Suggestion.mention_count < 3, Suggestion.last_seen_at < cutoff
            )
        ).all()
        if stale:
            session.execute(delete(Suggestion).where(Suggestion.id.in_(stale)))
        return len(stale)


@dataclass
class AnalyzeTotals:
    """Tüm yenileme için analiz sayaçları."""

    prefiltered: int = 0        # ön-filtrede elenen (Claude'a hiç gitmedi)
    analyzed: int = 0           # makale-başı analiz edilen
    discarded: int = 0          # relevance < eşik → elenen
    entity_assessments: int = 0  # entity-başı değerlendirme üretilen
    warnings: list[str] = field(default_factory=list)


# ------------------------------ Ön-filtre ------------------------------ #
def _match_terms(name: str, query: str) -> list[str]:
    """Bir makalenin bu entity'ye ait olup olmadığını ucuza sınamak için terimler."""
    terms: set[str] = set()
    for t in (query, name):
        t = (t or "").strip().lower()
        if len(t) >= 2:
            terms.add(t)
    # Çok kelimeli adlarda tek tek kelimeler de eşleşsin (ör. "Berkshire Hathaway").
    for w in (name or "").lower().split():
        if len(w) >= 3:
            terms.add(w)
    return list(terms)


def _prefilter(session: Session, entity: Entity, max_articles: int) -> tuple[list[dict], int]:
    """Bekleyen makaleleri ön-filtreden geçirir; kabul edilenlerin payload'ını döner.

    - Adı/ticker'ı hiç geçmeyenler `prefiltered=True` işaretlenir (Claude'a gitmez).
    - Kabul edilenler en yeniden eskiye sıralı; ilk `max_articles` alınır, gerisi
      bir sonraki yenilemeye kalır (analyzed=False, prefiltered=False).
    Döner: (payload listesi, ön-filtrede elenen sayısı).
    """
    pending: list[Article] = list(
        session.scalars(
            select(Article)
            .where(
                Article.entity_id == entity.id,
                Article.analyzed.is_(False),
                Article.prefiltered.is_(False),
            )
            .order_by(Article.published_at.desc().nullslast())
        ).all()
    )
    terms = _match_terms(entity.name, entity.query)
    kept: list[Article] = []
    prefiltered = 0
    for a in pending:
        haystack = f"{a.title} {a.description or ''}".lower()
        if terms and any(term in haystack for term in terms):
            kept.append(a)
        else:
            a.prefiltered = True
            prefiltered += 1

    capped = kept[:max_articles]  # tavan: gerisi sonraki yenilemede işlenir
    payload = [
        {"id": a.id, "title": a.title, "source": a.source, "description": a.description}
        for a in capped
    ]
    return payload, prefiltered


# ------------------------- DB yazma yardımcıları ------------------------- #
# Bunlar to_thread ile ayrı thread'de ama tek bir asyncio kilidiyle SIRAYLA
# çağrılır — aynı anda tek SQLite yazarı olur (WAL + 'locked' güvenliği).
def _apply_article_results(entity_id: int, batch_datas: list[dict]) -> dict:
    """Makale-başı analiz sonuçlarını DB'ye yazar; alakasızları eler."""
    analyzed = 0
    discarded = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as session:
        source_entity = session.get(Entity, entity_id)
        source_language = source_entity.language if source_entity else "en"
        for data in batch_datas:
            for raw in data.get("analyses", []):
                try:
                    clean = sanitize_article_analysis(raw)
                except (KeyError, ValueError, TypeError):
                    continue
                article = session.get(Article, clean["id"])
                if article is None or article.entity_id != entity_id:
                    continue
                if clean["relevance"] < RELEVANCE_THRESHOLD:
                    session.delete(article)  # alakasız → panelde gürültü tutma
                    discarded += 1
                    continue
                article.sentiment = clean["sentiment"]
                article.event_type = clean["event_type"]
                article.risk_flags = clean["risk_flags"]
                article.impact_horizon = clean["impact_horizon"]
                article.relevance = clean["relevance"]
                article.rationale = clean["rationale"]
                article.analyzed = True
                article.analyzed_at = now
                analyzed += 1
                # Öneri biriktir: yalnızca İLGİLİ (kalan) makalelerin co-mention'ları.
                if clean.get("co_mentioned"):
                    _accumulate_suggestions(
                        session, entity_id, source_language, clean["co_mentioned"], clean["rationale"]
                    )
    return {"analyzed": analyzed, "discarded": discarded}


def _read_assessment_payload(entity_id: int) -> list[dict]:
    """Entity değerlendirmesi için son analiz edilmiş makalelerden bağlam payload'ı."""
    with session_scope() as session:
        articles = session.scalars(
            select(Article)
            .where(Article.entity_id == entity_id, Article.analyzed.is_(True))
            .order_by(Article.published_at.desc().nullslast())
            .limit(AGGREGATE_LOOKBACK)
        ).all()
        return [
            {
                "title": a.title,
                "sentiment": a.sentiment or 0.0,
                "event_type": a.event_type or "other",
                "impact_horizon": a.impact_horizon or "short",
                "risk_flags": a.risk_flags or [],
                "rationale": a.rationale or "",
            }
            for a in articles
        ]


def _avg_sentiment(payload: list[dict]) -> float | None:
    """Değerlendirmeye giren makalelerin ortalama duygusu (snapshot için)."""
    vals = [p.get("sentiment") for p in payload if p.get("sentiment") is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _write_assessment(entity_id: int, data: dict, considered: int, avg_sentiment: float | None) -> None:
    """Entity-başı değerlendirmeyi APPEND-ONLY kaydeder ve geçmişi 100 kayıtla sınırlar."""
    clean = sanitize_entity_analysis(data)
    with session_scope() as session:
        session.add(
            EntityAnalysis(
                entity_id=entity_id,
                risk_score=clean["risk_score"],
                sentiment_trend=clean["sentiment_trend"],
                top_drivers=clean["top_drivers"],
                summary=clean["summary"],
                stance=clean["stance"],
                conviction=clean["conviction"],
                what_to_verify=clean["what_to_verify"],
                invalidation=clean["invalidation"],
                articles_considered=considered,
                avg_sentiment=avg_sentiment,
            )
        )
        session.flush()
        # Geçmiş korunur ama DB şişmesin: en yeni 100 dışındaki eski kayıtları temizle.
        stale = session.scalars(
            select(EntityAnalysis.id)
            .where(EntityAnalysis.entity_id == entity_id)
            .order_by(EntityAnalysis.created_at.desc())
            .offset(MAX_ANALYSIS_HISTORY)
        ).all()
        if stale:
            session.execute(delete(EntityAnalysis).where(EntityAnalysis.id.in_(stale)))


# ------------------------- Paralel orkestrasyon ------------------------- #
async def analyze_all_async(
    client: ClaudeClient,
    progress_cb=None,
) -> AnalyzeTotals:
    """Aktif tüm entity'ler için ön-filtre + paralel analiz + değerlendirme.

    progress_cb(done, total): her entity tamamlandığında çağrılır (ilerleme için).
    """
    settings = get_settings()
    batch_size = max(1, settings.batch_size)
    max_articles = max(1, settings.max_articles_per_entity)
    concurrency = max(1, settings.analysis_concurrency)

    totals = AnalyzeTotals()

    # --- Aşama 1: ön-filtre + batch listesi (DB, tek thread) ---
    entity_tasks: list[dict] = []
    with session_scope() as session:
        entities = session.scalars(
            select(Entity).where(Entity.active.is_(True))
        ).all()
        for e in entities:
            payload, pre = _prefilter(session, e, max_articles)
            totals.prefiltered += pre
            batches = [payload[i : i + batch_size] for i in range(0, len(payload), batch_size)]
            entity_tasks.append(
                {
                    "id": e.id, "name": e.name, "query": e.query, "type": e.type,
                    "language": e.language, "batches": batches,
                }
            )
        # session çıkışında prefiltered işaretleri commit edilir.

    total = len(entity_tasks)
    done = 0
    if progress_cb:
        progress_cb(done, total)

    sem = asyncio.Semaphore(concurrency)
    db_lock = asyncio.Lock()

    async def _call(tool, user, max_tokens):
        """Semaphore altında tek Claude çağrısı (sync istemci → to_thread)."""
        async with sem:
            return await asyncio.to_thread(
                client.call_tool,
                system=SYSTEM_PROMPT,
                user=user,
                tool=tool,
                max_tokens=max_tokens,
            )

    async def _run_batch(t: dict, b: list[dict]):
        user = build_article_batch_prompt(t["name"], t["query"], t["type"], b, t["language"])
        try:
            return await _call(ARTICLE_ANALYSIS_TOOL, user, 4096)
        except ClaudeError as exc:
            totals.warnings.append(f"[{t['name']}] makale batch atlandı: {exc}")
            return None

    async def _process_entity(t: dict):
        nonlocal done
        # 1) Makale batch'leri — hepsi paralel (global semaphore ile sınırlı).
        #    Batch'ler hem entity içinde hem entity'ler arası eşzamanlı çalışır;
        #    aynı anda en fazla `concurrency` çağrı olur.
        raw = await asyncio.gather(*[_run_batch(t, b) for b in t["batches"]])
        batch_datas: list[dict] = [d for d in raw if d]

        # 2) Sonuçları yaz (DB kilidi altında, sırayla).
        async with db_lock:
            applied = await asyncio.to_thread(_apply_article_results, t["id"], batch_datas)
        totals.analyzed += applied["analyzed"]
        totals.discarded += applied["discarded"]

        # 3) Değerlendirme payload'ını + fiyat bağlamını oku (DB), Claude çağır, yaz.
        async with db_lock:
            payload = await asyncio.to_thread(_read_assessment_payload, t["id"])
            price_ctx = await asyncio.to_thread(price_context_for, t["id"])
        if payload:
            user = build_entity_prompt(
                t["name"], t["query"], t["type"], payload, price=price_ctx, language=t["language"]
            )
            try:
                adata = await _call(ENTITY_ANALYSIS_TOOL, user, 2000)
                async with db_lock:
                    await asyncio.to_thread(
                        _write_assessment, t["id"], adata, len(payload), _avg_sentiment(payload)
                    )
                totals.entity_assessments += 1
            except ClaudeError as exc:
                totals.warnings.append(f"[{t['name']}] değerlendirme başarısız: {exc}")

        done += 1
        if progress_cb:
            progress_cb(done, total)

    # Tüm entity'ler eşzamanlı; Claude çağrıları semaphore ile sınırlı.
    await asyncio.gather(
        *[_process_entity(t) for t in entity_tasks], return_exceptions=False
    )

    # Bakım: tablo şişmesin diye eski/az anılan önerileri temizle.
    async with db_lock:
        await asyncio.to_thread(prune_stale_suggestions)

    return totals


def analyze_entity_sync(entity_id: int, client: ClaudeClient) -> AnalyzeTotals:
    """CLI/test için tek entity'yi senkron analiz eder (ön-filtre + batch + değerlendirme)."""
    settings = get_settings()
    batch_size = max(1, settings.batch_size)
    max_articles = max(1, settings.max_articles_per_entity)
    totals = AnalyzeTotals()

    with session_scope() as session:
        entity = session.get(Entity, entity_id)
        if entity is None:
            return totals
        name, query, etype, lang = entity.name, entity.query, entity.type, entity.language
        payload, pre = _prefilter(session, entity, max_articles)
        totals.prefiltered += pre

    batches = [payload[i : i + batch_size] for i in range(0, len(payload), batch_size)]
    batch_datas: list[dict] = []
    for b in batches:
        user = build_article_batch_prompt(name, query, etype, b, lang)
        try:
            batch_datas.append(
                client.call_tool(
                    system=SYSTEM_PROMPT, user=user, tool=ARTICLE_ANALYSIS_TOOL, max_tokens=4096
                )
            )
        except ClaudeError as exc:
            totals.warnings.append(f"[{name}] makale batch atlandı: {exc}")

    applied = _apply_article_results(entity_id, batch_datas)
    totals.analyzed += applied["analyzed"]
    totals.discarded += applied["discarded"]

    payload2 = _read_assessment_payload(entity_id)
    if payload2:
        user = build_entity_prompt(
            name, query, etype, payload2, price=price_context_for(entity_id), language=lang
        )
        try:
            adata = client.call_tool(
                system=SYSTEM_PROMPT, user=user, tool=ENTITY_ANALYSIS_TOOL, max_tokens=2000
            )
            _write_assessment(entity_id, adata, len(payload2), _avg_sentiment(payload2))
            totals.entity_assessments += 1
        except ClaudeError as exc:
            totals.warnings.append(f"[{name}] değerlendirme başarısız: {exc}")

    return totals
