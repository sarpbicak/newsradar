// SADE kart — 5 öğe: (1) ad+ticker(+yön değişti) (2) hüküm (kahraman) (3) genel sinyal
// (4) tek satır meta (5) tek satır finansal. Analist barı/risk deltası/kutular DETAYDA.
import React from "react";
import { SignalBand, AnimatedNumber, stanceLabel, stanceColor, horizonLabel, evidenceLabel } from "./ui.jsx";

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const dir = a ? stanceColor(a.stance) : "#8B8F9E";
  const isTicker = card.type === "ticker";
  const changed = a && card.delta?.stance_changed;
  // Yön değişimi oku: yeni yöne göre renkli (yükseliş yeşil ↑, düşüş kırmızı ↓).
  const changeUp = a?.stance === "bullish";
  const changeColor = a?.stance === "bullish" ? "#3FD68C" : a?.stance === "bearish" ? "#FF6B6B" : "#8B8F9E";

  const up = (card.change_percent ?? 0) >= 0;
  const upside = card.analyst?.upside_percent;
  const target = card.analyst?.target_mean;

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
      className="group relative flex cursor-pointer flex-col gap-3.5 overflow-hidden rounded-xl border border-ink-600 bg-ink-800 p-5 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      {/* Yön durumuna göre ince sol kenar şeridi */}
      <span className="absolute inset-y-0 left-0 w-1" style={{ background: a ? dir : "transparent" }} />

      {/* 1. Ad + ticker (+ yön değişti — küçük renkli metin) */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-display text-[15px] font-semibold text-slate-100">{card.name}</span>
          {changed && (
            <span className="text-[11px] font-semibold" style={{ color: changeColor }}>
              {changeUp ? "↑" : "↓"} yön değişti
            </span>
          )}
        </div>
        <span className="shrink-0 font-mono text-[11px] text-slate-500">
          {isTicker ? "$" : "#"}{card.query}
        </span>
      </div>

      {!a ? (
        <div className="py-2 text-sm text-slate-400">
          Henüz analiz yok — <strong className="text-slate-200">Yenile</strong>'ye basın.
        </div>
      ) : (
        <>
          {/* 2. Hüküm cümlesi — kartın kahramanı (en büyük, en dikkat çekici) */}
          <p className="line-clamp-3 font-display text-base font-semibold leading-snug text-slate-100">
            {a.headline_verdict || a.summary}
          </p>

          {/* 3. Genel sinyal barı (sade — sağda durum metni) */}
          <SignalBand stance={a.stance} evidence={card.evidence_strength} minimal />

          {/* 4. Tek satır meta */}
          <div className="text-xs text-slate-400">
            <span className="font-semibold" style={{ color: dir }}>{stanceLabel(a.stance)}</span>
            <span className="text-slate-600"> · </span>
            {horizonLabel(card.horizon)} vade
            <span className="text-slate-600"> · </span>
            {evidenceLabel(card.evidence_strength)} kanıt ({card.evidence_count} haber)
          </div>

          {/* 5. Tek satır finansal */}
          <div className="text-sm">
            {isTicker ? (
              card.price != null ? (
                <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
                  <span className="font-mono font-semibold text-slate-100">
                    <AnimatedNumber value={card.price} decimals={2} prefix="$" />
                  </span>
                  {card.change_percent != null && (
                    <span className={`font-mono text-xs font-medium ${up ? "text-emerald-400" : "text-rose-400"}`}>
                      {up ? "+" : "−"}{Math.abs(card.change_percent).toFixed(2)}%
                    </span>
                  )}
                  {target != null && (
                    <span className="text-slate-400">
                      <span className="text-slate-600"> · </span>hedef ${target.toFixed(0)}
                      {upside != null && (
                        <span className={upside >= 0 ? "text-emerald-400" : "text-rose-400"}>
                          {" "}({upside >= 0 ? "+" : "−"}%{Math.abs(Math.round(upside))})
                        </span>
                      )}
                    </span>
                  )}
                </span>
              ) : (
                <span className="text-slate-500">Fiyat verisi yok</span>
              )
            ) : (
              <span className="text-slate-500">Borsada işlem görmüyor</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
