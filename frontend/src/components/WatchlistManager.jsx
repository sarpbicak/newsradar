// İzleme listesi yöneticisi: tip-bazlı form + sembol otomatik arama.
//  - ticker: Ad + Sembol zorunlu, dil yok. Ada yazarken sembol araması çıkar.
//  - keyword: sadece Ad (query=name), Sembol gizli, dil seçici görünür.
import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";
import { Button, ConfirmDialog, Field, Input, Select } from "./kit.jsx";
import { displayName } from "./EntityCard.jsx";

const LANGUAGES = [
  { code: "en", tkey: "lang.en" },
  { code: "tr", tkey: "lang.tr" },
  { code: "de", tkey: "lang.de" },
  { code: "fr", tkey: "lang.fr" },
];

export default function WatchlistManager({ cards, onCreate, onDelete, embedded = false, focusSignal = 0 }) {
  const { t } = useI18n();
  const nameInputRef = useRef(null);
  // "Kendi şirketlerinle dene" → ad alanına odaklan ve görünür kaydır.
  useEffect(() => {
    if (!focusSignal) return;
    const id = setTimeout(() => {
      nameInputRef.current?.focus();
      nameInputRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 60);
    return () => clearTimeout(id);
  }, [focusSignal]);
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
  const [confirmNonUs, setConfirmNonUs] = useState(null); // ABD dışı borsa sembolü → keyword önerisi

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
    // ABD dışı borsa: ticker olarak eklenirse haber/fiyat gelmez → keyword'e yönlendir (onay penceresi).
    if (!r.us_supported) {
      setConfirmNonUs(r);
      return;
    }
    // ABD sembolü: ticker alanlarını doldur (name değişince yeniden arama yapma).
    skipSearch.current = true;
    setName(r.description);
    setQuery(r.symbol);
    setResults([]);
    setSearched(false);
  }

  function acceptKeyword(r) {
    // Tip keyword'e geç, ad dolsun, dil önerisi uygulansın (type keyword olunca arama efekti erken döner).
    setConfirmNonUs(null);
    setType("keyword");
    setQuery("");
    setLanguage(r.suggested_language || "en");
    setName(r.description);
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
  if (!name.trim()) missing.push(t("wl.fieldName"));
  if (type === "ticker" && !query.trim()) missing.push(t("wl.symbol"));
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
    <div className={embedded ? "" : "rounded-card bg-ink-800 p-5"}>
      {!embedded && <h3 className="mb-4 font-display text-base font-medium text-slate-100">{t("wl.title")}</h3>}

      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[12rem_minmax(0,1fr)_8rem_auto] md:items-end">
        <Field label={t("wl.type")} htmlFor="wl-type">
          <Select id="wl-type" value={type} onChange={(e) => changeType(e.target.value)}>
            <option value="ticker">{t("wl.typeTicker")}</option>
            <option value="keyword">{t("wl.typeKeyword")}</option>
          </Select>
        </Field>

        {/* Ad — ticker'da arama kutusu (sembol önerileri), keyword'de arama terimi */}
        <Field label={type === "ticker" ? t("wl.nameSearch") : t("wl.nameTerm")} htmlFor="wl-name" className="relative">
          <Input
            id="wl-name"
            ref={nameInputRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={type === "ticker" ? "Tesla" : "Aselsan"}
            autoComplete="off"
          />
          {showDropdown && (searching || results.length > 0 || searched) && (
            <div className="fade-in absolute top-full z-20 mt-1.5 w-full overflow-hidden rounded-control bg-raised p-1 shadow-raised ring-1 ring-ink-600">
              {searching && <div className="px-3 py-2 text-meta text-slate-500">{t("wl.searching")}</div>}
              {!searching &&
                results.map((r) => (
                  <button
                    key={r.symbol}
                    type="button"
                    onClick={() => pickSymbol(r)}
                    className="tap block w-full rounded-lg px-3 py-2 text-left text-meta transition-colors duration-hover ease-std hover:bg-ink-700"
                  >
                    <span className={`flex items-center justify-between gap-2 ${r.us_supported ? "" : "opacity-70"}`}>
                      <span className="truncate text-slate-200">{r.description}</span>
                      <span className="shrink-0 font-mono text-slate-400">
                        {r.symbol} <span className="text-slate-500">({r.market})</span>
                      </span>
                    </span>
                    {!r.us_supported && (
                      <span className="mt-0.5 flex items-center gap-1 text-micro text-amber-600">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" /> {r.exchange_name} — {t("wl.nonUsShort")}
                      </span>
                    )}
                  </button>
                ))}
              {!searching && searched && results.length === 0 && <div className="px-3 py-2 text-meta text-amber-600">{t("wl.notFound")}</div>}
            </div>
          )}
        </Field>

        {type === "ticker" ? (
          <Field label={t("wl.symbol")} htmlFor="wl-symbol">
            <Input
              id="wl-symbol"
              mono
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase().replace(/\s+/g, ""))}
              placeholder="TSLA"
              autoComplete="off"
            />
          </Field>
        ) : (
          <Field label={t("wl.language")} htmlFor="wl-lang">
            <Select id="wl-lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {t(l.tkey)}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <Button type="submit" variant="primary" disabled={!canSubmit} title={missing.length ? t("wl.missing", { fields: missing.join(", ") }) : ""}>
          {busy ? t("wl.adding") : t("wl.add")}
        </Button>
      </form>
      {missing.length > 0 && name && <p className="mt-2 text-micro text-slate-500">{t("wl.missing", { fields: missing.join(", ") })}</p>}
      {err && <p className="mt-2 text-meta text-rose-600">{err}</p>}

      {cards.length > 0 && (
        <ul className="mt-5 flex flex-wrap gap-2">
          {cards.map((c) => (
            <li key={c.id} className="inline-flex items-center gap-2 rounded-full bg-ink-800 py-1 pl-3 pr-1 text-meta ring-1 ring-slate-100/5">
              <span className="text-slate-200">{displayName(c)}</span>
              <span className="font-mono text-micro text-slate-500">
                {c.type === "ticker" ? "$" : "#"}
                {c.query}
              </span>
              {c.language && c.language !== "en" && <span className="rounded-full bg-ink-700 px-1.5 text-micro uppercase text-slate-400">{c.language}</span>}
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                icon={X}
                onClick={() => onDelete(c.id)}
                aria-label={`${t("wl.remove")}: ${displayName(c)}`}
                title={t("wl.remove")}
                className="h-7 w-7 hover:text-rose-600"
              />
            </li>
          ))}
        </ul>
      )}

      {confirmNonUs && (
        <ConfirmDialog
          title={t("wl.nonUsTitle", { symbol: confirmNonUs.symbol })}
          body={t("wl.nonUsBody", { exchange: confirmNonUs.exchange_name })}
          confirmLabel={t("wl.nonUsConfirm")}
          cancelLabel={t("common.cancel")}
          onConfirm={() => acceptKeyword(confirmNonUs)}
          onCancel={() => setConfirmNonUs(null)}
        />
      )}
    </div>
  );
}
