// "Bunları da izlemek ister misin?" — co-mentioned şirket önerileri.
// Öneri yoksa hiç render edilmez (boş başlık durmasın).
import React, { useState } from "react";

export default function SuggestionsSection({ suggestions, onAdd, onDismiss }) {
  const [busyId, setBusyId] = useState(null);

  if (!suggestions || suggestions.length === 0) return null;

  async function handle(action, id) {
    setBusyId(id);
    try {
      await action(id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800/60 p-4">
      <div className="mb-1 text-sm font-semibold text-slate-200">
        Bunları da izlemek ister misin?
      </div>
      <div className="mb-3 text-[11px] text-slate-500">
        Haberlerinde sık geçen, izleme listende olmayan şirketler.
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {suggestions.map((s) => {
          const busy = busyId === s.id;
          return (
            <div
              key={s.id}
              className="flex flex-col gap-2 rounded-lg border border-ink-600 bg-ink-800 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="font-semibold text-slate-100">{s.name}</span>
                  {s.ticker && (
                    <span className="font-mono text-[11px] text-slate-500">${s.ticker}</span>
                  )}
                </div>
                <span className="shrink-0 rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                  {s.mention_count} haberde geçti
                </span>
              </div>

              {s.sample_rationale && (
                <p className="text-xs leading-relaxed text-slate-400">{s.sample_rationale}</p>
              )}

              {s.source_entity_names?.length > 0 && (
                <div className="text-[11px] text-slate-500">
                  {s.source_entity_names.join(", ")} haberlerinde
                </div>
              )}

              <div className="mt-1 flex gap-2">
                <button
                  onClick={() => handle(onAdd, s.id)}
                  disabled={busy}
                  className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  {busy ? "…" : "+ Ekle"}
                </button>
                <button
                  onClick={() => handle(onDismiss, s.id)}
                  disabled={busy}
                  className="rounded-md border border-ink-500 px-3 py-1 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50"
                >
                  Gizle
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
