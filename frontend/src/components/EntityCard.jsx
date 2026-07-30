// KESİN SPEC kartı — 4 satır:
// 1) Durum pill (sol, büyük dolgulu) + şirket adı/ticker (sağ, tek satır)
// 2) Hüküm cümlesi (TAM, kesme yok, 3 satıra kadar sarar)
// 3) Fiyat bloğu (çerçeveli kutu: şimdi → analist hedefi + %)
// 4) Meta (küçük soluk: vade · N haber · yön değişti)
// Tüm kartlar aynı yükseklik (h-full + flex; fiyat+meta alta yapışır).
import React from "react";
import { ArrowRight } from "lucide-react";
import { SignalPill, overallSignal, AnimatedNumber, horizonLabel } from "./ui.jsx";

// Kompakt analist barı — al/tut/sat segmentleri + baskın görüş + analist sayısı.
const ANALYST_SEG = [
  { key: "strong_buy", color: "#0B7A42" },
  { key: "buy", color: "#0F8A4C" },
  { key: "hold", color: "#A8A49B" },
  { key: "sell", color: "#C62828" },
  { key: "strong_sell", color: "#A81E1E" },
];
function analystLean(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: "Al ağırlıklı", color: "#0F8A4C" };
  if (sellish > a.hold && sellish > buyish) return { text: "Sat ağırlıklı", color: "#C62828" };
  return { text: "Tut ağırlıklı", color: "#7A7770" };
}
function AnalystMiniBar({ a }) {
  const total = a.total || 1;
  const lean = analystLean(a);
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="whitespace-nowrap font-medium" style={{ color: lean.color }}>{lean.text}</span>
      <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700">
        {ANALYST_SEG.map((s) => {
          const n = a[s.key] || 0;
          if (!n) return null;
          return <div key={s.key} style={{ width: `${(n / total) * 100}%`, background: s.color }} />;
        })}
      </div>
      <span className="whitespace-nowrap text-slate-500">{a.total} analist</span>
    </div>
  );
}

function PriceBox({ card }) {
  const isTicker = card.type === "ticker";
  const price = card.price;
  const target = card.analyst?.target_mean;
  const upside = card.analyst?.upside_percent;

  // Ortak kutu kabuğu — tüm kartlarda aynı yükseklik.
  const shell = "rounded-lg border border-ink-600 bg-ink-900/40 px-3 py-2.5";

  // Keyword ya da fiyatsız: aynı kutu, ortalanmış açıklama.
  if (!isTicker || price == null) {
    return (
      <div className={`${shell} text-center`}>
        <div className="text-sm text-slate-400">
          {isTicker ? "Fiyat verisi yok" : "Borsada işlem görmüyor"}
        </div>
        <div className="mt-0.5 text-[10px] text-slate-500">sadece haber analizi</div>
      </div>
    );
  }

  return (
    <div className={shell}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1 text-center">
          <div className="font-mono text-base font-semibold tabular-nums text-slate-100">
            <AnimatedNumber value={price} decimals={2} prefix="$" />
          </div>
          <div className="text-[10px] text-slate-500">şimdi</div>
        </div>
        <ArrowRight className="h-4 w-4 shrink-0 text-slate-500" />
        <div className="min-w-0 flex-1 text-center">
          <div className="font-mono text-base font-semibold tabular-nums text-slate-100">
            {target != null ? (
              <>
                ${target.toFixed(0)}
                {upside != null && (
                  <span className={`ml-1 ${upside >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {upside >= 0 ? "+" : "−"}%{Math.abs(Math.round(upside))}
                  </span>
                )}
              </>
            ) : (
              <span className="text-slate-500">—</span>
            )}
          </div>
          <div className="text-[10px] text-slate-500">
            {target != null ? "analist hedefi" : "hedef yok"}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function EntityCard({ card, onOpen, big = false }) {
  const a = card.analysis;
  // Sol şerit rengi: analiz varsa duruma göre (5 durum + nötr gri); YOKSA açık gri.
  // ASLA koyu/siyah — eski #3A4152 fallback'i kağıt temada siyah görünüyordu.
  const stripColor = a ? overallSignal(a.stance, card.evidence_strength).color : "#D8D3C7";
  const changed = a && card.delta?.stance_changed;

  function open() {
    onOpen(card.id);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      className={`group relative flex h-full cursor-pointer flex-col gap-4 overflow-hidden rounded-xl border bg-ink-800 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 ${
        big ? "border-accent/30 p-6 pl-7" : "border-ink-600 p-5 pl-6 hover:border-accent/60"
      }`}
    >
      {/* Sol kenar durum şeridi (pill rengiyle aynı; Katman 1'de daha kalın) */}
      <span className={`absolute inset-y-0 left-0 ${big ? "w-2" : "w-1.5"}`} style={{ background: stripColor }} />

      {/* Satır 1 — Durum pill (sol) + ad/ticker (sağ, tek satır) */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {a ? (
            <SignalPill stance={a.stance} evidence={card.evidence_strength} />
          ) : (
            <span className="inline-flex items-center rounded-full bg-ink-700 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
              analiz yok
            </span>
          )}
          {/* Katman 1 nedeni — neden "bugün önemli" olduğunu tek kelimeyle söyler */}
          {big && card.priority_reason && (
            <span className="inline-flex items-center rounded-full bg-accent/15 px-2.5 py-1 text-[11px] font-semibold text-accent">
              {card.priority_reason}
            </span>
          )}
        </div>
        <div className="min-w-0 text-right">
          <div className={`truncate font-display font-semibold text-slate-100 ${big ? "text-lg" : "text-base"}`}>{card.name}</div>
          <div className="font-mono text-[11px] text-slate-500">
            {card.type === "ticker" ? "$" : "#"}{card.query}
          </div>
        </div>
      </div>

      {a ? (
        <>
          {/* Satır 2 — Hüküm cümlesi (SERİF, editöryel; TAM, kesme yok) */}
          <p className={`font-serif font-semibold leading-snug text-slate-100 ${big ? "text-[23px]" : "text-[19px]"}`}>
            {a.headline_verdict || a.summary}
          </p>

          {/* Satır 3 + analist + meta alta yapışır (tüm kartlar hizalı) */}
          <div className="mt-auto space-y-2.5">
            <PriceBox card={card} />
            {/* Analist barı — yalnızca ticker + tavsiye verisi olan */}
            {card.type === "ticker" && card.analyst?.total > 0 && <AnalystMiniBar a={card.analyst} />}
            <div className="text-xs text-slate-500">
              {horizonLabel(card.horizon)} vade
              <span className="text-slate-600"> · </span>
              {card.evidence_count} haber
              {changed && <span className="text-amber-400"> · yön değişti</span>}
            </div>
          </div>
        </>
      ) : (
        <div className="mt-auto text-sm text-slate-400">
          Henüz analiz yok — <strong className="text-slate-200">Yenile</strong>'ye basın.
        </div>
      )}
    </div>
  );
}

// Katman 2 — sıkışık tek satır (~48px). Sol şerit + ad + ticker + hüküm (kısaltılmış) + risk.
export function EntityRow({ card, onOpen }) {
  const a = card.analysis;
  const stripColor = a ? overallSignal(a.stance, card.evidence_strength).color : "#D8D3C7";
  const changed = a && card.delta?.stance_changed;
  return (
    <button
      onClick={() => onOpen(card.id)}
      className="group flex w-full items-center gap-3 overflow-hidden rounded-lg border border-ink-600 bg-ink-800 py-2 pl-0 pr-3 text-left transition hover:border-accent/50 hover:-translate-y-px hover:shadow-card"
    >
      <span className="h-9 w-1.5 shrink-0 self-stretch rounded-r" style={{ background: stripColor }} />
      <span className="w-28 shrink-0 truncate font-display text-sm font-semibold text-slate-100 sm:w-32">
        {card.name}
      </span>
      <span className="hidden w-14 shrink-0 truncate font-mono text-[11px] text-slate-500 sm:block">
        {card.type === "ticker" ? "$" : "#"}{card.query}
      </span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-slate-400">
        {a ? a.headline_verdict || a.summary : "Henüz analiz yok"}
      </span>
      {changed && <span className="hidden shrink-0 text-[11px] font-medium text-amber-400 md:inline">yön değişti</span>}
      {a && (
        <span
          className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums"
          style={{ background: `${stripColor}22`, color: stripColor }}
          title="Risk skoru"
        >
          {a.risk_score}
        </span>
      )}
    </button>
  );
}
