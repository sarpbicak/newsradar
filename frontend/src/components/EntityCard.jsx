// Verdict-First kart: 3 saniyede okunur. Ad → hüküm cümlesi → Genel sinyal →
// Yön/Vade/Kanıt → fiyat. Risk skoru, duygu çubuğu, bayrak çipleri → DETAY sayfasında.
// Kök öğe <div role="button">: içine "?" ipucu düğmeleri koyabilmek için (nested
// <button> geçersiz olurdu). Klavye ile de açılır (Enter/Space).
import React from "react";
import {
  RiskDelta,
  PriceDisplay,
  SignalBand,
  InfoTip,
  TERM_HELP,
  stanceLabel,
  stanceColor,
  horizonLabel,
  evidenceLabel,
  evidenceColor,
} from "./ui.jsx";
import AnalystConsensus from "./AnalystConsensus.jsx";

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const dir = a ? stanceColor(a.stance) : "#7A8699";

  function open() {
    onOpen(card.id);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      className="group relative flex cursor-pointer flex-col gap-4 overflow-hidden rounded-xl border border-ink-600 bg-ink-800 p-5 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      {/* Yön durumuna göre sol kenar şeridi */}
      <span className="absolute inset-y-0 left-0 w-1" style={{ background: a ? dir : "transparent" }} />

      {/* 1. Ad + tip */}
      <div className="flex items-start justify-between gap-2">
        <div className="font-display text-[15px] font-semibold text-slate-100">{card.name}</div>
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
          {/* 2. Tek cümlelik hüküm — kartın EN BÜYÜK, en okunaklı öğesi. Eski
              analizlerde verdict yoksa özete düşer; 3 satırla sınırlı ('3 saniye'). */}
          <p className="line-clamp-3 font-display text-base font-semibold leading-snug text-slate-100">
            {a.headline_verdict || a.summary}
          </p>

          {/* 3. Genel sinyal bandı — yön + kanıtı tek görsele indirger */}
          <SignalBand stance={a.stance} evidence={card.evidence_strength} />

          {/* Yön değişimi vurgusu */}
          {card.delta?.stance_changed && (
            <div className="flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-bold text-amber-200">
              ⚡ Yön değişti: {stanceLabel(card.delta.previous_stance)} → {stanceLabel(a.stance)}
            </div>
          )}

          {/* 4. Üç etiket: Yön / Vade / Kanıt — her birinde "?" açıklaması */}
          <div className="grid grid-cols-3 divide-x divide-ink-700 rounded-lg border border-ink-700 text-center">
            <div className="px-1 py-2">
              <div className="flex items-center justify-center gap-0.5 text-[10px] uppercase text-slate-500">
                Yön <InfoTip text={TERM_HELP.direction} />
              </div>
              <div className="text-sm font-bold" style={{ color: dir }}>
                {stanceLabel(a.stance)}
              </div>
            </div>
            <div className="px-1 py-2">
              <div className="flex items-center justify-center gap-0.5 text-[10px] uppercase text-slate-500">
                Vade <InfoTip text={TERM_HELP.horizon} />
              </div>
              <div className="text-sm font-bold text-slate-200">{horizonLabel(card.horizon)}</div>
            </div>
            <div className="px-1 py-2">
              <div className="flex items-center justify-center gap-0.5 text-[10px] uppercase text-slate-500">
                Kanıt <InfoTip text={TERM_HELP.evidence} />
              </div>
              <div className="text-sm font-bold" style={{ color: evidenceColor(card.evidence_strength) }}>
                {evidenceLabel(card.evidence_strength)}
              </div>
              <div className="text-[9px] tabular-nums text-slate-500">{card.evidence_count} haber</div>
            </div>
          </div>

          {/* 5. Fiyat (ticker) + risk değişimi kısa */}
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

          {/* Analist konsensüsü — kompakt tek satır (yalnızca veri varsa) */}
          {card.analyst && <AnalystConsensus analyst={card.analyst} price={card.price} type={card.type} compact />}
        </>
      )}
    </div>
  );
}
