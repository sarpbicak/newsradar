// Genel görünüm: değişim şeridi + sıralama seçici + entity kartları + izleme listesi.
import React, { useMemo, useState } from "react";
import EntityCard from "./EntityCard.jsx";
import WatchlistManager from "./WatchlistManager.jsx";
import SuggestionsSection from "./SuggestionsSection.jsx";
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
      {/* "Nasıl okunur" mini rehber — ilk açılışta görünür, kapatılınca o oturum
          boyunca gizli (sessionStorage; localStorage değil). */}
      <HowToGuide />

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
                className="flex w-full flex-wrap items-center gap-x-2 text-left text-sm text-slate-300 hover:text-accent"
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
          {/* Sıralama seçici — kompakt */}
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

          <div
            className={`stagger grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 ${
              scanning ? "scan-host rounded-xl" : ""
            }`}
          >
            {sorted.map((c) => (
              <EntityCard key={c.id} card={c} onOpen={onOpen} />
            ))}
          </div>
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

// "Nasıl okunur" rehberi — finans bilmeyen kullanıcı için tek seferlik açıklama.
// Kapatılınca sessionStorage'a yazılır → o tarayıcı oturumunda bir daha çıkmaz
// (localStorage KULLANILMAZ; yeni oturumda tekrar hatırlatır).
const GUIDE_KEY = "nr_guide_dismissed";
function HowToGuide() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(GUIDE_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (dismissed) return null;

  function close() {
    try {
      sessionStorage.setItem(GUIDE_KEY, "1");
    } catch {
      /* sessionStorage yoksa yalnızca bu render için gizle */
    }
    setDismissed(true);
  }

  return (
    <div className="relative rounded-xl border border-accent/30 bg-accent/5 p-4 pr-10">
      <button
        onClick={close}
        aria-label="rehberi kapat"
        className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-md text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
      >
        ✕
      </button>
      <div className="mb-2 text-sm font-semibold text-slate-100">📖 Panel nasıl okunur?</div>
      <p className="text-sm leading-relaxed text-slate-400">
        Her kart bir şirketin son haberlerinin özeti.{" "}
        <strong className="font-semibold text-slate-200">Yön</strong> = haberler olumlu mu
        olumsuz mu. <strong className="font-semibold text-slate-200">Kanıt</strong> = değerlendirme
        ne kadar güvenilir (kaç habere dayanıyor).{" "}
        <strong className="font-semibold text-slate-200">Hedef fiyat</strong> = gerçek analistlerin
        beklentisi (bizim tahminimiz değil). En üstteki büyük cümle işin özeti.
      </p>
      {/* Renk anlamları — tutarlı: yeşil=olumlu, kırmızı=olumsuz/risk, gri=nötr/veri yok */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#16A34A" }} /> yeşil = olumlu
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#DC2626" }} /> kırmızı = olumsuz / risk
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#7A8699" }} /> gri = nötr / veri yok
        </span>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        Bu bir yatırım tavsiyesi değil — haber akışının özeti. Kararlar sana ait.
      </p>
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
