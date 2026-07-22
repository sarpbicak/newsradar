// İzleme listesi yöneticisi: ticker/keyword tip seçiciyle ekle/çıkar.
import React, { useState } from "react";

export default function WatchlistManager({ cards, onCreate, onDelete }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("ticker");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!name.trim() || !query.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await onCreate({ name: name.trim(), type, query: query.trim() });
      setName("");
      setQuery("");
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-200">İzleme Listesi</h3>

      <form onSubmit={submit} className="mb-3 flex flex-wrap items-end gap-2">
        <div className="flex flex-col">
          <label className="mb-1 text-[10px] uppercase text-slate-500">Ad</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tesla"
            className="w-32 rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
          />
        </div>
        <div className="flex flex-col">
          <label className="mb-1 text-[10px] uppercase text-slate-500">Tip</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
          >
            <option value="ticker">ticker (public)</option>
            <option value="keyword">keyword (startup)</option>
          </select>
        </div>
        <div className="flex flex-col">
          <label className="mb-1 text-[10px] uppercase text-slate-500">
            {type === "ticker" ? "Sembol" : "Arama"}
          </label>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={type === "ticker" ? "TSLA" : "Anthropic"}
            className="w-32 rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
          />
        </div>
        <button
          disabled={busy}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Ekleniyor…" : "Ekle"}
        </button>
      </form>
      {err && <p className="mb-2 text-xs text-rose-400">{err}</p>}

      <ul className="flex flex-wrap gap-2">
        {cards.map((c) => (
          <li
            key={c.id}
            className="flex items-center gap-2 rounded-md border border-ink-500 bg-ink-700 px-2 py-1 text-xs"
          >
            <span className="text-slate-200">{c.name}</span>
            <span className="font-mono text-slate-500">
              {c.type === "ticker" ? "$" : "#"}
              {c.query}
            </span>
            <button
              onClick={() => onDelete(c.id)}
              title="Kaldır"
              className="text-slate-500 hover:text-rose-400"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
