// Genel görünüm: Katman 1 (bugün önemli — büyük kartlar) + Katman 2 (liste — satırlar).
import React, { useMemo, useState } from "react";
import EntityCard, { EntityRow } from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";
import SuggestionsSection from "./SuggestionsSection.jsx";

// Katman 2 sıralaması (Katman 1 zaten backend'de öncelik skoruyla seçilir).
const SORTS = {
  risk: {
    label: "Risk",
    fn: (a, b) => (b.analysis?.risk_score ?? -1) - (a.analysis?.risk_score ?? -1),
  },
  alpha: { label: "Alfabetik", fn: (a, b) => a.name.localeCompare(b.name, "tr") },
};

export default function Overview({
  cards,
  onOpen,
  onCreate,
  onDelete,
  suggestions,
  onAddSuggestion,
  onDismissSuggestion,
  scanning = false,
}) {
  const [sort, setSort] = useState("risk");

  // Katman 1: backend tier=1 verdiği kartlar, öncelik skoruna göre sıralı (en yüksek → sol).
  const tier1 = useMemo(
    () =>
      cards
        .filter((c) => c.tier === 1)
        .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)),
    [cards]
  );
  // Katman 2: kalan her şey, seçilen sıralamaya göre.
  const tier2 = useMemo(
    () => cards.filter((c) => c.tier !== 1).sort(SORTS[sort].fn),
    [cards, sort]
  );

  return (
    <div className="space-y-6">
      {cards.length === 0 ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-8 text-center text-slate-400">
          İzleme listesi boş. Aşağıdan bir varlık ekleyin.
        </div>
      ) : (
        <>
          {/* ── KATMAN 1 — "Bugün önemli" ─────────────────────────────── */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Bugün önemli
            </h2>
            {tier1.length > 0 ? (
              <div
                className={`stagger grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3 ${
                  scanning ? "scan-host rounded-xl" : ""
                }`}
              >
                {tier1.map((c) => (
                  <EntityCard key={c.id} card={c} onOpen={onOpen} big />
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-ink-600 bg-ink-800/50 px-4 py-6 text-center text-sm text-slate-400">
                Bugün önemli bir değişiklik yok — tüm varlıklar aşağıdaki listede.
              </div>
            )}
          </section>

          {/* ── KATMAN 2 — Tüm liste (sıkışık satırlar) ───────────────── */}
          {tier2.length > 0 && (
            <section className="space-y-2.5">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Liste ({tier2.length})
                </h2>
                <div className="flex items-center gap-1 text-[11px]">
                  <span className="mr-1 text-slate-500">Sırala:</span>
                  {Object.entries(SORTS).map(([key, { label }]) => (
                    <button
                      key={key}
                      onClick={() => setSort(key)}
                      className={`rounded px-2 py-0.5 transition ${
                        sort === key
                          ? "bg-accent/15 font-medium text-slate-100"
                          : "text-slate-500 hover:text-slate-300"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="stagger space-y-1.5">
                {tier2.map((c) => (
                  <EntityRow key={c.id} card={c} onOpen={onOpen} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {/* Öneriler — katlanabilir, varsayılan kapalı */}
      {suggestions.length > 0 && (
        <Collapsible title={`Öneriler (${suggestions.length})`}>
          <SuggestionsSection
            suggestions={suggestions}
            onAdd={onAddSuggestion}
            onDismiss={onDismissSuggestion}
            embedded
          />
        </Collapsible>
      )}

      {/* İzleme listesi — katlanabilir, varsayılan kapalı */}
      <Collapsible title={`İzleme listesi (${cards.length})`}>
        <WatchlistManager cards={cards} onCreate={onCreate} onDelete={onDelete} embedded />
      </Collapsible>
    </div>
  );
}

function Collapsible({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-semibold text-slate-200"
      >
        <span>{title}</span>
        <span className={`text-slate-500 transition ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && <div className="border-t border-ink-700 p-3">{children}</div>}
    </div>
  );
}
