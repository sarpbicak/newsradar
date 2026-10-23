// Genel görünüm: Katman 1 (bugün önemli — büyük kartlar) + Katman 2 (liste — satırlar).
import React, { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { useIsMobile } from "./ui.jsx";
import { tt } from "../i18n.jsx";
import EntityCard, { EntityRow } from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";
import SuggestionsSection from "./SuggestionsSection.jsx";

// Boş liste için "tıkla-ekle" popüler başlangıç önerileri.
const STARTERS = [
  { name: "Tesla", type: "ticker", query: "TSLA" },
  { name: "Apple", type: "ticker", query: "AAPL" },
  { name: "NVIDIA", type: "ticker", query: "NVDA" },
  { name: "Microsoft", type: "ticker", query: "MSFT" },
  { name: "Amazon", type: "ticker", query: "AMZN" },
  { name: "OpenAI", type: "keyword", query: "OpenAI" },
];

// Başlangıç önerisine tıkla-ekle (boş durum ve "birkaç şirket daha" satırı ortak kullanır).
function useStarterAdd(onCreate) {
  const [adding, setAdding] = useState(null);
  const [err, setErr] = useState(null);
  async function add(s) {
    setAdding(s.query);
    setErr(null);
    try {
      await onCreate({ ...s, language: "en" });
    } catch (e) {
      setErr(e.message);
    } finally {
      setAdding(null);
    }
  }
  return { add, adding, err };
}

function StarterChip({ s, onAdd, adding }) {
  return (
    <button
      onClick={() => onAdd(s)}
      disabled={adding === s.query}
      className="inline-flex items-center gap-1.5 rounded-lg border border-ink-500 bg-ink-700 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-accent/60 hover:bg-accent/10 disabled:opacity-60"
    >
      <Plus className="h-3.5 w-3.5 text-accent" />
      {s.name}
      <span className="font-mono text-[11px] text-slate-500">
        {s.type === "ticker" ? "$" : "#"}{s.query}
      </span>
    </button>
  );
}

// Boş durum: yeni kullanıcı için açıklama + popüler şirketlerle hızlı başlangıç.
function EmptyState({ onCreate, onHowItWorks }) {
  const { add, adding, err } = useStarterAdd(onCreate);
  return (
    <div className="rounded-2xl border border-ink-600 bg-ink-800 p-8 text-center">
      <h2 className="font-display text-xl font-bold text-slate-100">
        {tt("ov.emptyTitle")}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-[15px] leading-relaxed text-slate-400">
        {tt("ov.emptyBody")}
      </p>
      {onHowItWorks && (
        <button
          onClick={onHowItWorks}
          className="mt-3 text-sm font-medium text-accent underline underline-offset-2 hover:text-accent-hover"
        >
          {tt("hiw.link")}
        </button>
      )}
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {STARTERS.map((s) => (
          <StarterChip key={s.query} s={s} onAdd={add} adding={adding} />
        ))}
      </div>
      {err && <p className="mt-3 text-xs text-rose-400">{err}</p>}
      <p className="mt-4 text-xs text-slate-500">
        {tt("ov.emptyNote")}
      </p>
    </div>
  );
}

// "Birkaç şirket daha ekle": listede 3'ten az şirket varken listenin üstünde kalır. Eklenen
// öneri düşer, yerine sıradaki gelir; × ile kapatılır (tercih bu cihazda saklanır); 3 şirkete
// ulaşınca kendiliğinden kaybolur.
const MORE_MIN = 3;
const MORE_SHOWN = 4;
const MORE_DISMISS_KEY = "nr_more_starters_dismissed";

function readDismissed() {
  try {
    return localStorage.getItem(MORE_DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

function MoreStarters({ cards, onCreate }) {
  const { add, adding, err } = useStarterAdd(onCreate);
  const [dismissed, setDismissed] = useState(readDismissed);
  if (dismissed || cards.length === 0 || cards.length >= MORE_MIN) return null;
  const have = (s) =>
    cards.some((c) => (c.query || "").toLowerCase() === s.query.toLowerCase() || (c.name || "").toLowerCase() === s.name.toLowerCase());
  const left = STARTERS.filter((s) => !have(s)).slice(0, MORE_SHOWN);
  if (left.length === 0) return null;
  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(MORE_DISMISS_KEY, "1");
    } catch {
      /* depolama kapalıysa yalnızca bu oturumda gizli */
    }
  }
  return (
    <section className="rounded-xl border border-ink-600 bg-ink-800/60 p-3 sm:p-4" aria-labelledby="more-starters-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="more-starters-title" className="text-sm font-semibold text-slate-200">
          {tt("ov.moreTitle")}
        </h2>
        <button
          onClick={dismiss}
          title={tt("ov.moreDismiss")}
          aria-label={tt("ov.moreDismiss")}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {left.map((s) => (
          <StarterChip key={s.query} s={s} onAdd={add} adding={adding} />
        ))}
      </div>
      {err && <p className="mt-2 text-xs text-rose-400">{err}</p>}
    </section>
  );
}

// Katman 2 sıralaması (Katman 1 zaten backend'de öncelik skoruyla seçilir).
const SORTS = {
  risk: {
    tkey: "ov.sortRisk",
    fn: (a, b) => (b.analysis?.risk_score ?? -1) - (a.analysis?.risk_score ?? -1),
  },
  alpha: { tkey: "ov.sortAlpha", fn: (a, b) => a.name.localeCompare(b.name, "tr") },
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
  onHowItWorks,
  focusAdd = 0,
}) {
  const [sort, setSort] = useState("risk");
  const isMobile = useIsMobile();

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
  // Az şirket modu (backend hepsini tier=1 yaptı): kademe yok, hepsi büyük kart,
  // nötr başlık — "Bugün önemli değişiklik" iddiası olmadan sayfa dolu görünür.
  const fewMode = tier1.length > 0 && tier2.length === 0;

  // MOBİL: en fazla 2 büyük kart göster; geri kalan tier1 kartları listeye (satır) düşer.
  // Böylece 3 şirket için 3 ekran kaydırmak gerekmez. MASAÜSTÜ: hepsi büyük kart.
  const bigCards = isMobile ? tier1.slice(0, 2) : tier1;
  const tier1Overflow = isMobile ? tier1.slice(2) : [];
  // Listede: taşan tier1 kartları (öncelikli, en üstte) + sıralı tier2.
  const listRows = [...tier1Overflow, ...tier2];

  const bigGrid = (
    <div
      className={`stagger grid grid-cols-1 gap-4 md:gap-5 md:grid-cols-2 lg:grid-cols-3 ${
        scanning ? "scan-host rounded-xl" : ""
      }`}
    >
      {bigCards.map((c) => (
        <EntityCard key={c.id} card={c} onOpen={onOpen} big />
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
      <MoreStarters cards={cards} onCreate={onCreate} />
      {cards.length === 0 ? (
        <EmptyState onCreate={onCreate} onHowItWorks={onHowItWorks} />
      ) : fewMode ? (
        /* ── AZ ŞİRKET — büyük kart(lar), nötr başlık ─────────────── */
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {tt("ov.following")}
          </h2>
          {bigGrid}
          {/* MOBİL: 2'den fazla varsa kalanı sıkışık liste olarak göster */}
          {tier1Overflow.length > 0 && (
            <div className="stagger space-y-1.5 pt-1">
              {tier1Overflow.map((c) => (
                <EntityRow key={c.id} card={c} onOpen={onOpen} />
              ))}
            </div>
          )}
        </section>
      ) : (
        <>
          {/* ── KATMAN 1 — "Bugün önemli" ─────────────────────────────── */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {tt("ov.todayImportant")}
            </h2>
            {tier1.length > 0 ? (
              bigGrid
            ) : (
              <div className="rounded-xl border border-dashed border-ink-600 bg-ink-800/50 px-4 py-6 text-center text-sm text-slate-400">
                {tt("ov.noChangeToday")}
              </div>
            )}
          </section>

          {/* ── KATMAN 2 — Tüm liste (sıkışık satırlar) + mobilde taşan tier1 ── */}
          {listRows.length > 0 && (
            <section className="space-y-2.5">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  {tt("ov.list", { n: listRows.length })}
                </h2>
                <div className="flex items-center gap-1 text-[11px]">
                  <span className="mr-1 text-slate-500">{tt("ov.sort")}</span>
                  {Object.entries(SORTS).map(([key, { tkey }]) => (
                    <button
                      key={key}
                      onClick={() => setSort(key)}
                      className={`min-h-[32px] rounded px-2 py-1 transition ${
                        sort === key
                          ? "bg-accent/15 font-medium text-slate-100"
                          : "text-slate-500 hover:text-slate-300"
                      }`}
                    >
                      {tt(tkey)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="stagger space-y-1.5">
                {listRows.map((c) => (
                  <EntityRow key={c.id} card={c} onOpen={onOpen} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {/* Öneriler — katlanabilir, varsayılan kapalı */}
      {suggestions.length > 0 && (
        <Collapsible title={tt("ov.suggestions", { n: suggestions.length })}>
          <SuggestionsSection
            suggestions={suggestions}
            onAdd={onAddSuggestion}
            onDismiss={onDismissSuggestion}
            embedded
          />
        </Collapsible>
      )}

      {/* İzleme listesi — katlanabilir, varsayılan kapalı */}
      <Collapsible title={tt("ov.watchlist", { n: cards.length })} openSignal={focusAdd}>
        <WatchlistManager cards={cards} onCreate={onCreate} onDelete={onDelete} embedded focusSignal={focusAdd} />
      </Collapsible>
    </div>
  );
}

// openSignal değişince (ör. "Kendi şirketlerinle dene") kendiliğinden açılır.
function Collapsible({ title, children, openSignal = 0 }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (openSignal) setOpen(true);
  }, [openSignal]);
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
