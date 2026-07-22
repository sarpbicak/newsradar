"""Haber çekme + dedupe + kalıcılaştırma servisi.

`fetch_for_entity` bir entity için sağlayıcıdan haberleri çeker, URL hash'e göre
tekrarları eler (DB'de zaten olanları atlar) ve yeni makaleleri kaydeder.
Tek bir kaynak hatası hattı çökertmez: uyarı toplanır, işlem devam eder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import Article, Entity, url_hash
from .providers import get_provider_for

logger = logging.getLogger("newsradar.ingest")


@dataclass
class IngestResult:
    """Bir entity için çekme özeti."""

    entity_id: int
    entity_name: str
    fetched: int = 0          # sağlayıcıdan gelen toplam
    new_articles: list[Article] = field(default_factory=list)
    duplicates: int = 0       # zaten DB'de olan
    warnings: list[str] = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return len(self.new_articles)


def fetch_for_entity(
    session: Session,
    entity: Entity,
    lookback_hours: int | None = None,
) -> IngestResult:
    """Bir entity için haberleri çeker, dedupe eder, yenileri kaydeder."""
    settings = get_settings()
    hours = lookback_hours if lookback_hours is not None else settings.lookback_hours
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = IngestResult(entity_id=entity.id, entity_name=entity.name)

    provider = get_provider_for(entity)
    if provider is None:
        result.warnings.append(f"'{entity.type}' tipi için sağlayıcı yok.")
        return result

    outcome = provider.fetch(entity, since)
    if outcome.warning:
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
            published_at=_naive_utc(fa.published_at),
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
        result.warnings.append(
            f"yazma hatası, entity atlandı: {exc.__class__.__name__}"
        )
        logger.warning("[%s] yazma hatası, entity atlandı: %s", entity.name, exc)

    return result


def fetch_all(session: Session, lookback_hours: int | None = None) -> list[IngestResult]:
    """Aktif tüm entity'ler için haberleri çeker."""
    entities = session.scalars(
        select(Entity).where(Entity.active.is_(True))
    ).all()
    return [fetch_for_entity(session, e, lookback_hours) for e in entities]


def _naive_utc(dt: datetime | None) -> datetime | None:
    """SQLite DateTime kolonu için timezone'suz UTC datetime'a çevirir."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
