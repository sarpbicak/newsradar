// Analist konsensüsü — GERÇEK veri (Finnhub), NewsRadar üretmez.
// Veri yoksa: kartta (compact) sessizce gizlenir; detayda BOŞLUK yerine NEDEN
// veri olmadığını düz Türkçe açıklayan bir not gösterilir (özel şirket / desteklenmeyen borsa).
// compact=true: kart için mini bar + kısa etiket. false: detay için tam gösterim.
import React from "react";
import { InfoTip, TERM_HELP } from "./ui.jsx";

// Veri yokken gösterilecek açıklama (boşluk bir eksiklik değil, bir açıklama gibi görünsün).
function noDataNote(type, hasPrice) {
  if (type === "keyword") {
    return "Bu şirket borsada işlem görmüyor (özel şirket) — hedef fiyat ve analist " +
      "verisi yok. Değerlendirme sadece haber akışına dayanıyor.";
  }
  if (!hasPrice) {
    // Ticker ama fiyat da yok → ABD dışı borsa (BIST/Avrupa) — kaynağımız kapsamıyor.
    return "Bu borsa için fiyat ve analist verisi kaynağımızda yok (ör. Türkiye/Avrupa " +
      "borsaları). Değerlendirme haber akışına dayanıyor.";
  }
  // Ticker + fiyat var ama analist verisi yok.
  return "Bu şirket için analist konsensüsü şu an kaynağımızda yok. Değerlendirme " +
    "haber akışına dayanıyor.";
}

const SEGMENTS = [
  { key: "strong_buy", label: "Güçlü Al", color: "#15803d" },
  { key: "buy", label: "Al", color: "#22c55e" },
  { key: "hold", label: "Tut", color: "#9ca3af" },
  { key: "sell", label: "Sat", color: "#ef4444" },
  { key: "strong_sell", label: "Güçlü Sat", color: "#b91c1c" },
];

function consensusLabel(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: "Al ağırlıklı", color: "#16a34a" };
  if (sellish > a.hold && sellish > buyish) return { text: "Sat ağırlıklı", color: "#dc2626" };
  return { text: "Tut ağırlıklı", color: "#6b7280" };
}

function Bar({ analyst }) {
  const total = analyst.total || 1;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-black/10">
      {SEGMENTS.map((s) => {
        const n = analyst[s.key] || 0;
        if (!n) return null;
        return (
          <div
            key={s.key}
            style={{ width: `${(n / total) * 100}%`, background: s.color }}
            title={`${s.label}: ${n}`}
          />
        );
      })}
    </div>
  );
}

export default function AnalystConsensus({ analyst, price, type, compact = false }) {
  // Veri yok: kartta gizle (kart sade kalsın); detayda açıklayıcı not göster.
  if (!analyst || !analyst.total) {
    if (compact) return null;
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
        <div className="mb-1 flex items-center gap-1 text-[11px] uppercase text-slate-500">
          Analist konsensüsü <InfoTip text={TERM_HELP.analyst} />
        </div>
        <p className="text-sm leading-relaxed text-slate-400">
          {noDataNote(type, price != null)}
        </p>
      </div>
    );
  }
  const lean = consensusLabel(analyst);

  // Hedef fiyat (Finnhub ücretsiz katmanda None → gösterilmez; premium açılırsa dolar).
  const target = analyst.target_mean;
  const pct =
    target && price ? Math.round(((target - price) / price) * 100) : null;

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold" style={{ color: lean.color }}>
          {lean.text}
        </span>
        <div className="min-w-[60px] flex-1">
          <Bar analyst={analyst} />
        </div>
        <span className="text-[10px] tabular-nums text-slate-500">{analyst.total} analist</span>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="inline-flex items-center gap-1 text-[11px] uppercase text-slate-500">
          Analist konsensüsü <InfoTip text={TERM_HELP.analyst} />
        </span>
        <span className="text-xs font-semibold" style={{ color: lean.color }}>
          {lean.text}
        </span>
      </div>

      {target && price && (
        <div className="mb-3 flex items-baseline gap-2 text-sm">
          <span className="text-slate-400">${price.toFixed(2)}</span>
          <span className="inline-flex items-center gap-0.5 text-slate-500">
            → hedef <InfoTip text={TERM_HELP.target} />
          </span>
          <span className="font-semibold tabular-nums text-slate-100">${target.toFixed(2)}</span>
          {pct != null && (
            <span className={pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
              ({pct >= 0 ? "+" : ""}
              {pct}%)
            </span>
          )}
        </div>
      )}

      <Bar analyst={analyst} />
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] tabular-nums">
        {SEGMENTS.map((s) => (
          <span key={s.key} className="flex items-center gap-1 text-slate-400">
            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
            {s.label} <span className="font-semibold text-slate-200">{analyst[s.key] || 0}</span>
          </span>
        ))}
      </div>

      <div className="mt-3 text-[10px] leading-relaxed text-slate-500">
        Analist konsensüsü (Finnhub{analyst.period ? ` · ${analyst.period}` : ""}) —
        NewsRadar'ın kendi görüşü değil.
      </div>
    </div>
  );
}
