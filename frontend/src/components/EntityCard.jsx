// Overview ızgarasındaki tek entity kartı.
import React from "react";
import { StanceBadge, RiskScore, SentimentGauge, TrendArrow, FlagChip, timeAgo } from "./ui.jsx";

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

      <div className="flex items-center justify-between">
        <RiskScore score={a?.risk_score ?? null} />
        {a && <TrendArrow trend={a.sentiment_trend} />}
      </div>

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
