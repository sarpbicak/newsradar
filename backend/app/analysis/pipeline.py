"""Claude analiz hattı.

Akış:
  analyze_entity(session, entity):
    1. Bu entity'nin analiz EDİLMEMİŞ makalelerini al (analyzed=False).
    2. 10'arlı gruplar halinde Claude'a gönder (token tasarrufu), makale-başı JSON al.
    3. Sonuçları makalelere yaz; relevance < 0.3 olanlar elenir (silinir).
    4. Analiz edilmiş son ~N makaleyle entity-başı toplu değerlendirme üret ve kaydet.

Dayanıklılık: bir batch veya entity hata verirse loglanır ve gerisi devam eder —
tek bir API hatası tüm işi çökertmez.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Article, Entity, EntityAnalysis
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

BATCH_SIZE = 10          # makale-başı çağrı başına en fazla makale
AGGREGATE_LOOKBACK = 20  # entity değerlendirmesinde kaç son makale bağlam olarak verilir


@dataclass
class AnalyzeResult:
    """Bir entity için analiz özeti."""

    entity_id: int
    entity_name: str
    analyzed: int = 0            # makale-başı analiz edilen
    discarded: int = 0          # relevance < eşik → elenen
    entity_assessment: bool = False  # entity-başı değerlendirme üretildi mi
    warnings: list[str] = field(default_factory=list)


def analyze_entity(
    session: Session,
    entity: Entity,
    client: ClaudeClient | None = None,
) -> AnalyzeResult:
    """Bir entity için makale-başı + entity-başı analizi çalıştırır."""
    result = AnalyzeResult(entity_id=entity.id, entity_name=entity.name)
    client = client or ClaudeClient()

    # 1) Analiz edilmemiş makaleler (asla aynı makaleye iki kez ödeme yapma).
    pending: list[Article] = list(
        session.scalars(
            select(Article)
            .where(Article.entity_id == entity.id, Article.analyzed.is_(False))
            .order_by(Article.published_at.desc().nullslast())
        ).all()
    )

    # 2-3) Makale-başı analiz, 10'arlı gruplar halinde.
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        try:
            _analyze_batch(session, entity, batch, client, result)
        except ClaudeError as exc:
            msg = f"Makale batch analizi başarısız (atlandı): {exc}"
            logger.warning(msg)
            result.warnings.append(msg)
            # Bu batch analiz edilemedi; makaleler analyzed=False kalır (sonra tekrar denenir).

    # autoflush=False olduğundan, aşağıdaki entity sorgusunun makale-başı
    # değişiklikleri (analyzed=True, silmeler) görmesi için önce flush et.
    session.flush()

    # 4) Entity-başı toplu değerlendirme (analiz edilmiş, ilgili makalelerden).
    try:
        _assess_entity(session, entity, client, result)
    except ClaudeError as exc:
        msg = f"Entity değerlendirmesi başarısız: {exc}"
        logger.warning(msg)
        result.warnings.append(msg)

    session.flush()
    return result


def _analyze_batch(
    session: Session,
    entity: Entity,
    batch: list[Article],
    client: ClaudeClient,
    result: AnalyzeResult,
) -> None:
    """Tek bir makale grubunu analiz eder ve sonuçları yazar."""
    payload = [
        {"id": a.id, "title": a.title, "source": a.source, "description": a.description}
        for a in batch
    ]
    user = build_article_batch_prompt(entity.name, entity.query, entity.type, payload)
    data = client.call_tool(
        system=SYSTEM_PROMPT,
        user=user,
        tool=ARTICLE_ANALYSIS_TOOL,
        max_tokens=4096,
    )

    by_id = {a.id: a for a in batch}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for raw in data.get("analyses", []):
        try:
            clean = sanitize_article_analysis(raw)
        except (KeyError, ValueError, TypeError):
            continue
        article = by_id.get(clean["id"])
        if article is None:
            continue
        if clean["relevance"] < RELEVANCE_THRESHOLD:
            # Alakasız: makaleyi ele (sil) — gürültüyü panelde tutma.
            session.delete(article)
            result.discarded += 1
            continue
        article.sentiment = clean["sentiment"]
        article.event_type = clean["event_type"]
        article.risk_flags = clean["risk_flags"]
        article.impact_horizon = clean["impact_horizon"]
        article.relevance = clean["relevance"]
        article.rationale = clean["rationale"]
        article.analyzed = True
        article.analyzed_at = now
        result.analyzed += 1


def _assess_entity(
    session: Session,
    entity: Entity,
    client: ClaudeClient,
    result: AnalyzeResult,
) -> None:
    """Analiz edilmiş son makalelerden entity-başı değerlendirme üretir ve kaydeder."""
    analyzed_articles: list[Article] = list(
        session.scalars(
            select(Article)
            .where(Article.entity_id == entity.id, Article.analyzed.is_(True))
            .order_by(Article.published_at.desc().nullslast())
            .limit(AGGREGATE_LOOKBACK)
        ).all()
    )
    if not analyzed_articles:
        return  # değerlendirilecek analiz yok

    payload = [
        {
            "title": a.title,
            "sentiment": a.sentiment or 0.0,
            "event_type": a.event_type or "other",
            "impact_horizon": a.impact_horizon or "short",
            "risk_flags": a.risk_flags or [],
            "rationale": a.rationale or "",
        }
        for a in analyzed_articles
    ]
    user = build_entity_prompt(entity.name, entity.query, entity.type, payload)
    data = client.call_tool(
        system=SYSTEM_PROMPT,
        user=user,
        tool=ENTITY_ANALYSIS_TOOL,
        max_tokens=2000,
    )
    clean = sanitize_entity_analysis(data)

    session.add(
        EntityAnalysis(
            entity_id=entity.id,
            risk_score=clean["risk_score"],
            sentiment_trend=clean["sentiment_trend"],
            top_drivers=clean["top_drivers"],
            summary=clean["summary"],
            stance=clean["stance"],
            conviction=clean["conviction"],
            what_to_verify=clean["what_to_verify"],
            invalidation=clean["invalidation"],
            articles_considered=len(analyzed_articles),
        )
    )
    result.entity_assessment = True


def analyze_all(session: Session, client: ClaudeClient | None = None) -> list[AnalyzeResult]:
    """Aktif tüm entity'ler için analizi çalıştırır (tek entity hatası hattı durdurmaz)."""
    client = client or ClaudeClient()
    entities = session.scalars(select(Entity).where(Entity.active.is_(True))).all()
    results: list[AnalyzeResult] = []
    for e in entities:
        try:
            results.append(analyze_entity(session, e, client))
        except Exception as exc:  # noqa: BLE001 — bir entity çökse bile devam et
            logger.exception("Entity analizi çöktü: %s", e.name)
            r = AnalyzeResult(entity_id=e.id, entity_name=e.name)
            r.warnings.append(f"Beklenmeyen hata: {exc}")
            results.append(r)
    return results
