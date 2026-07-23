// İzleme listesi yöneticisi: tip-bazlı form + sembol otomatik arama.
//  - ticker: Ad + Sembol zorunlu, dil yok. Ada yazarken sembol araması çıkar.
//  - keyword: sadece Ad (query=name), Sembol gizli, dil seçici görünür.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const LANGUAGES = [
  { code: "en", label: "İngilizce" },
  { code: "tr", label: "Türkçe" },
  { code: "de", label: "Almanca" },
  { code: "fr", label: "Fransızca" },
];

export default function WatchlistManager({ cards, onCreate, onDelete }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("ticker");
  const [query, setQuery] = useState(""); // sembol (yalnızca ticker)
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // Sembol arama durumu (yalnızca ticker).
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const skipSearch = useRef(false); // öneri seçilince tekrar aramayı bastır

  // Ada yazarken (ticker, ≥2 karakter, 400ms debounce) sembol ara.
  useEffect(() => {
    if (type !== "ticker") {
      setResults([]);
      setSearched(false);
      return;
    }
    if (skipSearch.current) {
      skipSearch.current = false;
      return;
    }
    const q = name.trim();
    if (q.length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.searchSymbols(q);
        setResults(r);
        setSearched(true);
      } catch {
        setResults([]);
        setSearched(true);
      } finally {
        setSearching(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [name, type]);

  function pickSymbol(r) {
    // ABD dışı borsa: ticker olarak eklenirse haber/fiyat gelmez → keyword'e yönlendir.
    if (!r.us_supported) {
      const ok = window.confirm(
        `${r.symbol} — ${r.exchange_name}. Bu borsa için haber/fiyat verisi (Finnhub) yok; ` +
          `keyword olarak eklemeniz önerilir.\n\nKeyword olarak devam edilsin mi?`
      );
      if (!ok) return;
      // Tip keyword'e geç, ad dolsun, dil önerisi uygulansın. (type keyword olunca
      // arama efekti erken döner; skipSearch gerekmez.)
      setType("keyword");
      setQuery("");
      setLanguage(r.suggested_language || "en");
      setName(r.description);
      setResults([]);
      setSearched(false);
      return;
    }
    // ABD sembolü: ticker alanlarını doldur (name değişince yeniden arama yapma).
    skipSearch.current = true;
    setName(r.description);
    setQuery(r.symbol);
    setResults([]);
    setSearched(false);
  }

  function changeType(next) {
    setType(next);
    setResults([]);
    setSearched(false);
    if (next === "keyword") setQuery(""); // keyword'de sembol yok
  }

  // Eksik alanlar (tip-bazlı).
  const missing = [];
  if (!name.trim()) missing.push("Ad");
  if (type === "ticker" && !query.trim()) missing.push("Sembol");
  const canSubmit = missing.length === 0 && !busy;

  async function submit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setErr(null);
    try {
      const payload =
        type === "ticker"
          ? { name: name.trim(), type: "ticker", query: query.trim(), language: "en" }
          : { name: name.trim(), type: "keyword", query: name.trim(), language };
      await onCreate(payload);
      setName("");
      setQuery("");
      setResults([]);
      setSearched(false);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  }

  const showDropdown = type === "ticker" && name.trim().length >= 2;

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-200">İzleme Listesi</h3>

      <form onSubmit={submit} className="mb-3 flex flex-wrap items-end gap-2">
        {/* Tip */}
        <div className="flex flex-col">
          <label className="mb-1 text-[10px] uppercase text-slate-500">Tip</label>
          <select
            value={type}
            onChange={(e) => changeType(e.target.value)}
            className="rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
          >
            <option value="ticker">ticker (ABD hissesi)</option>
            <option value="keyword">keyword (şirket/konu)</option>
          </select>
        </div>

        {/* Ad — ticker'da arama kutusu, keyword'de arama terimi */}
        <div className="relative flex flex-col">
          <label className="mb-1 text-[10px] uppercase text-slate-500">
            {type === "ticker" ? "Ad (ara)" : "Ad / arama terimi"}
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={type === "ticker" ? "Tesla" : "Aselsan"}
            autoComplete="off"
            className="w-48 rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
          />

          {/* Sembol arama açılır listesi (yalnızca ticker) */}
          {showDropdown && (searching || results.length > 0 || searched) && (
            <div className="absolute top-full z-20 mt-1 w-72 overflow-hidden rounded-md border border-ink-500 bg-ink-900 shadow-xl">
              {searching && (
                <div className="px-3 py-2 text-xs text-slate-500">Aranıyor…</div>
              )}
              {!searching &&
                results.map((r) => (
                  <button
                    key={r.symbol}
                    type="button"
                    onClick={() => pickSymbol(r)}
                    className="block w-full px-3 py-1.5 text-left text-xs hover:bg-ink-700"
                  >
                    <div
                      className={`flex items-center justify-between gap-2 ${
                        r.us_supported ? "" : "opacity-60"
                      }`}
                    >
                      <span className="truncate text-slate-200">{r.description}</span>
                      <span className="shrink-0 font-mono text-slate-400">
                        {r.symbol}
                        <span className="ml-1 text-slate-600">({r.market})</span>
                      </span>
                    </div>
                    {!r.us_supported && (
                      <div className="mt-0.5 text-[10px] text-amber-400/80">
                        ⚠ {r.exchange_name} — haber/fiyat yok, keyword önerilir
                      </div>
                    )}
                  </button>
                ))}
              {!searching && searched && results.length === 0 && (
                <div className="px-3 py-2 text-xs text-amber-300">
                  Bulunamadı — Türk/Avrupa şirketleri için tip olarak{" "}
                  <strong>keyword</strong> seçip dili ayarlayın.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sembol — yalnızca ticker */}
        {type === "ticker" && (
          <div className="flex flex-col">
            <label className="mb-1 text-[10px] uppercase text-slate-500">Sembol</label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase().replace(/\s+/g, ""))}
              placeholder="TSLA"
              autoComplete="off"
              className="w-28 rounded-md border border-ink-500 bg-ink-900 px-2 py-1 font-mono text-sm outline-none focus:border-accent"
            />
          </div>
        )}

        {/* Dil — yalnızca keyword */}
        {type === "keyword" && (
          <div className="flex flex-col">
            <label className="mb-1 text-[10px] uppercase text-slate-500">Dil</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="rounded-md border border-ink-500 bg-ink-900 px-2 py-1 text-sm outline-none focus:border-accent"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        )}

        <button
          disabled={!canSubmit}
          title={missing.length ? `Eksik: ${missing.join(", ")}` : ""}
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Ekleniyor…" : "Ekle"}
        </button>

        {missing.length > 0 && (
          <span className="text-[11px] text-slate-500">Eksik: {missing.join(", ")}</span>
        )}
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
            {c.language && c.language !== "en" && (
              <span className="rounded bg-ink-600 px-1 text-[10px] uppercase text-slate-400">
                {c.language}
              </span>
            )}
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
