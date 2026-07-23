// Verdict-First kart: 3 saniyede okunur. Ad → hüküm cümlesi → Yön/Vade/Kanıt →
// fiyat. Risk skoru, duygu çubuğu, bayrak çipleri, sayaç → DETAY sayfasında.
import React from "react";
import {
  RiskDelta,
  PriceDisplay,
  stanceLabel,
  stanceColor,
  horizonLabel,
  evidenceLabel,
  evidenceColor,
} from "./ui.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const dir = a ? stanceColor(a.stance) : "#6b7280";

  return (
    <button
      onClick={() => onOpen(card.id)}
      className="group relative flex flex-col gap-3 overflow-hidden rounded-xl border border-ink-600 bg-ink-800 p-4 text-left transition hover:border-accent/50 hover:bg-ink-700"
    >
      {/* Yön durumuna göre sol kenar şeridi */}
      <span className="absolute inset-y-0 left-0 w-1" style={{ background: a ? dir : "transparent" }} />

      {/* 1. Ad + tip */}
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold text-slate-100">{card.name}</div>
        <span className="shrink-0 font-mono text-[11px] text-slate-500">
          {card.type === "ticker" ? "$" : "#"}
          {card.query}
        </span>
      </div>

      {!a ? (
        /* Boş durum — boş göstergeler yerine tek net mesaj */
        <div className="py-3 text-sm text-slate-400">
          Henüz analiz yok — <strong className="text-slate-200">Yenile</strong>'ye basın.
        </div>
      ) : (
        <>
          {/* 2. Tek cümlelik hüküm (büyük, düz Türkçe) */}
          <p className="text-[15px] font-medium leading-snug text-slate-100">
            {a.headline_verdict || a.summary}
          </p>

          {/* Yön değişimi vurgusu */}
          {card.delta?.stance_changed && (
            <div className="flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-bold text-amber-200">
              ⚡ Yön değişti: {stanceLabel(card.delta.previous_stance)} → {stanceLabel(a.stance)}
            </div>
          )}

          {/* 3. Üç etiket: Yön / Vade / Kanıt */}
          <div className="grid grid-cols-3 divide-x divide-ink-700 rounded-lg border border-ink-700 text-center">
            <div className="px-1 py-2">
              <div className="text-[10px] uppercase text-slate-500">Yön</div>
              <div className="text-sm font-bold" style={{ color: dir }}>
                {stanceLabel(a.stance)}
              </div>
            </div>
            <div className="px-1 py-2">
              <div className="text-[10px] uppercase text-slate-500">Vade</div>
              <div className="text-sm font-bold text-slate-200">{horizonLabel(card.horizon)}</div>
            </div>
            <div className="px-1 py-2">
              <div className="text-[10px] uppercase text-slate-500">Kanıt</div>
              <div className="text-sm font-bold" style={{ color: evidenceColor(card.evidence_strength) }}>
                {evidenceLabel(card.evidence_strength)}
              </div>
              <div className="text-[9px] tabular-nums text-slate-500">
                {card.evidence_count} haber
              </div>
            </div>
          </div>

          {/* 4. Fiyat (ticker) + risk değişimi kısa */}
          {card.price != null && (
            <div className="flex items-center justify-between">
              <PriceDisplay
                price={card.price}
                changePercent={card.change_percent}
                updatedAt={card.price_updated_at}
              />
              <RiskDelta delta={card.delta} />
            </div>
          )}

          {/* Analist konsensüsü — kompakt tek satır (varsa) */}
          {card.analyst && <AnalystConsensus analyst={card.analyst} price={card.price} compact />}
        </>
      )}
    </button>
  );
}
