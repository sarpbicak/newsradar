"""SQLAlchemy motoru + oturum (session) fabrikası."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_settings = get_settings()

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
    _ensure_column("articles", "prefilter_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("entity_analyses", "avg_sentiment", "FLOAT")
    _ensure_column("entity_analyses", "headline_verdict", "TEXT")
    _ensure_column("entity_analyses", "ai_take", "TEXT")
    _ensure_column("entities", "language", "VARCHAR(5) NOT NULL DEFAULT 'en'")
    _ensure_column("suggestions", "source_language", "VARCHAR(5) NOT NULL DEFAULT 'en'")
    _ensure_column("suggestions", "country", "VARCHAR(60)")
    _ensure_column("suggestions", "exchange", "VARCHAR(60)")
    _ensure_column("suggestions", "why_relevant", "TEXT")
    _ensure_column("analyst_snapshots", "target_consensus", "FLOAT")


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
    """FastAPI bağımlılığı (Depends) — istek başına oturum verir."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
