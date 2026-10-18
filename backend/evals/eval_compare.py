"""Haiku 5.5 vs Sonnet 5.5 — entity değerlendirmesi yan yana (TR + EN), karar VERMEZ.

Her entity için pipeline ile AYNI girdi (son analiz edilmiş makaleler + fiyat + analist
bağlamı) ve AYNI kurtarma mantığı (_assess_entity_with_recovery) kullanılır; sonuçlar
entity_analyses'e YAZILMAZ. Çağrı maliyetleri llm_usage'a yazılır (purpose=assessment).
Çıktı: hüküm, ai_take, what_to_verify, risk skoru, yön/kanaat + çağrı başına maliyet.

Çalıştır (backend/ içinden, eval_refresh'in kullandığı DB kopyasıyla):
  python -m evals.eval_compare --db <kopya.db> --out evals/reports/haiku_vs_sonnet.md
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ENTITIES = "Tesla,Anthropic,Microsoft"
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--entities", default=DEFAULT_ENTITIES)
    ap.add_argument("--out", default="evals/reports/haiku_vs_sonnet.md")
    args = ap.parse_args()
    os.environ.update(NEWSRADAR_DB=str(Path(args.db).resolve()), NEWSRADAR_LLM_PROVIDER="anthropic",
                      NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off")

    from sqlalchemy import select

    from app.analysis.advice_guard import scan_assessment
    from app.analysis.claude_client import ClaudeClient, ClaudeError
    from app.analysis.pipeline import _assess_entity_with_recovery, _read_assessment_payload
    from app.analysis.prompts import build_entity_prompt
    from app.analysis.schemas import sanitize_entity_analysis
    from app.analyst import analyst_context_for
    from app.db.database import init_db, session_scope
    from app.db.models import Entity
    from app.prices import price_context_for

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    init_db()

    names = [n.strip() for n in args.entities.split(",") if n.strip()]
    with session_scope() as s:
        ents = [(e.id, e.name, e.query, e.type, e.language)
                for e in s.scalars(select(Entity).where(Entity.name.in_(names)))]
    clients = {m: ClaudeClient(model=m, purpose="assessment") for m in MODELS}

    rows: dict[tuple[str, str], dict[str, dict]] = {}
    costs: dict[str, list[float]] = {m: [] for m in MODELS}
    for eid, name, query, etype, elang in ents:
        payload = _read_assessment_payload(eid)
        price, analyst = price_context_for(eid), analyst_context_for(eid)
        for lang in ("tr", "en"):
            def build(items, _l=lang):
                return build_entity_prompt(name, query, etype, items, price=price,
                                           language=elang, analyst=analyst, out_lang=_l)
            for m, c in clients.items():
                before = c.total_cost_usd
                try:
                    data, used = _assess_entity_with_recovery(c, build, payload, f"{name}/{lang}/{m}")
                    clean = sanitize_entity_analysis(data, lang)
                    err = None
                except ClaudeError as exc:
                    clean, used, err = {}, [], str(exc)
                cost = c.total_cost_usd - before
                costs[m].append(cost)
                rows.setdefault((name, lang), {})[m] = {
                    "data": clean, "cost": cost, "usage": dict(c.last_usage or {}),
                    "articles": len(used), "error": err, "advice": scan_assessment(clean),
                }

    now = datetime.now(timezone.utc)
    L = ["# Haiku 5.5 vs Sonnet 5.5 — entity değerlendirmesi", "",
         f"- Tarih (UTC): {now:%Y-%m-%d %H:%M}",
         f"- Entity'ler: {', '.join(n for _, n, *_ in ents)} · diller: TR + EN",
         "- Aynı girdi (son analiz edilmiş makaleler + fiyat + analist bağlamı), aynı prompt.",
         "- Haiku 5.5: zorunlu tool_choice (thinking atlanır), varsayılan effort. "
         "Sonnet 5.5: tool_choice=auto, adaptive thinking, effort=medium.",
         "- Karar verilmedi — yalnızca karşılaştırma.", "",
         "## Maliyet özeti", "", "| Model | Çağrı | Toplam USD | Çağrı başına ort. USD |", "|---|---|---|---|"]
    for m in MODELS:
        n = len(costs[m])
        L.append(f"| `{m}` | {n} | ${sum(costs[m]):.4f} | ${(sum(costs[m]) / n if n else 0):.4f} |")
    L.append("")

    for (name, lang), by_model in rows.items():
        L += [f"## {name} — {lang.upper()}", "", "| | " + " | ".join(f"`{m}`" for m in MODELS) + " |",
              "|---|" + "---|" * len(MODELS)]

        def row(label, fn):
            L.append(f"| {label} | " + " | ".join(_cell(fn(by_model[m])) for m in MODELS) + " |")

        row("Hata", lambda r: r["error"] or "—")
        row("Hüküm", lambda r: r["data"].get("headline_verdict", ""))
        row("ai_take", lambda r: r["data"].get("ai_take", ""))
        row("what_to_verify", lambda r: " • ".join(r["data"].get("what_to_verify", [])))
        row("Risk skoru", lambda r: str(r["data"].get("risk_score", "")))
        row("Yön / kanaat", lambda r: f"{r['data'].get('stance', '')} / {r['data'].get('conviction', '')}")
        row("Bağlam makale", lambda r: str(r["articles"]))
        row("Token (girdi / cache okuma / çıktı)", lambda r: (
            f"{r['usage'].get('input_tokens', 0)} / {r['usage'].get('cache_read_input_tokens', 0)} / "
            f"{r['usage'].get('output_tokens', 0)}"))
        row("Çağrı maliyeti", lambda r: f"${r['cost']:.4f}")
        row("Tavsiye taraması", lambda r: "temiz" if not r["advice"] else
            "; ".join(f"{f}:{lbl}" for f, lbl, _ in r["advice"]))
        L.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nRapor: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
