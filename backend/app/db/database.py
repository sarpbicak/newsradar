"""SQLAlchemy motoru + oturum (session) fabrikası."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_settings = get_settings()
logger = logging.getLogger("newsradar.db")

# SQLite + FastAPI (çok thread'li) için check_same_thread=False gerekli.
# timeout=30: kilit meşgulken 30 sn beklenir, hemen "database is locked" atmaz.
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    """Her yeni bağlantıda WAL + busy_timeout ayarla.

    WAL modu okuma ile yazmanın birbirini bloke etmesini büyük ölçüde önler;
    busy_timeout ise kilit meşgulken 30 sn boyunca yeniden dener ('database is
    locked' hatasının başlıca sebebi eşzamanlı yazma + kısa/yok bekleme süresidir).
    """
    cursor = dbapi_conn.cursor()
    # Önce busy_timeout: WAL'a geçiş başka bir bağlantının kilidine takılırsa
    # 30 sn boyunca yeniden denesin (aksi halde geçişin kendisi 'locked' atar).
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Tabloları oluşturur (yoksa) + hafif kolon migration'ı. Açılışta/seed'de çağrılır."""
    from . import models  # noqa: F401 — modelleri Base'e kaydeder

    models.Base.metadata.create_all(bind=engine)
    # create_all mevcut tabloya kolon EKLEMEZ; eski DB'ler için elle ekle.
    _ensure_column("articles", "prefiltered", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("articles", "source_count", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column("articles", "prefilter_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("articles", "expired", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("entity_analyses", "avg_sentiment", "FLOAT")
    _ensure_column("entity_analyses", "headline_verdict", "TEXT")
    _ensure_column("entity_analyses", "ai_take", "TEXT")
    _ensure_column("entity_analyses", "driver_directions", "JSON")
    _ensure_column("entities", "language", "VARCHAR(5) NOT NULL DEFAULT 'en'")
    _ensure_column("suggestions", "source_language", "VARCHAR(5) NOT NULL DEFAULT 'en'")
    _ensure_column("suggestions", "country", "VARCHAR(60)")
    _ensure_column("suggestions", "exchange", "VARCHAR(60)")
    _ensure_column("suggestions", "why_relevant", "TEXT")
    _ensure_column("analyst_snapshots", "target_consensus", "FLOAT")
    _ensure_column("users", "guide_dismissed", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("users", "tutorial_done", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("users", "last_active_at", "DATETIME")
    _ensure_column("users", "is_anonymous", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("users", "device_id_hash", "VARCHAR(64)")
    _ensure_column("users", "language", "VARCHAR(5) NOT NULL DEFAULT 'tr'")
    # Analiz kayıtlarının dili (tr/en); eski kayıtlar tr üretildi.
    _ensure_column("entity_analyses", "language", "VARCHAR(5) NOT NULL DEFAULT 'tr'")
    # LLM kullanımı çağrı başına: model/amaç/cache token'ları/USD maliyet.
    _ensure_column("llm_usage", "model", "VARCHAR(64)")
    _ensure_column("llm_usage", "purpose", "VARCHAR(16)")
    _ensure_column("llm_usage", "cache_creation_tokens", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("llm_usage", "cache_read_tokens", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("llm_usage", "cost_usd", "FLOAT NOT NULL DEFAULT 0")
    # Kısa görünen ad + bilinen uzun adlar için idempotent doldurma (yalnızca NULL'lar).
    _ensure_column("entities", "display_name", "VARCHAR(200)")
    from ..entity_names import backfill_display_names

    with engine.begin() as conn:
        backfill_display_names(conn)


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """SQLite: kolon yoksa ekler (idempotent basit migration)."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


@contextmanager
def session_scope() -> Iterator[Session]:
    """CLI/servis için commit/rollback'i yöneten oturum bağlamı."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI bağımlılığı — istek başına oturum; route gövdesi bitince commit eder.

    ROUTE'LARDA HER ZAMAN ``Depends(get_db, scope="function")`` İLE KULLANILIR.
    Varsayılan (scope="request") yield-bağımlılığında yield sonrası kod YANIT
    GÖNDERİLDİKTEN SONRA çalışır: istemci 200/204 alır ama commit henüz olmamıştır →
    hemen ardından gelen istek eski veriyi görür (ör. silinen kullanıcının token'ı
    bir süre daha 200 alır) ve commit başarısız olursa istemciye yine "başarılı"
    denmiş olur. scope="function" ile yield sonrası kod route fonksiyonu (ve yanıt
    serileştirmesi) bittikten hemen sonra, yanıt GÖNDERİLMEDEN önce çalışır.

    Önbellek anahtarı scope'u içerir: aynı istekte get_current_user ile route'un AYNI
    oturumu paylaşması için tüm kullanımlar aynı scope'u kullanmalı
    (test_commit_timing bunu tüm route'lar için denetler).

    Commit başarısızsa rollback + 500 (genel mesaj; ayrıntı yalnızca sunucu logunda).
    Route bir istisna fırlatırsa (HTTPException dahil) değişiklikler geri alınır.

    SSE/streaming uçları: oturum, akış BAŞLAMADAN commit edilip kapanır → akış
    üreteci bu oturumu ya da ondan gelen ORM nesnelerinin tembel alanlarını
    KULLANMAMALI; akış sırasında DB gerekiyorsa kendi ``session_scope()``'unu açmalı
    (bkz. routes_chat).
    """
    session = SessionLocal()
    try:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        try:
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("İstek sonu commit başarısız — değişiklikler geri alındı.")
            raise HTTPException(
                status_code=500,
                detail="Değişiklik kaydedilemedi, lütfen tekrar deneyin.",
            ) from exc
    finally:
        session.close()
