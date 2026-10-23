"""Varsayılan izleme listesini ekleyen seed script'i.

Çalıştır:  python -m app.seed
"""

from __future__ import annotations

from sqlalchemy import select

from .db.database import init_db, session_scope
from .db.models import Entity
from .entity_names import display_name_for

# (name, type, query)
DEFAULT_WATCHLIST = [
    ("Tesla", "ticker", "TSLA"),
    ("NVIDIA", "ticker", "NVDA"),
    ("Microsoft", "ticker", "MSFT"),
    ("Anthropic", "keyword", "Anthropic"),
    ("SpaceX", "keyword", "SpaceX"),
]


def seed() -> None:
    init_db()
    added, skipped = 0, 0
    with session_scope() as session:
        for name, type_, query in DEFAULT_WATCHLIST:
            exists = session.scalar(
                select(Entity).where(Entity.type == type_, Entity.query == query)
            )
            if exists:
                skipped += 1
                continue
            session.add(Entity(name=name, display_name=display_name_for(name),
                               type=type_, query=query))
            added += 1
    print(f"Seed tamam: {added} eklendi, {skipped} zaten vardı.")


if __name__ == "__main__":
    seed()
