// Overview ızgarasındaki tek entity kartı.
import React from "react";
import {
  StanceBadge,
  RiskScore,
  RiskDelta,
  SentimentGauge,
  TrendArrow,
  FlagChip,
  PriceDisplay,
  stanceLabel,
  timeAgo,
} from "./ui.jsx";

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  return (
    <button
      onClick={() => onOpen(card.id)}
      className="group flex flex-col gap-3 rounded-xl border border-ink-600 bg-ink-800 p-4 text-left transition hover:border-accent/50 hover:bg-ink-700"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-slate-100">{card.name}</div>
          <div className="font-mono text-[11px] text-slate-500">
            {card.type === "ticker" ? "$" : "#"}
            {card.query}
          </div>
        </div>
        {a ? (
          <StanceBadge stance={a.stance} conviction={a.conviction} />
        ) : (
          <span className="rounded-md border border-ink-500 px-2 py-0.5 text-[11px] text-slate-500">
            analiz yok
          </span>
        )}
      </div>

      {/* Stance değişimi belirgin vurgu (ör. NÖTR → DÜŞÜŞ) */}
      {a && card.delta?.stance_changed && (
        <div className="flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-bold text-amber-200">
          ⚡ Yön değişti: {stanceLabel(card.delta.previous_stance)} → {stanceLabel(a.stance)}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RiskScore score={a?.risk_score ?? null} />
          <RiskDelta delta={card.delta} />
        </div>
        {a && <TrendArrow trend={a.sentiment_trend} />}
      </div>

      {/* Fiyat — yalnızca ticker entity'lerde (keyword'de card.price null → gizli) */}
      {card.price != null && (
        <div className="flex items-center justify-between border-t border-ink-700 pt-2">
          <span className="text-[10px] uppercase text-slate-500">fiyat</span>
          <PriceDisplay
            price={card.price}
            changePercent={card.change_percent}
            updatedAt={card.price_updated_at}
          />
        </div>
      )}

      <SentimentGauge value={card.avg_sentiment} />

      {card.top_flags?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.top_flags.map((f) => (
            <FlagChip key={f} flag={f} />
          ))}
        </div>
      )}

      <div className="mt-auto flex items-center justify-between text-[11px] text-slate-500">
        <span>
          {card.analyzed_count}/{card.article_count} analiz
        </span>
        <span>{card.last_updated ? timeAgo(card.last_updated) : "yenilenmedi"}</span>
      </div>
    </button>
  );
}
