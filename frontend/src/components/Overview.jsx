// Genel görünüm: değişim şeridi + sıralama seçici + entity kartları + izleme listesi.
import React, { useMemo, useState } from "react";
import EntityCard from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";
import { stanceLabel } from "./ui.jsx";

// Değişim büyüklüğü: risk farkı + yön değişimi (ağır) + duygu farkı.
function changeScore(card) {
  const d = card.delta;
  if (!d) return -1; // geçmiş yok → en alta
  let s = Math.abs(d.risk_delta || 0);
  if (d.stance_changed) s += 50;
  if (d.sentiment_delta) s += Math.abs(d.sentiment_delta) * 20;
  return s;
}

function hasChange(card) {
  const d = card.delta;
  return !!(
    d && (d.risk_delta !== 0 || d.stance_changed || (d.sentiment_delta && d.sentiment_delta !== 0))
  );
}

// "Tesla: risk 72→78 · NÖTR→DÜŞÜŞ" gibi tek satırlık değişim özeti.
function changeSummary(card) {
  const d = card.delta;
  const a = card.analysis;
  const parts = [];
  if (d.risk_delta && card.previous_analysis)
    parts.push(`risk ${card.previous_analysis.risk_score}→${a.risk_score}`);
  if (d.stance_changed)
    parts.push(`${stanceLabel(d.previous_stance)}→${stanceLabel(a.stance)}`);
  if (d.sentiment_delta)
    parts.push(`duygu ${d.sentiment_delta > 0 ? "+" : ""}${d.sentiment_delta}`);
  return parts.join(" · ");
}

const SORTS = {
  change: { label: "En çok değişen", fn: (a, b) => changeScore(b) - changeScore(a) },
  risk: {
    label: "Risk",
    fn: (a, b) => (b.analysis?.risk_score ?? -1) - (a.analysis?.risk_score ?? -1),
  },
  alpha: { label: "Alfabetik", fn: (a, b) => a.name.localeCompare(b.name, "tr") },
};

export default function Overview({ cards, onOpen, onCreate, onDelete }) {
  const [sort, setSort] = useState("change");

  const sorted = useMemo(() => [...cards].sort(SORTS[sort].fn), [cards, sort]);
  const changed = useMemo(
    () =>
      cards
        .filter(hasChange)
        .sort((a, b) => changeScore(b) - changeScore(a))
        .slice(0, 3),
    [cards]
  );

  return (
    <div className="space-y-6">
      {/* Değişim şeridi — hiçbir şey değişmediyse gösterme */}
      {changed.length > 0 && (
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-accent">
            Son taramaya göre
          </div>
          <div className="space-y-1.5">
            {changed.map((c) => (
              <button
                key={c.id}
                onClick={() => onOpen(c.id)}
                className="flex w-full flex-wrap items-center gap-x-2 text-left text-sm text-slate-300 hover:text-white"
              >
                <span className="font-semibold text-slate-100">{c.name}</span>
                <span className="text-slate-400">{changeSummary(c)}</span>
                {c.delta?.stance_changed && (
                  <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 text-[10px] font-semibold text-amber-200">
                    yön değişti
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {cards.length === 0 ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-8 text-center text-slate-400">
          İzleme listesi boş. Aşağıdan bir varlık ekleyin.
        </div>
      ) : (
        <>
          {/* Sıralama seçici */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500">Sırala:</span>
            {Object.entries(SORTS).map(([key, { label }]) => (
              <button
                key={key}
                onClick={() => setSort(key)}
                className={`rounded-md border px-2.5 py-1 transition ${
                  sort === key
                    ? "border-accent/50 bg-accent/15 text-slate-100"
                    : "border-ink-600 text-slate-400 hover:text-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sorted.map((c) => (
              <EntityCard key={c.id} card={c} onOpen={onOpen} />
            ))}
          </div>
        </>
      )}

      <WatchlistManager cards={cards} onCreate={onCreate} onDelete={onDelete} />
    </div>
  );
}
