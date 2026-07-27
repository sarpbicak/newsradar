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
import logging
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
        # diagnose ile AYNI geniş eşleşmeyi kullan — hangi entity'ye çözüldüğü
        # ve BİRDEN ÇOK eşleşme (duplikasyon) olup olmadığı görünsün.
        q = args.query.strip()
        matches = session.scalars(
            select(Entity).where(Entity.query == q).order_by(Entity.id)
        ).all()
        if not matches:
            # Tam eşleşme yoksa geniş ara (gizli karakter/duplikasyon ipucu).
            like = f"%{q.lstrip('$').strip()}%"
            alt = session.scalars(
                select(Entity).where(Entity.name.ilike(like) | Entity.query.ilike(like))
            ).all()
            if alt:
                print(f"'{q}' TAM eşleşmedi ama benzer entity(ler) var — query'de gizli "
                      f"karakter olabilir. `diagnose {q}` ile kontrol edin:")
                for e in alt:
                    print(f"   #{e.id} {e.name!r} [{e.type}:{e.query!r}]")
            else:
                print(f"'{q}' izleme listesinde yok.")
            sys.exit(1)
        if len(matches) > 1:
            print(f"⚠ '{q}' ile {len(matches)} entity eşleşti (duplikasyon):")
            for e in matches:
                print(f"   #{e.id} {e.name!r} [{e.type}:{e.query!r}]")
        entity = matches[0]
        entity_id = entity.id
        print(f"→ analiz edilen entity: #{entity.id} {entity.name!r} "
              f"[{entity.type}:{entity.query!r}] (query len={len(entity.query)})")

    totals = analyze_entity_sync(entity_id, client)
    print(f"\n=== {args.query} analizi (entity #{entity_id}) ===")
    # KRİTİK: _prefilter'ın BU analiz yolunda batch'e kaç makale seçtiği. diagnose'un
    # gösterdiği sayı ile karşılaştır — farklıysa iki komut farklı entity'ye çözülüyor.
    print(f"  Batch'e giren makale (bu yolda _prefilter seçimi): {totals.selected}")
    print(f"  Ön-filtrede elenen: {totals.prefiltered} | Analiz edilen: {totals.analyzed} | "
          f"Elenen (alakasız): {totals.discarded} | "
          f"Değerlendirme: {'evet' if totals.entity_assessments else 'hayır'}")
    print(f"  [teşhis] Claude döndürdü: {totals.returned} | eşleşmeyen id: {totals.unmatched}")

    # Analiz 0 çıktıysa: SEBEBİ tam burada ayrıştır ve hangi entity'de makale olduğunu göster.
    if totals.analyzed == 0:
        if totals.selected == 0:
            print("\n  ⚠ SEBEP: _prefilter bu entity için 0 makale seçti (batch boş → "
                  "Claude hiç çağrılmadı). Yani bu entity'de bekleyen makale YOK.")
            # Aynı ad/query ile makalesi OLAN başka entity var mı? (çözüm farkını göster.)
            # Not: Article/Entity modül başında import edildi — burada YENİDEN import ETME,
            # yoksa fonksiyon kapsamında yerelleşir ve aşağıdaki JSON bölümü UnboundLocalError verir.
            like = f"%{args.query.strip().lstrip('$').strip()}%"
            cands = db_scan_pending(client_query=args.query, like=like)
            if cands:
                print("  → Ama şu entity(ler)de BEKLEYEN makale var — analyze YANLIŞ "
                      "entity'ye çözülmüş olabilir:")
                for cid, cname, ctype, cq, pend in cands:
                    marker = "  ← analyze bunu işledi" if cid == entity_id else ""
                    print(f"     #{cid} {cname!r} [{ctype}:{cq!r}] bekleyen={pend}{marker}")
                print("  Düzeltme: doğru entity'yi query'siyle analiz edin ya da fazla "
                      "(boş) entity'yi silin.")
        elif totals.returned == 0 and not totals.warnings:
            print("\n  ⚠ SEBEP: _prefilter %d makale seçti ve batch gönderildi AMA Claude "
                  "0 analiz döndürdü (hata da yok). Claude yanıtı boş — API/anahtar ya da "
                  "model sorunu olabilir; ANTHROPIC_API_KEY ve modeli kontrol edin." % totals.selected)
        elif totals.unmatched > 0:
            print(f"\n  ⚠ SEBEP: Claude {totals.unmatched} analizi bu entity'nin "
                  "makalelerine EŞLEŞMEYEN id ile döndürdü (sessizce kayboluyordu).")
        elif totals.discarded > 0:
            print(f"\n  ⚠ SEBEP: {totals.discarded} makale relevance<0.3 ile elendi "
                  "(Claude alakasız buldu).")
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


def db_scan_pending(client_query: str, like: str) -> list[tuple]:
    """query/ad ile eşleşen ve BEKLEYEN (analyzed=False, prefiltered=False) makalesi olan
    entity'leri döndürür: (id, name, type, query, pending_sayısı). Boş entity'ler hariç."""
    from sqlalchemy import func

    q = client_query.strip()
    out: list[tuple] = []
    with session_scope() as session:
        ents = session.scalars(
            select(Entity).where(
                (Entity.query == q) | Entity.name.ilike(like) | Entity.query.ilike(like)
            ).order_by(Entity.id)
        ).all()
        for e in ents:
            pend = session.scalar(
                select(func.count()).select_from(Article).where(
                    Article.entity_id == e.id,
                    Article.analyzed.is_(False),
                    Article.prefiltered.is_(False),
                )
            ) or 0
            if pend > 0:
                out.append((e.id, e.name, e.type, e.query, pend))
    return out


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Bir entity'nin analiz-takılması tanısı — CLAUDE ÇAĞIRMAZ, anında çalışır.

    Elle-eklenen ile öneri-eklenen entity arasındaki farkı + makale kırılımını +
    ön-filtrenin kaç makale seçeceğini gösterir. Render Shell için:
        python -m app.cli diagnose AMD
    """
    from sqlalchemy import func

    from .analysis.pipeline import _prefilter
    from .config import get_settings
    from .providers import get_provider_for

    init_db()
    q = args.query.strip()
    with session_scope() as session:
        # 1) Bu query ile EŞLEŞEN TÜM entity'ler (duplikasyon/tuhaf-query yakalamak için:
        #    tam, büyük/küçük harf duyarsız, $ önekli ve boşluklu varyantlar).
        like = f"%{q.lstrip('$').strip()}%"
        matches = session.scalars(
            select(Entity).where(
                (Entity.query == q) | (Entity.name.ilike(like)) | (Entity.query.ilike(like))
            ).order_by(Entity.id)
        ).all()
        if not matches:
            print(f"'{q}' ile eşleşen entity yok. Tam liste için: python -m app.cli status")
            return
        if len(matches) > 1:
            print(f"⚠ DİKKAT: '{q}' ile eşleşen {len(matches)} entity var (duplikasyon olabilir):")

        for e in matches:
            print(f"\n=== Entity #{e.id}: {e.name!r} ===")
            print(f"  type={e.type!r} query={e.query!r} language={e.language!r} "
                  f"active={e.active} created_at={e.created_at}")
            # repr ile gizli boşluk/$/kontrol karakterleri görünür olsun.
            print(f"  query repr (gizli karakter kontrolü): {e.query!r}  (len={len(e.query)})")

            # 2) Makale kırılımı — durum + kaynak + published_at null sayısı.
            def c(*conds):
                return session.scalar(select(func.count()).select_from(Article).where(
                    Article.entity_id == e.id, *conds)) or 0

            total = c()
            analyzed = c(Article.analyzed.is_(True))
            pre = c(Article.prefiltered.is_(True))
            pending = c(Article.analyzed.is_(False), Article.prefiltered.is_(False))
            null_pub = c(Article.published_at.is_(None))
            print(f"  makaleler: toplam={total} analiz={analyzed} elenen(pre)={pre} "
                  f"bekleyen={pending} | published_at NULL={null_pub}")
            # prefilter_version dağılımı (reconcile takılması için).
            ver_rows = session.execute(
                select(Article.prefilter_version, func.count())
                .where(Article.entity_id == e.id)
                .group_by(Article.prefilter_version)
            ).all()
            if ver_rows:
                print("  prefilter_version dağılımı:",
                      ", ".join(f"v{v}={n}" for v, n in ver_rows))
            prov_rows = session.execute(
                select(Article.provider, func.count())
                .where(Article.entity_id == e.id).group_by(Article.provider)
            ).all()
            if prov_rows:
                print("  sağlayıcı dağılımı:",
                      ", ".join(f"{p or '(boş)'}={n}" for p, n in prov_rows))

            # 3) Sağlayıcı + entity_filtered.
            provider = get_provider_for(e)
            print(f"  get_provider_for → {provider.name if provider else None} "
                  f"(entity_filtered={provider.entity_filtered if provider else 'N/A'})")

            # 4) analyze döngüsüne giriyor mu? (active filtresi)
            in_loop = e.active
            print(f"  analyze_all_async'e giriyor mu (active=True)? {'EVET' if in_loop else 'HAYIR — atlanır!'}")

            # 5) _prefilter Claude'suz kaç makale seçer? (gerçek fonksiyon).
            settings = get_settings()
            payload, would_pre = _prefilter(session, e, settings.max_articles_per_entity)
            print(f"  _prefilter şu an seçer: analize={len(payload)} yeni-eleme={would_pre}")
            if payload:
                print(f"    örnek seçilen id'ler: {[p['id'] for p in payload[:5]]}…")
            else:
                print("    ⚠ _prefilter 0 makale seçti → analiz edilecek makale YOK "
                      "(bekleyen makaleler varsa bu bir sorundur).")
        # rollback (prefilter yan etki yaratmasın — diagnose salt-okunur olmalı)
        session.rollback()


def cmd_fmp_check(args: argparse.Namespace) -> None:
    """FMP ücretsiz katmanı DOĞRULAMA — hedef fiyat uçları anahtarınla çalışıyor mu?

    Kullanım (FMP_API_KEY .env'de olmalı):  python -m app.cli fmp-check AMD
    Her ucun HTTP kodunu + örnek yanıtı + net hükmü basar. 200 + hedef verisi =
    ÇALIŞIYOR. 401/402/403 = anahtar geçersiz ya da uç ücretsiz katman dışı.
    """
    import httpx

    from .config import get_settings

    settings = get_settings()
    key = settings.fmp_api_key
    if not key:
        print("FMP_API_KEY tanımlı değil. backend/.env'e ekleyin:  FMP_API_KEY=...")
        print("Ücretsiz anahtar: https://site.financialmodelingprep.com/developer/docs")
        sys.exit(1)

    sym = args.symbol.upper().strip()
    # (insan-okur ad, URL, hangi alanları bekliyoruz)
    endpoints = [
        ("price-target-consensus (stable)",
         "https://financialmodelingprep.com/stable/price-target-consensus",
         {"symbol": sym}, "targetConsensus/targetHigh/targetLow"),
        ("price-target-consensus (v4)",
         "https://financialmodelingprep.com/api/v4/price-target-consensus",
         {"symbol": sym}, "targetConsensus/targetHigh/targetLow"),
        ("price-target-summary (stable)",
         "https://financialmodelingprep.com/stable/price-target-summary",
         {"symbol": sym}, "lastMonthAvgPriceTarget/lastQuarter..."),
        ("price-target (v4, bireysel)",
         "https://financialmodelingprep.com/api/v4/price-target",
         {"symbol": sym}, "bireysel analist hedefleri"),
        ("analyst-estimates (stable)",
         "https://financialmodelingprep.com/stable/analyst-estimates",
         {"symbol": sym}, "gelir/kazanç tahminleri"),
    ]

    print(f"FMP ücretsiz katman kontrolü — sembol: {sym}\n" + "=" * 60)
    any_target = False
    for name, url, params, expect in endpoints:
        p = {**params, "apikey": key}
        try:
            resp = httpx.get(url, params=p, timeout=20.0)
        except httpx.HTTPError as exc:
            print(f"\n▸ {name}\n   BAĞLANTI HATASI: {exc}")
            continue
        code = resp.status_code
        body = resp.text[:220].replace("\n", " ")
        verdict = "?"
        if code == 200:
            low = body.lower()
            if '"error' in low or "premium" in low or "exclusive" in low or "legacy" in low:
                verdict = "⚠ 200 ama içerik hata/premium uyarısı (kapsam dışı olabilir)"
            elif body.strip() in ("[]", "{}", ""):
                verdict = "⚠ boş yanıt (bu sembol için veri yok olabilir)"
            else:
                verdict = "✓ ÇALIŞIYOR"
                if "target" in low:
                    any_target = True
        elif code in (401,):
            verdict = "✗ 401 — anahtar geçersiz"
        elif code in (402, 403):
            verdict = "✗ %d — ücretsiz katman bu ucu KAPSAMIYOR (premium)" % code
        else:
            verdict = f"✗ HTTP {code}"
        print(f"\n▸ {name}  (beklenen: {expect})")
        print(f"   HTTP {code} — {verdict}")
        print(f"   yanıt: {body}")

    print("\n" + "=" * 60)
    if any_target:
        print("SONUÇ: ✓ Hedef fiyat uçlarından en az biri ÇALIŞIYOR — NewsRadar gerçek "
              "hedef fiyatı gösterebilir. Yenile'ye basınca AMD/NVDA hedefi dolacak.")
    else:
        print("SONUÇ: ✗ Hiçbir hedef fiyat ucu çalışmadı. Ücretsiz katman kapsamıyor "
              "olabilir — Sarp'a bildir, alternatif (Alpha Vantage) konuşalım. "
              "Bu durumda hedef fiyat GÖSTERİLMEZ (tavsiye/haber etkilenmez).")


def cmd_reconcile(_args: argparse.Namespace) -> None:
    """Eski ön-filtre sürümüyle elenmiş makaleleri yeniden değerlendirmeye açar."""
    from .analysis.pipeline import reconcile_prefilter

    init_db()
    n = reconcile_prefilter()
    print(f"Ön-filtre reconcile: {n} makale yeniden değerlendirmeye açıldı.")


def main() -> None:
    # CLI'de de analiz hattının [analiz] loglarını göster (entity-başı görünürlük).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # gürültü azalt
    parser = argparse.ArgumentParser(prog="newsradar-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Sağlayıcı anahtarları + izleme listesi").set_defaults(func=cmd_status)
    sub.add_parser(
        "reconcile", help="Eski ön-filtre sürümüyle elenen makaleleri yeniden aç"
    ).set_defaults(func=cmd_reconcile)

    p_diag = sub.add_parser(
        "diagnose", help="Bir entity'nin analiz-takılması tanısı (Claude'suz, anında)"
    )
    p_diag.add_argument("query", help="Entity query ya da adı (örn. AMD)")
    p_diag.set_defaults(func=cmd_diagnose)

    p_fmp = sub.add_parser(
        "fmp-check", help="FMP ücretsiz katmanı hedef fiyat uçlarını doğrula"
    )
    p_fmp.add_argument("symbol", nargs="?", default="AAPL", help="Sembol (örn. AMD). Vars: AAPL")
    p_fmp.set_defaults(func=cmd_fmp_check)

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
