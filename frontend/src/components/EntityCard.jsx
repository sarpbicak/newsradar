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
import {
  AnimatedNumber, HorizonToggle, NewsPill, divergenceText, hasHorizons, newsSignal, riskColor, targetOf, targetSourceLabel,
  useHorizon,
} from "./ui.jsx";
import { Card, Chip, cx } from "./kit.jsx";
import { tt, fmtPct, getLang } from "../i18n.jsx";
import { fmtMoney } from "../money.js";
import { C } from "../theme.js";

// Analiz yoksa NEDEN: dil eksik · bekleyen haber var (yenileme işe yarar) · pencerede haber yok
// (yenileme işe yaramaz; yeni haber çıkınca kendiliğinden güncellenir). short: liste satırı.
export function noAnalysisText(card, short = false) {
  if (card.analysis_missing_language) return tt("card.langMissing");
  if (card.no_analysis_reason === "few_news") return tt("card.fewNews", { days: card.news_window_days ?? 2 });
  return short ? tt("card.noAnalysisYet") : tt("card.pressRefresh", { refresh: tt("header.refresh") });
}

export const displayName = (e) => e.display_name || e.name;
export const symbolOf = (e) => `${e.type === "ticker" ? "$" : "#"}${e.query}`;
// ABD dışı hissede borsa · ülke ("XETRA · Almanya"); ABD ve keyword'de null (gürültü olmasın).
export const marketLabel = (e) => (e.us_market === false && e.exchange ? `${e.exchange} · ${e.country}` : null);

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
  const target = targetOf(entity.analyst);
  const upside = entity.analyst?.upside_percent;
  // ABD dışı borsa: fiyat/analist kaynağı yok (yuva boş) → borsayı adıyla söyle.
  if (price == null) {
    return (
      <p className="text-meta text-slate-500">
        {entity.us_market === false ? tt("card.noPriceExchange", { exchange: entity.exchange }) : tt("card.noPrice")} · {tt("card.newsOnly")}
      </p>
    );
  }
  // Fiyat kendi para biriminde, dile uygun ondalıkla (dönüşüm yok).
  const cur = entity.currency || "USD";
  const lang = getLang();
  const num = cx(size === "lg" ? "text-title" : "text-body", muted && "!text-slate-500");
  const tone = (v) => (muted ? "text-slate-500" : v >= 0 ? "text-emerald-600" : "text-rose-600");
  return (
    <div className="flex items-start gap-3">
      <div>
        <div className={cx("flex items-baseline gap-2 font-mono font-semibold tabular-nums text-slate-100", num)}>
          <AnimatedNumber value={price} format={(v) => fmtMoney(v, cur, lang)} />
          {chg != null && <span className={cx("text-meta font-medium", tone(chg))}>{fmtPct(chg, { digits: 2 })}</span>}
        </div>
        <div className="text-micro text-slate-500">{tt("card.now")}</div>
      </div>
      {target != null && (
        <>
          <ArrowRight className={cx("h-4 w-4 shrink-0 text-slate-600", size === "lg" ? "mt-2" : "mt-1")} aria-hidden="true" />
          <div>
            <div className={cx("flex items-baseline gap-2 font-mono font-semibold tabular-nums text-slate-100", num)}>
              {fmtMoney(target, cur, lang, { digits: 0 })}
              {upside != null && <span className={cx("text-meta font-medium", tone(upside))}>{fmtPct(upside)}</span>}
            </div>
            <div className="text-micro text-slate-500">{targetSourceLabel(entity.analyst)}</div>
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
  const [horizon, setHorizon] = useHorizon();
  const edge = a ? newsSignal(a, card.evidence_strength, horizon).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const diverge = a ? divergenceText(a, card.evidence_strength, card.analyst, horizon) : null;
  // Ayrışma notu görünüyorsa aynı bilgiyi taşıyan "ayrışma" çipi tekrarlanmaz.
  const priority = diverge && card.priority_reason === "divergence" ? null : card.priority_reason;
  const open = () => onOpen(card.id);
  return (
    // Kart düz bir kutu: fareyle her yeri açar; klavye/ekran okuyucu için tüm kartı kaplayan TEK
    // açma düğmesi var. Vade seçici bu düğmenin üstünde (iç içe etkileşimli öğe yok — axe).
    <Card interactive onClick={open} className="card-cq relative flex h-full flex-col gap-4 overflow-hidden p-5 text-left md:p-6">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          open();
        }}
        aria-label={tt("card.openDetail", { name: displayName(card) })}
        className="absolute inset-0 rounded-card focus-visible:[outline-offset:-2px]"
      />
      <span className="absolute inset-x-0 top-0 h-0.5" style={{ background: edge }} aria-hidden="true" />

      {/* Başlık: sabit en az yükseklik (iki satırlık ad + sembol) → hüküm her kartta aynı hizada. */}
      <div className="flex min-h-14 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words font-display text-base font-medium leading-tight text-slate-100">{displayName(card)}</div>
          <div className="mt-1 font-mono text-micro text-slate-500">
            {symbolOf(card)}
            {marketLabel(card) && <span className="font-sans"> · {card.exchange}</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!a && <Chip tone="muted">{tt(card.analysis_missing_language ? "card.langMissingShort" : "card.noAnalysis")}</Chip>}
          {priority && <PriorityChip reason={priority} />}
        </div>
      </div>
      {a && (
        <div className="-mt-1 flex flex-wrap items-center justify-between gap-2">
          <NewsPill a={a} evidence={card.evidence_strength} horizon={horizon} />
          {hasHorizons(a) && <HorizonToggle value={horizon} onChange={setHorizon} compact className="relative z-10" />}
        </div>
      )}

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
            {diverge && (
              <p className="flex items-center gap-1.5 text-micro text-slate-400">
                <GitFork className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden="true" />
                {diverge}
              </p>
            )}
            <p className="text-micro text-slate-500">
              {tt("card.newsCount", { n: card.evidence_count })}
              {changed && <span className="text-amber-600"> · {tt("card.stanceChanged")}</span>}
            </p>
          </div>
        </>
      ) : (
        // Kullanıcının dilinde analiz yoksa diğer dili sessizce göstermek yerine açık not.
        <p className="mt-auto text-body text-slate-400">
          {noAnalysisText(card)}
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
  const [horizon] = useHorizon();
  const edge = a ? newsSignal(a, card.evidence_strength, horizon).color : C.subtle;
  const changed = a && card.delta?.stance_changed;
  const verdict = a ? a.headline_verdict || a.summary : noAnalysisText(card, true);
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
        {a && (
          <span className="mt-1 flex md:mt-0 md:w-60 md:shrink-0">
            <NewsPill a={a} evidence={card.evidence_strength} horizon={horizon} />
          </span>
        )}
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
