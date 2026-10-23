// Pano: başlık · "birkaç şirket daha" satırı · Katman 1 (bugün önemli — kartlar) · Katman 2
// (liste — satırlar) · öneriler · izleme listesi. Ayrım çizgiyle değil boşluk, yüzey tonu ve
// tipografiyle. Boş durum ortak EmptyState; ilk yükleme gerçek düzeni taklit eden iskelet.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Plus, Radar, X } from "lucide-react";
import { useIsMobile } from "./ui.jsx";
import { tt } from "../i18n.jsx";
import EntityCard, { EntityRow } from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";
import SuggestionsSection from "./SuggestionsSection.jsx";
import { Button, Card, ChipButton, EmptyState, Skeleton, Tabs, cx, useFlip } from "./kit.jsx";

// "Tıkla-ekle" popüler başlangıç önerileri (boş durum + "birkaç şirket daha" satırı).
const STARTERS = [
  { name: "Tesla", type: "ticker", query: "TSLA" },
  { name: "Apple", type: "ticker", query: "AAPL" },
  { name: "NVIDIA", type: "ticker", query: "NVDA" },
  { name: "Microsoft", type: "ticker", query: "MSFT" },
  { name: "Amazon", type: "ticker", query: "AMZN" },
  { name: "OpenAI", type: "keyword", query: "OpenAI" },
];

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
    <ChipButton icon={Plus} onClick={() => onAdd(s)} disabled={adding === s.query}>
      {s.name}
      <span className="font-mono text-micro font-normal text-slate-500">
        {s.type === "ticker" ? "$" : "#"}
        {s.query}
      </span>
    </ChipButton>
  );
}

// Boş durum: landing'in tonunda kısa başlık, tek cümle, öneri çipleri.
function Empty({ onCreate, onHowItWorks }) {
  const { add, adding, err } = useStarterAdd(onCreate);
  return (
    <Card className="px-4">
      <EmptyState icon={Radar} title={tt("ov.emptyTitle")} body={tt("ov.emptyBody")}>
        <div className="flex flex-wrap justify-center gap-2">
          {STARTERS.map((s) => (
            <StarterChip key={s.query} s={s} onAdd={add} adding={adding} />
          ))}
        </div>
        {err && <p className="mt-3 text-meta text-rose-600">{err}</p>}
        <p className="mt-5 text-micro text-slate-500">
          {tt("ov.emptyNote")}
          {onHowItWorks && (
            <>
              {" · "}
              <button type="button" onClick={onHowItWorks} className="font-medium text-accent underline-offset-2 hover:underline">
                {tt("hiw.link")}
              </button>
            </>
          )}
        </p>
      </EmptyState>
    </Card>
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
    <section className="flex flex-col gap-3 sm:flex-row sm:items-center" aria-labelledby="more-starters-title">
      <h2 id="more-starters-title" className="shrink-0 text-meta font-medium text-slate-300">
        {tt("ov.moreTitle")}
      </h2>
      <div className="flex flex-1 flex-wrap gap-2">
        {left.map((s) => (
          <StarterChip key={s.query} s={s} onAdd={add} adding={adding} />
        ))}
      </div>
      <Button variant="ghost" size="sm" iconOnly icon={X} onClick={dismiss} title={tt("ov.moreDismiss")} aria-label={tt("ov.moreDismiss")} className="self-end sm:self-auto" />
      {err && <p className="text-meta text-rose-600">{err}</p>}
    </section>
  );
}

// Katman 2 sıralaması (Katman 1 zaten backend'de öncelik skoruyla seçilir).
const SORTS = {
  risk: { tkey: "ov.sortRisk", fn: (a, b) => (b.analysis?.risk_score ?? -1) - (a.analysis?.risk_score ?? -1) },
  alpha: { tkey: "ov.sortAlpha", fn: (a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name, "tr") },
};

function SectionTitle({ children, aside }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="font-display text-base font-semibold text-slate-100">{children}</h2>
      {aside}
    </div>
  );
}

// Katlanabilir bölüm (öneriler, izleme listesi): çerçeve yok, ince üst ayırıcı + başlık butonu.
function Collapsible({ title, children, openSignal = 0 }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (openSignal) setOpen(true);
  }, [openSignal]);
  return (
    <section className="border-t border-ink-600">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 py-4 text-left font-display text-base font-semibold text-slate-200 transition-colors duration-hover ease-std hover:text-slate-100"
      >
        <span>{title}</span>
        <ChevronRight className={cx("h-4 w-4 text-slate-500 transition-transform duration-hover ease-std", open && "rotate-90")} aria-hidden="true" />
      </button>
      {open && <div className="fade-in pb-6">{children}</div>}
    </section>
  );
}

// İlk yükleme iskeleti — pano düzeninin aynısı (başlık, kartlar, satırlar).
export function OverviewSkeleton() {
  return (
    <div className="space-y-10" aria-busy="true">
      <div>
        <Skeleton className="h-8 w-40" />
        <Skeleton className="mt-3 h-4 w-56" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="space-y-4 p-6">
            <div className="flex justify-between">
              <Skeleton className="h-6 w-28 rounded-full" />
              <Skeleton className="h-5 w-20" />
            </div>
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-4/5" />
            <Skeleton className="h-10 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </Card>
        ))}
      </div>
      <div className="space-y-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}

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
  const listRef = useRef(null);

  // Katman 1: backend tier=1 verdiği kartlar, öncelik skoruna göre sıralı.
  const tier1 = useMemo(
    () => cards.filter((c) => c.tier === 1).sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)),
    [cards]
  );
  const tier2 = useMemo(() => cards.filter((c) => c.tier !== 1).sort(SORTS[sort].fn), [cards, sort]);
  // Az şirket modu (backend hepsini tier=1 yaptı): kademe yok, hepsi kart, nötr başlık.
  const fewMode = tier1.length > 0 && tier2.length === 0;
  // MOBİL: en fazla 2 kart; kalan tier1 listeye düşer (3 şirket için 3 ekran kaydırılmasın).
  const bigCards = isMobile ? tier1.slice(0, 2) : tier1;
  const tier1Overflow = isMobile ? tier1.slice(2) : [];
  const listRows = [...tier1Overflow, ...tier2];
  useFlip(listRef, [listRows.map((c) => c.id).join(",")]);

  const cardGrid = (
    <div className={cx("stagger grid gap-4 md:grid-cols-2 xl:grid-cols-3", scanning && "scan-host rounded-card")}>
      {bigCards.map((c) => (
        <EntityCard key={c.id} card={c} onOpen={onOpen} />
      ))}
    </div>
  );
  const rows = (items) => (
    <div ref={listRef} className="space-y-1">
      {items.map((c) => (
        <div key={c.id} data-key={c.id}>
          <EntityRow card={c} onOpen={onOpen} />
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-page font-semibold text-slate-100">{tt("ov.title")}</h1>
        {cards.length > 0 && <p className="mt-1.5 text-meta text-slate-500">{tt("ov.count", { n: cards.length })}</p>}
      </header>

      <MoreStarters cards={cards} onCreate={onCreate} />

      {cards.length === 0 ? (
        <Empty onCreate={onCreate} onHowItWorks={onHowItWorks} />
      ) : fewMode ? (
        <section>
          <SectionTitle>{tt("ov.following")}</SectionTitle>
          {cardGrid}
          {tier1Overflow.length > 0 && <div className="mt-4">{rows(tier1Overflow)}</div>}
        </section>
      ) : (
        <>
          <section>
            <SectionTitle>{tt("ov.todayImportant")}</SectionTitle>
            {tier1.length > 0 ? cardGrid : <p className="rounded-card bg-ink-800 px-5 py-6 text-center text-body text-slate-400">{tt("ov.noChangeToday")}</p>}
          </section>
          {listRows.length > 0 && (
            <section>
              <SectionTitle
                aside={
                  <Tabs
                    variant="pill"
                    label={tt("ov.sortLabel")}
                    value={sort}
                    onChange={setSort}
                    items={Object.entries(SORTS).map(([key, { tkey }]) => ({ key, label: tt(tkey) }))}
                  />
                }
              >
                {tt("ov.list", { n: listRows.length })}
              </SectionTitle>
              {rows(listRows)}
            </section>
          )}
        </>
      )}

      <div>
        {suggestions.length > 0 && (
          <Collapsible title={tt("ov.suggestions", { n: suggestions.length })}>
            <SuggestionsSection suggestions={suggestions} onAdd={onAddSuggestion} onDismiss={onDismissSuggestion} embedded />
          </Collapsible>
        )}
        <Collapsible title={tt("ov.watchlist", { n: cards.length })} openSignal={focusAdd}>
          <WatchlistManager cards={cards} onCreate={onCreate} onDelete={onDelete} embedded focusSignal={focusAdd} />
        </Collapsible>
      </div>
    </div>
  );
}
