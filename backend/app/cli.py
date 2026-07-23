"""NewsRadar CLI — hattı adım adım test etmek için.

Kullanım:
  python -m app.cli status                 # sağlayıcı anahtarları + entity sayısı
  python -m app.cli fetch                   # tüm izleme listesi için haber çek + yazdır
  python -m app.cli fetch TSLA              # tek bir entity (query ile) için çek
  python -m app.cli fetch TSLA --hours 168  # geriye dönük pencereyi değiştir
  python -m app.cli analyze TSLA            # tek entity'yi Claude ile analiz et + JSON yazdır
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from .config import get_settings
from .db.database import init_db, session_scope
from .db.models import Article, Entity, EntityAnalysis
from .ingest import IngestResult, fetch_all, fetch_for_entity
from .providers import provider_status


def _print_result(r: IngestResult) -> None:
    print(f"\n=== {r.entity_name} (id={r.entity_id}) ===")
    print(f"  Çekilen: {r.fetched} | Yeni: {r.new_count} | Tekrar: {r.duplicates}")
    for w in r.warnings:
        print(f"  ⚠ {w}")
    for a in r.new_articles[:15]:
        date = a.published_at.strftime("%Y-%m-%d %H:%M") if a.published_at else "tarih yok"
        print(f"   • [{date}] {a.title[:90]}")
        print(f"     {a.source} — {a.url[:80]}")
    if r.new_count > 15:
        print(f"     … ve {r.new_count - 15} makale daha")


def cmd_status(_args: argparse.Namespace) -> None:
    settings = get_settings()
    init_db()
    print("Sağlayıcı anahtarları:")
    for name, ok in provider_status().items():
        print(f"  {name:10}: {'✓ var' if ok else '✗ yok (atlanacak)'}")
    print(f"  {'claude':10}: {'✓ var' if settings.claude_available else '✗ yok'}")
    with session_scope() as session:
        entities = session.scalars(select(Entity)).all()
        print(f"\nİzleme listesi: {len(entities)} entity")
        for e in entities:
            print(f"  #{e.id} {e.name} [{e.type}:{e.query}]")


def cmd_fetch(args: argparse.Namespace) -> None:
    init_db()
    with session_scope() as session:
        if args.query:
            entity = session.scalar(
                select(Entity).where(Entity.query == args.query)
            )
            if not entity:
                print(f"'{args.query}' izleme listesinde yok. Önce: python -m app.seed")
                sys.exit(1)
            results = [fetch_for_entity(session, entity, args.hours)]
        else:
            results = fetch_all(session, args.hours)
            if not results:
                print("İzleme listesi boş. Önce: python -m app.seed")
                return
        total_new = sum(r.new_count for r in results)
        for r in results:
            _print_result(r)
        print(f"\nToplam yeni makale: {total_new}")


def cmd_analyze(args: argparse.Namespace) -> None:
    from .analysis.claude_client import ClaudeClient, MissingAPIKeyError
    from .analysis.pipeline import analyze_entity_sync

    init_db()
    try:
        client = ClaudeClient()
    except MissingAPIKeyError as exc:
        print(exc)
        sys.exit(1)

    with session_scope() as session:
        entity = session.scalar(select(Entity).where(Entity.query == args.query))
        if not entity:
            print(f"'{args.query}' izleme listesinde yok.")
            sys.exit(1)
        entity_id = entity.id

    totals = analyze_entity_sync(entity_id, client)
    print(f"\n=== {args.query} analizi ===")
    print(f"  Ön-filtrede elenen: {totals.prefiltered} | Analiz edilen: {totals.analyzed} | "
          f"Elenen (alakasız): {totals.discarded} | "
          f"Değerlendirme: {'evet' if totals.entity_assessments else 'hayır'}")
    for w in totals.warnings:
        print(f"  ⚠ {w}")

    with session_scope() as session:
        entity = session.scalar(select(Entity).where(Entity.query == args.query))
        print("\n--- Analiz edilmiş makaleler (JSON) ---")
        arts = session.scalars(
            select(Article).where(Article.entity_id == entity.id, Article.analyzed.is_(True))
        ).all()
        for a in arts[:10]:
            print(json.dumps({
                "title": a.title[:70],
                "sentiment": a.sentiment,
                "event_type": a.event_type,
                "risk_flags": a.risk_flags,
                "impact_horizon": a.impact_horizon,
                "relevance": a.relevance,
                "rationale": a.rationale,
            }, ensure_ascii=False, indent=2))

        latest = session.scalar(
            select(EntityAnalysis)
            .where(EntityAnalysis.entity_id == entity.id)
            .order_by(EntityAnalysis.created_at.desc())
        )
        if latest:
            print("\n--- Entity toplu değerlendirmesi (JSON) ---")
            print(json.dumps({
                "risk_score": latest.risk_score,
                "sentiment_trend": latest.sentiment_trend,
                "stance": latest.stance,
                "conviction": latest.conviction,
                "top_drivers": latest.top_drivers,
                "summary": latest.summary,
                "what_to_verify": latest.what_to_verify,
                "invalidation": latest.invalidation,
            }, ensure_ascii=False, indent=2))


def cmd_reconcile(_args: argparse.Namespace) -> None:
    """Eski ön-filtre sürümüyle elenmiş makaleleri yeniden değerlendirmeye açar."""
    from .analysis.pipeline import reconcile_prefilter

    init_db()
    n = reconcile_prefilter()
    print(f"Ön-filtre reconcile: {n} makale yeniden değerlendirmeye açıldı.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="newsradar-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Sağlayıcı anahtarları + izleme listesi").set_defaults(func=cmd_status)
    sub.add_parser(
        "reconcile", help="Eski ön-filtre sürümüyle elenen makaleleri yeniden aç"
    ).set_defaults(func=cmd_reconcile)

    p_fetch = sub.add_parser("fetch", help="Haber çek + yazdır")
    p_fetch.add_argument("query", nargs="?", help="Tek entity (query, örn. TSLA). Boşsa hepsi.")
    p_fetch.add_argument("--hours", type=int, default=None, help="Geriye dönük pencere (saat)")
    p_fetch.set_defaults(func=cmd_fetch)

    p_an = sub.add_parser("analyze", help="Tek entity'yi Claude ile analiz et")
    p_an.add_argument("query", help="Entity query (örn. TSLA)")
    p_an.set_defaults(func=cmd_analyze)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
