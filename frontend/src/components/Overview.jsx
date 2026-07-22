// Genel görünüm: entity kartları ızgarası + izleme listesi yöneticisi.
import React from "react";
import EntityCard from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";

export default function Overview({ cards, onOpen, onCreate, onDelete }) {
  return (
    <div className="space-y-6">
      {cards.length === 0 ? (
        <div className="rounded-xl border border-ink-600 bg-ink-800 p-8 text-center text-slate-400">
          İzleme listesi boş. Aşağıdan bir varlık ekleyin.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {cards.map((c) => (
            <EntityCard key={c.id} card={c} onOpen={onOpen} />
          ))}
        </div>
      )}

      <WatchlistManager cards={cards} onCreate={onCreate} onDelete={onDelete} />
    </div>
  );
}
