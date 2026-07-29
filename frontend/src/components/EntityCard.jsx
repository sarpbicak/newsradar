// KESİN SPEC kartı — 4 satır:
// 1) Durum pill (sol, büyük dolgulu) + şirket adı/ticker (sağ, tek satır)
// 2) Hüküm cümlesi (TAM, kesme yok, 3 satıra kadar sarar)
// 3) Fiyat bloğu (çerçeveli kutu: şimdi → analist hedefi + %)
// 4) Meta (küçük soluk: vade · N haber · yön değişti)
// Tüm kartlar aynı yükseklik (h-full + flex; fiyat+meta alta yapışır).
import React from "react";
import { ArrowRight } from "lucide-react";
import { SignalPill, overallSignal, AnimatedNumber, horizonLabel } from "./ui.jsx";

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

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const sig = a ? overallSignal(a.stance, card.evidence_strength) : null;
  const stripColor = sig ? sig.color : "transparent";
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
      className="group relative flex h-full cursor-pointer flex-col gap-4 overflow-hidden rounded-xl border border-ink-600 bg-ink-800 p-5 pl-6 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      {/* Sol kenar durum şeridi (pill rengiyle aynı) */}
      <span className="absolute inset-y-0 left-0 w-1.5" style={{ background: a ? stripColor : "#3A4152" }} />

      {/* Satır 1 — Durum pill (sol) + ad/ticker (sağ, tek satır) */}
      <div className="flex items-start justify-between gap-3">
        {a ? (
          <SignalPill stance={a.stance} evidence={card.evidence_strength} />
        ) : (
          <span className="inline-flex items-center rounded-full bg-ink-700 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
            analiz yok
          </span>
        )}
        <div className="min-w-0 text-right">
          <div className="truncate font-display text-base font-semibold text-slate-100">{card.name}</div>
          <div className="font-mono text-[11px] text-slate-500">
            {card.type === "ticker" ? "$" : "#"}{card.query}
          </div>
        </div>
      </div>

      {a ? (
        <>
          {/* Satır 2 — Hüküm cümlesi (TAM, kesme yok) */}
          <p className="font-display text-[17px] font-semibold leading-snug text-slate-100">
            {a.headline_verdict || a.summary}
          </p>

          {/* Satır 3 + 4 alta yapışır (tüm kartlar hizalı) */}
          <div className="mt-auto space-y-3">
            <PriceBox card={card} />
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
