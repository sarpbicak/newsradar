"""Canlı değerlendirme: N entity ile TAM yenileme (TR + EN) + otomatik kalite kontrolleri.

GERÇEK API çağrısı yapar (maliyet llm_usage'a yazılır ve raporda gösterilir). Yerel DB'nin
KOPYASI üzerinde çalışır — geliştirme verisi değişmez.

Kontroller (herhangi biri BAŞARISIZ → çıkış kodu 1):
  1. Şablon çöküşü: tüm headline_verdict'ler yan yana; aynı açılış (ilk 3 kelime) ve
     entity'ler arasında tekrar eden 3+ kelimelik öbekler raporlanır. Entity'lerin %50'sinden
     fazlası aynı açılışı ya da aynı öbeği paylaşıyorsa BAŞARISIZ. Yasaklı ifade
     (text_quality.BANNED_PHRASES) herhangi bir metin alanında geçerse BAŞARISIZ. risk_score:
     bir dilde entity'lerin %50'sinden fazlası aynı skorsa BAŞARISIZ.
  2. Yatırım tavsiyesi bariyeri: TR+EN tüm metin alanları + makale gerekçeleri taranır.
  3. Kesilme: yenileme boyunca TruncationError (log) sayısı.
  4. Türkçe karakter bozulması (mojibake / hiç ı-ş-ğ-İ olmaması).
  5. Kesik cümle: tüm metin alanları ve liste maddeleri . ! ? ile bitmeli.

Çalıştır (backend/ içinden):
  python -m evals.eval_refresh --db <kopya.db> --out evals/reports/refresh.md
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ENTITIES = "Tesla,NVIDIA,Microsoft,Anthropic,SpaceX"
_MOJIBAKE = re.compile(r"Ã.|Ä[±°ŸŞ]|Å[Ÿž]|�|\\u0[0-9a-f]{3}")
_TR_CHARS = set("ışğİŞĞıçöüÇÖÜ")


def _copy_db(src: Path, dst: Path) -> None:
    """WAL'lı SQLite'ı tutarlı kopyala (backup API)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)


class _LogCap(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.msgs: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.msgs.append((record.levelname, record.getMessage()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Çalışılacak DB kopyası (yoksa yerel DB'den kopyalanır)")
    ap.add_argument("--entities", default=DEFAULT_ENTITIES)
    ap.add_argument("--max-articles", default="40", help="Entity başına analiz tavanı (maliyet)")
    ap.add_argument("--budget", default="5.00", help="Bu koşu için günlük USD tavanı")
    ap.add_argument("--out", default="evals/reports/refresh.md")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        _copy_db(Path(__file__).resolve().parent.parent / "newsradar.db", db)
    os.environ.update(
        NEWSRADAR_DB=str(db), NEWSRADAR_LLM_PROVIDER="anthropic", NEWSRADAR_SCHEDULER="off",
        NEWSRADAR_SEED_ON_START="off", NEWSRADAR_MAX_ARTICLES_PER_ENTITY=args.max_articles,
        NEWSRADAR_DAILY_BUDGET_USD=args.budget,
    )

    from sqlalchemy import func, select

    from app.analysis.advice_guard import scan_assessment, scan_text
    from app.analysis.text_quality import banned_phrase_hits, repeated_ngrams, unterminated_fields
    from app.config import get_settings
    from app.db.database import init_db, session_scope
    from app.db.models import Article, Entity, EntityAnalysis, LlmUsage
    from app.refresh import run_refresh

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    cap = _LogCap()
    logging.getLogger("newsradar").addHandler(cap)

    init_db()
    s = get_settings()
    names = [n.strip() for n in args.entities.split(",") if n.strip()]
    with session_scope() as ses:
        ents = {e.name: e.id for e in ses.scalars(select(Entity).where(Entity.name.in_(names)))}
    missing = [n for n in names if n not in ents]
    if missing:
        print(f"Entity bulunamadı: {missing}")
        return 2

    started = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"Yenileme başlıyor: {names} · makale modeli={s.article_model} · "
          f"değerlendirme modeli={s.assessment_model} · tavan={args.max_articles}/entity")
    summary = run_refresh(manual=True, entity_ids=set(ents.values()))

    # ---- sonuçları oku ----
    results: dict[str, dict[str, EntityAnalysis]] = {}
    with session_scope() as ses:
        for name, eid in ents.items():
            results[name] = {}
            for lang in ("tr", "en"):
                row = ses.scalar(
                    select(EntityAnalysis)
                    .where(EntityAnalysis.entity_id == eid, EntityAnalysis.language == lang,
                           EntityAnalysis.created_at >= started)
                    .order_by(EntityAnalysis.created_at.desc()).limit(1)
                )
                if row is not None:
                    results[name][lang] = row
        rationales = [
            (a.entity_id, a.rationale or "")
            for a in ses.scalars(select(Article).where(
                Article.entity_id.in_(ents.values()), Article.analyzed_at >= started))
        ]
        usage = ses.execute(
            select(LlmUsage.model, LlmUsage.purpose, func.count(), func.sum(LlmUsage.prompt_tokens),
                   func.sum(LlmUsage.cache_creation_tokens), func.sum(LlmUsage.cache_read_tokens),
                   func.sum(LlmUsage.completion_tokens), func.sum(LlmUsage.cost_usd))
            .where(LlmUsage.created_at >= started)
            .group_by(LlmUsage.model, LlmUsage.purpose)
        ).all()

    fails: list[str] = []
    lines: list[str] = [
        "# Yenileme değerlendirmesi (canlı)", "",
        f"- Tarih (UTC): {started:%Y-%m-%d %H:%M}",
        f"- Entity'ler: {', '.join(names)}",
        f"- Makale modeli: `{s.article_model}` · değerlendirme modeli: `{s.assessment_model}`",
        f"- Entity başına makale tavanı: {args.max_articles}",
        f"- Yenileme özeti: yeni={summary.fetched_new} analiz={summary.analyzed} "
        f"elenen={summary.discarded} değerlendirme={summary.entity_assessments}",
        "",
    ]

    # ---- 1. şablon çöküşü ----
    lines += ["## 1. Şablon çöküşü", ""]
    for lang in ("tr", "en"):
        rows = [(n, r[lang]) for n, r in results.items() if lang in r]
        lines += [f"### {lang.upper()}", "", "| Entity | risk | yön/kanaat | headline_verdict |",
                  "|---|---|---|---|"]
        for n, r in rows:
            v = (r.headline_verdict or "").replace("|", "\\|")
            lines.append(f"| {n} | {r.risk_score} | {r.stance}/{r.conviction} | {v} |")
        lines.append("")
        if len(rows) < len(names):
            fails.append(f"{lang}: {len(names) - len(rows)} entity için değerlendirme üretilmedi")
        openings = Counter(" ".join((r.headline_verdict or "").lower().split()[:3]) for _, r in rows)
        dup = {o: c for o, c in openings.items() if c > 1}
        lines.append(f"- Aynı açılış (ilk 3 kelime): {dup or 'yok'}")
        if rows and max(openings.values()) > len(rows) / 2:
            fails.append(f"{lang}: entity'lerin yarısından fazlası aynı açılış: {dup}")
        grams = repeated_ngrams({n: r.headline_verdict or "" for n, r in rows}, n=3)
        lines.append(f"- Tekrar eden 3+ kelimelik öbek (hüküm): "
                     f"{ {g: len(ns) for g, ns in grams.items()} or 'yok'}")
        worst = max((len(ns) for ns in grams.values()), default=0)
        if rows and worst > len(rows) / 2:
            fails.append(f"{lang}: hükümlerin yarısından fazlası aynı öbeği paylaşıyor: "
                         f"{[g for g, ns in grams.items() if len(ns) == worst]}")
        take_grams = repeated_ngrams({n: r.ai_take or "" for n, r in rows}, n=3,
                                     min_docs=max(3, len(rows) // 2 + 1))
        lines.append(f"- ai_take'te entity'lerin yarısından fazlasında geçen öbek (bilgi): "
                     f"{list(take_grams) or 'yok'}")
        banned = []
        for n, r in rows:
            text = " ".join([r.headline_verdict or "", r.ai_take or "", r.summary or "",
                             r.invalidation or "", *(r.top_drivers or []), *(r.what_to_verify or [])])
            banned += [f"{n}: '{p}'" for p in banned_phrase_hits(text, lang)]
        lines.append(f"- Yasaklı ifade: {banned or 'yok'}")
        if banned:
            fails.append(f"{lang}: yasaklı ifade kullanıldı: {banned}")
        scores = Counter(r.risk_score for _, r in rows)
        lines.append(f"- risk_score dağılımı: {dict(sorted(scores.items()))}")
        if rows and max(scores.values()) > len(rows) / 2:
            fails.append(f"{lang}: entity'lerin yarısından fazlası aynı risk_score: {dict(scores)}")
        lines.append("")

    # ---- 2. yatırım tavsiyesi ----
    lines += ["## 2. Yatırım tavsiyesi bariyeri", ""]
    advice_hits = []
    for n, r in results.items():
        for lang, row in r.items():
            data = {f: getattr(row, f) for f in (
                "headline_verdict", "ai_take", "summary", "invalidation", "top_drivers", "what_to_verify")}
            for field, label, sent in scan_assessment(data):
                advice_hits.append(f"{n}/{lang}/{field}: [{label}] {sent}")
    for eid, rat in rationales:
        for label, sent in scan_text(rat):
            advice_hits.append(f"makale gerekçesi (entity {eid}): [{label}] {sent}")
    lines += [f"- Taranan: {sum(len(r) for r in results.values())} değerlendirme + "
              f"{len(rationales)} makale gerekçesi", f"- İhlal: {len(advice_hits)}"]
    lines += [f"  - {h}" for h in advice_hits]
    if advice_hits:
        fails.append(f"yatırım tavsiyesi ifadesi bulundu ({len(advice_hits)})")
    lines.append("")

    # ---- 3. kesilme ----
    trunc = [m for lvl, m in cap.msgs if "max_tokens'ta kesildi" in m]
    lines += ["## 3. Kesilme", "", f"- TruncationError: {len(trunc)}"]
    lines += [f"  - {m}" for m in trunc[:10]]
    if trunc:
        fails.append(f"TruncationError: {len(trunc)}")
    lines.append("")

    # ---- 4. Türkçe karakter ----
    tr_text = " ".join(
        " ".join([r["tr"].headline_verdict or "", r["tr"].ai_take or "", r["tr"].summary or "",
                  r["tr"].invalidation or "", *(r["tr"].what_to_verify or []), *(r["tr"].top_drivers or [])])
        for r in results.values() if "tr" in r
    )
    moji = _MOJIBAKE.findall(tr_text)
    tr_found = sorted(set(tr_text) & _TR_CHARS)
    lines += ["## 4. Türkçe karakter", "", f"- Mojibake/kaçış dizisi: {len(moji)} {moji[:10] or ''}",
              f"- Bulunan Türkçe karakterler: {' '.join(tr_found) or 'YOK'}", ""]
    if moji:
        fails.append(f"Türkçe karakter bozulması: {moji[:5]}")
    if tr_text and not ({"ı", "ş", "ğ"} & set(tr_text)):
        fails.append("TR metinlerde hiç ı/ş/ğ yok — karakterler düzleştirilmiş olabilir")

    # ---- 5. kesik cümle ----
    lines += ["## 5. Kesik cümle (noktalama ile bitmeyen alan)", ""]
    cut = []
    for n, r in results.items():
        for lang, row in r.items():
            data = {f: getattr(row, f) for f in (
                "headline_verdict", "ai_take", "summary", "invalidation", "top_drivers", "what_to_verify")}
            cut += [f"{n}/{lang}/{f}: …{v[-60:]}" for f, v in unterminated_fields(data)]
    lines.append(f"- Noktalamasız biten alan/madde: {len(cut)}")
    lines += [f"  - {c}" for c in cut]
    if cut:
        fails.append(f"kesik/noktalamasız metin alanı: {len(cut)}")
    lines.append("")

    # ---- maliyet ----
    lines += ["## Maliyet (bu koşu)", "", "| Model | Amaç | Çağrı | Girdi | Cache yazma | Cache okuma | Çıktı | USD |",
              "|---|---|---|---|---|---|---|---|"]
    total = 0.0
    for model, purpose, n, inp, cw, cr, out, cost in usage:
        total += cost or 0
        lines.append(f"| {model} | {purpose} | {n} | {inp} | {cw} | {cr} | {out} | ${(cost or 0):.4f} |")
    lines += ["", f"**Toplam: ${total:.4f}**", ""]

    lines += ["## Sonuç", "", "**BAŞARILI**" if not fails else "**BAŞARISIZ**"]
    lines += [f"- {f}" for f in fails]
    if summary.warnings:
        lines += ["", "### Yenileme uyarıları", *[f"- {w}" for w in summary.warnings[:30]]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRapor: {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
