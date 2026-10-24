// Pano kartı — landing hero'daki canlı karar kartının dili (araç ölçeğinde):
//  1) durum etiketi (dolgulu, anlamsal) + varsa ikincil bilgi çipi · sağda kısa ad + sembol
//  2) hüküm cümlesi (Inter Display ~21px, kesilmez)
//  3) fiyat satırı: $212.21 → $339 +60% (çerçevesiz; altında "şimdi / analist hedefi")
//  4) analist dağılımı: "Analistler: alım yönlü" + ince bar + analist sayısı
//  5) meta (vade · haber sayısı · yön değişti) — en alta yapışır; kartlar aynı yükseklikte.
// Renk göstergesi: üst kenarda ince (2px) anlamsal çizgi. Kısa ad: display_name, yoksa ad
// (iki satıra kadar sarar, asla kesilmez).
import React from "react";
import { Activity, ArrowLeftRight, ArrowRight, Compass, GitFork, Lock, TrendingUp, Zap } from "lucide-react";
import { AnimatedNumber, SignalPill, horizonLabel, overallSignal, riskColor } from "./ui.jsx";
import { Card, Chip, cx } from "./kit.jsx";
import { tt, fmtPct } from "../i18n.jsx";
import { C } from "../theme.js";

export const displayName = (e) => e.display_name || e.name;
export const symbolOf = (e) => `${e.type === "ticker" ? "$" : "#"}${e.query}`;

// Analist dağılımı (al → sat) ve baskın görüşün TAVSİYE GİBİ OKUNMAYAN etiketi.
const ANALYST_SEG = [
  { key: "strong_buy", color: C.posStrong },
  { key: "buy", color: C.pos },
  { key: "hold", color: C.subtle },
  { key: "sell", color: C.neg },
  { key: "strong_sell", color: C.negStrong },
];
export function analystLean(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: tt("card.buyLean"), color: C.pos };
  if (sellish > a.hold && sellish > buyish) return { text: tt("card.sellLean"), color: C.neg };
  return { text: tt("card.holdLean"), color: C.neutral };
}

export function AnalystBar({ a, className = "" }) {
  const total = a.total || 1;
  const lean = analystLean(a);
  return (
    <div className={cx("flex items-center gap-3 text-micro", className)}>
      <span className="whitespace-nowrap font-medium" style={{ color: lean.color }}>{lean.text}</span>
      <div className="flex h-1 flex-1 overflow-hidden rounded-[2px] bg-ink-700" aria-hidden="true">
        {ANALYST_SEG.map((s) => {
          const n = a[s.key] || 0;
          return n ? <div key={s.key} style={{ width: `${(n / total) * 100}%`, background: s.color }} /> : null;
        })}
      </div>
      <span className="whitespace-nowrap tabular-nums text-slate-500">{tt("card.analysts", { n: a.total })}</span>
    </div>
  );
}

// Fiyat satırı: şimdi → analist hedefi (kart ve detay aynı dil).
// muted: hedef verisi eski (detay) — renkler soluk ama AA (slate-500), opaklık değil.
export function PriceRow({ entity, size = "md", muted = false }) {
  const price = entity.price;
  const chg = entity.change_percent;
  const target = entity.analyst?.target_mean;
  const upside = entity.analyst?.upside_percent;
  if (price == null) return <p className="text-meta text-slate-500">{tt("card.noPrice")} · {tt("card.newsOnly")}</p>;
  const num = cx(size === "lg" ? "text-title" : "text-body", muted && "!text-slate-500");
  const tone = (v) => (muted ? "text-slate-500" : v >= 0 ? "text-emerald-600" : "text-rose-600");
  return (
    <div className="flex items-start gap-3">
      <div>
        <div className={cx("flex items-baseline gap-2 font-mono font-semibold tabular-nums text-slate-100", num)}>
          <AnimatedNumber value={price} decimals={2} prefix="$" />
          {chg != null && <span className={cx("text-meta font-medium", tone(chg))}>{fmtPct(chg, { digits: 2 })}</span>}
        </div>
        <div className="text-micro text-slate-500">{tt("card.now")}</div>
      </div>
      {target != null && (
        <>
          <ArrowRight className={cx("h-4 w-4 shrink-0 text-slate-600", size === "lg" ? "mt-2" : "mt-1")} aria-hidden="true" />
          <div>
            <div className={cx("flex items-baseline gap-2 font-mono font-semibold tabular-nums text-slate-100", num)}>
              ${target.toFixed(0)}
              {upside != null && <span className={cx("text-meta font-medium", tone(upside))}>{fmtPct(upside)}</span>}
            </div>
            <div className="text-micro text-slate-500">{tt("card.analystTarget")}</div>
          </div>
        </>
      )}
    </div>
  );
}

function PrivateLine({ drivers }) {
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1.5 text-meta text-slate-400">
        <Lock className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
        {tt("card.privateShort")}
      </p>
      {drivers?.[0] && (
        <p className="text-micro text-slate-500">
          <span className="font-medium">{tt("card.topDriver")}</span> <span className="text-slate-400">{drivers[0]}</span>
        </p>
      )}
    </div>
  );
}

// "Bugün önemli" nedeni (sert hareket, risk sıçraması…): genişte çip, darda ikon + açıklama.
const PRIORITY_ICON = { stance_reversed: ArrowLeftRight, stance_clarified: Compass, risk_jump: TrendingUp, sharp_move: Activity, divergence: GitFork };
function PriorityChip({ reason }) {
  const label = tt(`pr.${reason}`);
  const Icon = PRIORITY_ICON[reason] || Zap;
  return (
    <>
      <Chip tone="neutral" className="chip-full">{label}</Chip>
      <span className="chip-compact h-7 w-7 shrink-0 items-center justify-center rounded-control bg-ink-700 text-slate-300" title={label}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">{label}</span>
      </span>
    </>
  );
}

export default function EntityCard({ card, onOpen }) {
  const a = card.analysis;
  const edge = a ? overallSignal(a.stance, card.evidence_strength).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const open = () => onOpen(card.id);
  return (
    <Card
      interactive
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      className="card-cq relative flex h-full flex-col gap-4 overflow-hidden p-5 text-left md:p-6"
    >
      <span className="absolute inset-x-0 top-0 h-0.5" style={{ background: edge }} aria-hidden="true" />

      {/* Başlık: sabit en az yükseklik (iki satırlık ad + sembol) → hüküm her kartta aynı hizada. */}
      <div className="flex min-h-14 items-start justify-between gap-3">
        <div className="flex min-w-0 flex-nowrap items-center gap-2">
          {a ? <SignalPill stance={a.stance} evidence={card.evidence_strength} /> : <Chip tone="muted">{tt(card.analysis_missing_language ? "card.langMissingShort" : "card.noAnalysis")}</Chip>}
          {card.priority_reason && <PriorityChip reason={card.priority_reason} />}
        </div>
        <div className="min-w-0 basis-2/5 text-right">
          <div className="break-words font-display text-base font-medium leading-tight text-slate-100">{displayName(card)}</div>
          <div className="mt-1 font-mono text-micro text-slate-500">{symbolOf(card)}</div>
        </div>
      </div>

      {a ? (
        <>
          <p className="font-display text-title font-medium text-slate-100">{a.headline_verdict || a.summary}</p>
          <div className="mt-auto space-y-3">
            {card.type === "ticker" ? (
              <>
                <PriceRow entity={card} />
                {card.analyst?.total > 0 && <AnalystBar a={card.analyst} />}
              </>
            ) : (
              <PrivateLine drivers={a.top_drivers} />
            )}
            <p className="text-micro text-slate-500">
              {tt("card.horizon", { h: horizonLabel(card.horizon) })} · {tt("card.newsCount", { n: card.evidence_count })}
              {changed && <span className="text-amber-600"> · {tt("card.stanceChanged")}</span>}
            </p>
          </div>
        </>
      ) : (
        // Kullanıcının dilinde analiz yoksa diğer dili sessizce göstermek yerine açık not.
        <p className="mt-auto text-body text-slate-400">
          {card.analysis_missing_language ? tt("card.langMissing") : tt("card.pressRefresh", { refresh: tt("header.refresh") })}
        </p>
      )}
    </Card>
  );
}

// Liste satırı: ince renk göstergesi · kısa ad · sembol · tek satır değerlendirme (tooltip'te
// tamamı) · sağda risk skoru (mono) ve varsa "yön değişti". Satırlar ince çizgilerle ayrılır (tablo).
// Mobilde değerlendirme adın altına iner (iki satıra kadar).
export function EntityRow({ card, onOpen }) {
  const a = card.analysis;
  const edge = a ? overallSignal(a.stance, card.evidence_strength).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const verdict = a ? a.headline_verdict || a.summary : tt(card.analysis_missing_language ? "card.langMissing" : "card.noAnalysisYet");
  return (
    <button
      type="button"
      onClick={() => onOpen(card.id)}
      title={verdict}
      className="group flex w-full items-center gap-3 px-2 py-3 text-left transition-colors duration-hover ease-std hover:bg-ink-800"
    >
      <span className="h-9 w-0.5 shrink-0 self-center rounded-full" style={{ background: edge }} aria-hidden="true" />
      <span className="min-w-0 flex-1 md:flex md:items-center md:gap-4">
        <span className="flex items-baseline gap-2 md:w-56 md:shrink-0">
          <span className="break-words font-display text-sm font-medium text-slate-100">{displayName(card)}</span>
          <span className="shrink-0 font-mono text-micro text-slate-500">{symbolOf(card)}</span>
        </span>
        <span className="mt-0.5 line-clamp-2 text-meta text-slate-400 md:mt-0 md:line-clamp-1 md:flex-1">{verdict}</span>
      </span>
      {changed && <span className="hidden shrink-0 text-micro font-medium text-amber-600 md:inline">{tt("card.stanceChanged")}</span>}
      {a && (
        <span className="w-8 shrink-0 text-right font-mono text-meta font-semibold tabular-nums" style={{ color: riskColor(a.risk_score) }} title={tt("sum.riskLabel")}>
          {a.risk_score}
        </span>
      )}
    </button>
  );
}
