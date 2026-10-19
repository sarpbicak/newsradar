"""Haber çekme + dedupe + kalıcılaştırma servisi.

`fetch_for_entity` bir entity için sağlayıcıdan haberleri çeker, URL hash'e göre
tekrarları eler (DB'de zaten olanları atlar) ve yeni makaleleri kaydeder.
Tek bir kaynak hatası hattı çökertmez: uyarı toplanır, işlem devam eder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import Article, Entity, url_hash
from .messages import msg, render
from .providers import get_provider_for
from .quota import newsapi_usage, record_call

# Manuel yenilemede keyword entity bu kadar süre içinde çekildiyse NewsAPI'ye gidilmez.
MANUAL_FRESH_HOURS = 2

logger = logging.getLogger("newsradar.ingest")


@dataclass
class IngestResult:
    """Bir entity için çekme özeti."""

    entity_id: int
    entity_name: str
    fetched: int = 0          # sağlayıcıdan gelen toplam
    new_articles: list[Article] = field(default_factory=list)
    duplicates: int = 0       # zaten DB'de olan
    warnings: list[dict] = field(default_factory=list)  # GERÇEK sorunlar — messages.msg(...)
    infos: list[dict] = field(default_factory=list)     # NORMAL bilgi (tazelik/kota atlaması)

    @property
    def new_count(self) -> int:
        return len(self.new_articles)



def _quota_msg(usage: dict) -> dict:
    return msg("newsapi_quota", used=usage["used"], limit=usage["limit"],
               hours=usage["reset_in_hours"])

def _recently_fetched(session: Session, entity: Entity, hours: int) -> bool:
    """Bu entity için son çekim `hours` saatten yeni mi (tazelik kontrolü)."""
    latest = session.scalar(
        select(func.max(Article.fetched_at)).where(Article.entity_id == entity.id)
    )
    if latest is None:
        return False
    return latest >= datetime.now(timezone.utc) - timedelta(hours=hours)


def fetch_for_entity(
    session: Session,
    entity: Entity,
    lookback_hours: int | None = None,
    manual: bool = False,
) -> IngestResult:
    """Bir entity için haberleri çeker, dedupe eder, yenileri kaydeder.

    manual=True (elle Yenile): keyword entity son 2 saatte çekildiyse NewsAPI'ye
    hiç gidilmez (kota korunur). Ticker (Finnhub) kotası bol → her zaman çekilir.
    NewsAPI kotası dolduysa çekme atlanır ve anlaşılır mesaj döner.
    """
    settings = get_settings()
    hours = lookback_hours if lookback_hours is not None else settings.lookback_hours
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = IngestResult(entity_id=entity.id, entity_name=entity.name)

    provider = get_provider_for(entity)
    if provider is None:
        result.warnings.append(msg("no_provider", type=entity.type))
        return result

    is_newsapi = provider.name == "newsapi"
    if is_newsapi and provider.is_available():
        # Tazelik: manuel yenilemede taze veri varsa NewsAPI'ye gitme.
        if manual and _recently_fetched(session, entity, MANUAL_FRESH_HOURS):
            # NORMAL davranış (kota koruması) → info, uyarı DEĞİL.
            result.infos.append(msg("news_fresh_skip", hours=MANUAL_FRESH_HOURS))
            logger.info("[%s] NewsAPI atlandı: taze veri", entity.name)
            return result
        # Kota: dolduysa hiç çağırma (NORMAL kota koruması → info).
        usage = newsapi_usage(session)
        if usage["exhausted"]:
            m = _quota_msg(usage)
            result.infos.append(m)
            logger.info("[%s] %s", entity.name, render(m))
            return result

    outcome = provider.fetch(entity, since)

    # NewsAPI'ye gerçekten gidildiyse kotadan düş; ham 429'u anlaşılır mesaja çevir.
    if is_newsapi and provider.is_available():
        record_call(session, "newsapi")
        w = outcome.warning or {}
        p = w.get("params", {})
        if (w.get("code") == "http_error" and p.get("status") == 429) or (
            w.get("code") == "newsapi_status" and "ratelimited" in str(p.get("message", "")).lower()
        ):
            outcome.warning = _quota_msg(newsapi_usage(session))

    if outcome.warning:
        # NewsAPI kota mesajı NORMAL (kota koruması) → info; diğerleri gerçek hata → warning.
        if outcome.warning.get("code") == "newsapi_quota":
            result.infos.append(outcome.warning)
        else:
            result.warnings.append(outcome.warning)
    result.fetched = len(outcome.articles)

    # Bu entity için mevcut url_hash'leri tek sorguda al (dedupe).
    existing: set[str] = set(
        session.scalars(
            select(Article.url_hash).where(Article.entity_id == entity.id)
        ).all()
    )
    # Aynı çekmede tekrar eden URL'leri de ele.
    seen_this_batch: set[str] = set()

    pending: list[Article] = []
    for fa in outcome.articles:
        h = url_hash(fa.url)
        if h in existing or h in seen_this_batch:
            result.duplicates += 1
            continue
        seen_this_batch.add(h)
        article = Article(
            entity_id=entity.id,
            url=fa.url,
            url_hash=h,
            title=fa.title,
            source=fa.source,
            description=fa.description,
            image_url=fa.image_url,
            published_at=_utc(fa.published_at),
            provider=outcome.provider,
        )
        session.add(article)
        pending.append(article)

    # Entity başına commit: kısmi ilerleme korunur (bir sonraki entity'de yazma
    # hatası olsa bile buraya kadar çekilenler kalıcı olur). Bu entity'nin
    # yazması patlarsa (ör. 'database is locked'), onu atlayıp diğerlerine devam
    # ederiz — tek entity hatası tüm yenilemeyi çökertmez.
    try:
        session.flush()   # id'leri doldur
        session.commit()  # bu entity'nin makalelerini kalıcılaştır
        result.new_articles.extend(pending)
    except SQLAlchemyError as exc:
        session.rollback()
        result.new_articles.clear()
        result.warnings.append(msg("db_write_error", error=exc.__class__.__name__))
        logger.warning("[%s] yazma hatası, entity atlandı: %s", entity.name, exc)

    # Teşhis: her entity için sağlayıcı/çekme sonucu tek satırda loglanır. Böylece
    # canlıda (Render logs) "AMD 0 haber mi çekiyor" doğrudan görülebilir.
    logger.info(
        "[%s] sağlayıcı=%s çekilen=%d yeni=%d tekrar=%d%s",
        entity.name, outcome.provider, result.fetched, result.new_count,
        result.duplicates,
        f" UYARI: {'; '.join(render(w) for w in result.warnings)}" if result.warnings else "",
    )
    return result


def fetch_all(
    session: Session,
    lookback_hours: int | None = None,
    manual: bool = False,
    entity_ids: set[int] | None = None,
    on_entity=None,
) -> list[IngestResult]:
    """Aktif entity'ler için haberleri çeker (manual: elle Yenile'de akıllı davran).

    entity_ids verilirse yalnızca o entity'ler (kişisel elle yenileme); None → tüm aktif.
    on_entity(entity_id, name, state): ilerleme bildirimi — state "start" | "done".
    """
    q = select(Entity).where(Entity.active.is_(True))
    if entity_ids is not None:
        q = q.where(Entity.id.in_(entity_ids))
    entities = session.scalars(q).all()
    results = []
    for e in entities:
        if on_entity:
            on_entity(e.id, e.name, "start")
        results.append(fetch_for_entity(session, e, lookback_hours, manual))
        if on_entity:
            on_entity(e.id, e.name, "done")
    return results


def _utc(dt: datetime | None) -> datetime | None:
    """UTC-aware datetime'a çevirir (naive girdi UTC kabul edilir; DB tipi UTCDateTime)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
