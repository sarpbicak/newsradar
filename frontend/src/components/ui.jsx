// Paylaşılan UI atomları: rozetler, göstergeler, çipler.
import React, { useEffect, useRef, useState } from "react";
import { fmtPct, getLang, tt, timeAgo as _timeAgo } from "../i18n.jsx";
import { C, cssColor } from "../theme.js";

// timeAgo dil-farkında sürümü i18n'de; geriye uyum için buradan da dışa aç.
export const timeAgo = _timeAgo;

const REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Mobil kırılma noktası (<768px). matchMedia ile — kaydırmada değil, yalnızca
// gerçek genişlik değişince yeniden hesaplanır (ucuz). Tailwind `md:` ile hizalı.
export function useIsMobile(breakpoint = 768) {
  const query = `(max-width: ${breakpoint - 1}px)`;
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.(query).matches
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const onChange = (e) => setIsMobile(e.matches);
    setIsMobile(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return isMobile;
}

// Görünür viewport (visualViewport API) — iOS'ta klavye açılınca küçülen GERÇEK
// görünür alanı verir. Modal'ı klavyenin ÜSTÜNDE tutmak için kullanılır: klavye
// açılınca height küçülür, offsetTop kayar → "Gönder" butonu klavye arkasında kalmaz.
export function useVisualViewport() {
  const [vp, setVp] = useState(() => ({
    height: typeof window !== "undefined" ? window.innerHeight : 0,
    offsetTop: 0,
  }));
  useEffect(() => {
    const vv = typeof window !== "undefined" ? window.visualViewport : null;
    if (!vv) return;
    const onChange = () => setVp({ height: vv.height, offsetTop: vv.offsetTop });
    onChange();
    vv.addEventListener("resize", onChange);
    vv.addEventListener("scroll", onChange);
    return () => {
      vv.removeEventListener("resize", onChange);
      vv.removeEventListener("scroll", onChange);
    };
  }, []);
  return vp;
}

// Sayısal değerleri animasyonlu sayaçla gösterir (reduced-motion'da anında).
export function AnimatedNumber({ value, decimals = 0, prefix = "", suffix = "" }) {
  const [display, setDisplay] = useState(value ?? 0);
  const fromRef = useRef(value ?? 0);
  useEffect(() => {
    const to = value ?? 0;
    if (REDUCED_MOTION || fromRef.current === to) {
      setDisplay(to);
      fromRef.current = to;
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    const dur = 500;
    let raf;
    const tick = (t) => {
      const p = Math.min((t - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (to - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = to;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return (
    <span className="tabular-nums">
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

// Skeleton kutusu — yükleme sırasında layout zıplamasın.
export function Skeleton({ className = "" }) {
  return <div className={`skeleton ${className}`} />;
}

// --- Yön (stance) rozeti ---
const STANCE = {
  bullish: { label: "YÜKSELİŞ", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  neutral: { label: "NÖTR", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
  bearish: { label: "DÜŞÜŞ", cls: "bg-rose-500/15 text-rose-300 border-rose-500/30" },
};
const CONVICTION = { low: "düşük", medium: "orta", high: "yüksek" };

export function stanceLabel(stance) {
  return tt(`stance.${STANCE[stance] ? stance : "neutral"}`);
}

// Yön/vade/kanıt için renk + etiket yardımcıları. Koyu zeminde parlak sinyal tonları.
const STANCE_COLOR = { bullish: C.pos, neutral: C.neutral, bearish: C.neg };
export function stanceColor(stance) {
  return STANCE_COLOR[stance] || STANCE_COLOR.neutral;
}
export function horizonLabel(h) {
  return ["short", "medium", "long"].includes(h) ? tt(`horizon.${h}`) : "—";
}
export function evidenceLabel(e) {
  return ["strong", "medium", "weak"].includes(e) ? tt(`evidence.${e}`) : "—";
}
export function evidenceColor(e) {
  return { strong: C.pos, medium: C.warn, weak: C.neg }[e] || C.neutral;
}

// --- Düz Türkçe terim açıklamaları (tooltip metinleri; jargon yok) ---
export const TERM_HELP = {
  signal:
    "Genel sinyal: haberlerin yönünü ve ne kadar güvenilir olduğunu tek bir ölçekte " +
    "birleştirir — güçlü olumsuzdan güçlü olumluya. Bir fiyat tahmini değil.",
  direction:
    "Yön: haberler genel olarak olumlu mu (yükseliş), olumsuz mu (düşüş), yoksa " +
    "kararsız mı (nötr). Bir fiyat tahmini değil — haberlerin havası.",
  horizon:
    "Vade: haberlerin etkisinin ne kadar süreceği. Kısa = günler/haftalar, " +
    "Orta = birkaç ay, Uzun = daha uzun vade.",
  evidence:
    "Kanıt gücü: bu değerlendirmenin kaç habere ve ne kadar tutarlı sinyale " +
    "dayandığı. Zayıf = az/çelişkili haber, dikkatli ol. Güçlü = çok ve aynı yönde haber.",
  risk:
    "Risk skoru: 0 (düşük) – 100 (yüksek). Haberlerdeki risk işaretlerinin " +
    "(dava, rekabet, düzenleme…) yoğunluğu.",
  target:
    "Hedef fiyat: gerçek analistlerin ortalama beklentisi — bizim tahminimiz değil.",
  analyst:
    "Analist konsensüsü: gerçek borsa analistlerinin al/tut/sat dağılımı (Finnhub). " +
    "NewsRadar'ın kendi görüşü değil.",
};

// --- "?" ipucu — üstüne gelince/dokununca düz Türkçe açıklama gösterir ---
// Not: kart bir <div role=button> olduğundan içinde <button> kullanmak GEÇERLİDİR.
export function InfoTip({ text, className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <span className={`relative inline-flex ${className}`}>
      <button
        type="button"
        aria-label="açıklama"
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          setOpen((o) => !o);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-500 text-[9px] font-bold leading-none text-slate-500 transition hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-30 mb-1.5 w-52 max-w-[60vw] -translate-x-1/2 rounded-lg border border-ink-500 bg-ink-800 px-3 py-2 text-[11px] font-normal normal-case leading-snug tracking-normal text-slate-300 shadow-card-hover"
          style={{ pointerEvents: "none" }}
        >
          {text}
        </span>
      )}
    </span>
  );
}

// --- Genel sinyal: yön + kanıt gücünü 5 kademeli tek ölçeğe indirger ---
// Sol (güçlü olumsuz, kırmızı) → sağ (güçlü olumlu, yeşil). Fiyat tahmini DEĞİL.
const SIGNAL_LEVELS = [
  { key: -2, tkey: "sig.strongNeg", color: C.negStrong },
  { key: -1, tkey: "sig.neg", color: C.neg },
  { key: 0, tkey: "sig.neutral", color: C.neutral },
  { key: 1, tkey: "sig.pos", color: C.pos },
  { key: 2, tkey: "sig.strongPos", color: C.posStrong },
];

// Beş durumun renk eşlemesi tek yerde. Beklenmedik stance/evidence (büyük-küçük harf,
// boş) → NÖTR (gri). ASLA koyu/siyaha düşmez. label dile göre çevrilir.
const NEUTRAL = SIGNAL_LEVELS.find((l) => l.key === 0);
export function overallSignal(stance, evidence) {
  const s = String(stance || "").toLowerCase();
  const base = s === "bullish" ? 1 : s === "bearish" ? -1 : 0;
  const strong = String(evidence || "").toLowerCase() === "strong";
  const level = base === 0 ? 0 : base > 0 ? (strong ? 2 : 1) : strong ? -2 : -1;
  const lvl = SIGNAL_LEVELS.find((l) => l.key === level) || NEUTRAL;
  return { ...lvl, label: tt(lvl.tkey) };
}

// Durum "pill" stili: güçlü uçlar dolu (zıt metin); ortalar soluk dolgu+renkli metin. Kontrast
// iki temada AA (≥4.5:1) — renkler src/index.css'te.
const PILL_STYLE = {
  "2": { bg: C.posStrong, color: C.onStrong },               // GÜÇLÜ OLUMLU (dolu)
  "1": { bg: cssColor("pos", 0.12), color: C.pos },           // OLUMLU (soluk dolgu)
  "0": { bg: cssColor("neutral", 0.14), color: C.neutral },   // NÖTR
  "-1": { bg: cssColor("neg", 0.10), color: C.neg },          // OLUMSUZ (soluk dolgu)
  "-2": { bg: C.negStrong, color: C.onStrong },               // GÜÇLÜ OLUMSUZ (dolu)
};

// Büyük, dolgulu, uzaktan okunan DURUM etiketi (kartın en dikkat çekici öğesi).
export function SignalPill({ stance, evidence }) {
  const sig = overallSignal(stance, evidence);
  const st = PILL_STYLE[String(sig.key)] || PILL_STYLE["0"];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-wide"
      style={{ background: st.bg, color: st.color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: st.color }} />
      {sig.label}
    </span>
  );
}

// TEK durum etiketi: yön · güç ("BULLISH · Medium"). Güç YALNIZCA evidence_strength'ten
// (kanaat + haber sayısı + tutarlılıktan türetilen kanonik alan; genel bakış kartıyla aynı)
// — conviction ayrıca gösterilmez, çelişki olmaz. Renk overallSignal ile aynı.
export function StatusTag({ stance, evidence }) {
  const sig = overallSignal(stance, evidence);
  const st = PILL_STYLE[String(sig.key)] || PILL_STYLE["0"];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold tracking-wide"
      style={{ background: st.bg, color: st.color }}
    >
      <span className="uppercase">{stanceLabel(stance)}</span>
      {evidence && <span className="font-semibold">· {evidenceLabel(evidence)}</span>}
    </span>
  );
}

export function SignalBand({ stance, evidence, showLabel = true, minimal = false }) {
  const sig = overallSignal(stance, evidence);
  // -2..2 → %0..100 konum (olumsuz sol, olumlu sağ).
  const pos = ((sig.key + 2) / 4) * 100;
  return (
    <div>
      {showLabel && (
        // minimal (kart): sadece sağda durum metni. Tam (detay): solda "Genel sinyal".
        <div className={`mb-1.5 flex items-center ${minimal ? "justify-end" : "justify-between"}`}>
          {!minimal && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {tt("sig.overall")}
            </span>
          )}
          <span className="text-xs font-bold" style={{ color: sig.color }}>
            {sig.label}
          </span>
        </div>
      )}
      {/* Yumuşak spektrum (olumsuz→nötr(gri)→olumlu) + konum işaretçisi. Renkler temaya bağlı. */}
      <div
        className="relative h-2 rounded-full"
        style={{
          background:
            `linear-gradient(90deg, ${cssColor("neg", 0.55)} 0%, ${cssColor("neg", 0.22)} 28%, ${cssColor("neutral", 0.2)} 50%, ${cssColor("pos", 0.22)} 72%, ${cssColor("pos", 0.55)} 100%)`,
        }}
        aria-label={`Genel sinyal: ${sig.label}`}
      >
        <span
          className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-800 transition-all duration-300"
          style={{ left: `${pos}%`, background: sig.color, boxShadow: `0 0 0 1px ${cssColor("slate-100", 0.08)}` }}
          title={sig.label}
        />
      </div>
    </div>
  );
}

// --- Fiyat gösterimi (yalnızca ticker; price null ise hiç render etme) ---
// Burada fiyat ARTIŞI yeşil (iyi), düşüş kırmızı — risk deltasının TERSİ.
export function PriceDisplay({ price, changePercent, updatedAt, showTime = true }) {
  if (price == null) return null;
  const up = (changePercent ?? 0) >= 0;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="font-mono font-semibold text-slate-100">
        <AnimatedNumber value={price} decimals={2} prefix="$" />
      </span>
      {changePercent != null && (
        <span className={`font-mono text-xs font-medium ${up ? "text-emerald-400" : "text-rose-400"}`}>
          {fmtPct(changePercent, { digits: 2 })}
        </span>
      )}
      {showTime && updatedAt && (
        <span className="text-[10px] text-slate-500" title="fiyatın çekilme zamanı">
          {timeAgo(updatedAt)}
        </span>
      )}
    </span>
  );
}

// --- Risk değişim rozeti (son taramaya göre) ---
// Risk için ARTIŞ kötü (kırmızı ▲), AZALIŞ iyi (yeşil ▼). Değişim yoksa gizli.
export function RiskDelta({ delta }) {
  if (!delta || !delta.risk_delta) return null;
  const up = delta.risk_delta > 0;
  return (
    <span
      className={`text-xs font-bold ${up ? "text-rose-400" : "text-emerald-400"}`}
      title="son taramaya göre risk değişimi"
    >
      {up ? "▲+" : "▼"}
      {delta.risk_delta}
    </span>
  );
}

export function StanceBadge({ stance, conviction }) {
  const s = STANCE[stance] || STANCE.neutral;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${s.cls}`}>
      {stanceLabel(stance)}
      {conviction && (
        <span className="font-normal">
          · {tt(`conviction.${["low", "medium", "high"].includes(conviction) ? conviction : "medium"}`)} {tt("conviction.suffix")}
        </span>
      )}
    </span>
  );
}

// --- Risk skoru rengi (0 yeşil → 100 kırmızı) ---
export function riskColor(score) {
  if (score == null) return C.neutral;
  if (score < 34) return C.pos;
  if (score < 67) return C.warn;
  return C.neg;
}

export function RiskScore({ score }) {
  const color = riskColor(score);
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-9 w-9 shrink-0">
        <svg viewBox="0 0 36 36" className="h-9 w-9 -rotate-90">
          <circle cx="18" cy="18" r="15" fill="none" stroke={cssColor("ink-600")} strokeWidth="4" />
          <circle
            cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${(2 * Math.PI * 15 * (score ?? 0)) / 100} ${2 * Math.PI * 15}`}
            strokeLinecap="round"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-[11px] font-bold" style={{ color }}>
          {score ?? "–"}
        </span>
      </div>
      <div className="text-xs text-slate-400 leading-tight">
        <div className="text-slate-300 font-medium">{tt("sum.riskLabel")}</div>
        <div>{score == null ? tt("sum.riskNone") : tt("sum.riskScale")}</div>
      </div>
    </div>
  );
}

// --- Duygu göstergesi (-1..1) ---
export function SentimentGauge({ value }) {
  const v = value ?? 0;
  const pct = ((v + 1) / 2) * 100; // -1..1 -> 0..100
  const color = v > 0.15 ? C.pos : v < -0.15 ? C.neg : C.neutral;
  return (
    <div className="w-full">
      <div className="flex justify-between text-[10px] text-slate-500 mb-1">
        <span>−</span>
        <span className="text-slate-400">
          {tt("gauge.sentiment")} {value == null ? "–" : v.toFixed(2)}
        </span>
        <span>+</span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-ink-600">
        <div className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-ink-800"
             style={{ left: `calc(${pct}% - 6px)`, background: color }} />
      </div>
    </div>
  );
}

// --- Trend oku ---
export function TrendArrow({ trend }) {
  const icons = { improving: "▲", stable: "▬", deteriorating: "▼" };
  const clsMap = { improving: "text-emerald-400", stable: "text-slate-400", deteriorating: "text-rose-400" };
  const key = icons[trend] ? trend : "stable";
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${clsMap[key]}`}>
      <span>{icons[key]}</span>
      <span className="text-slate-400">{tt(`trend.${key}`)}</span>
    </span>
  );
}

// --- Risk bayrağı çipi (iki dilli) ---
const FLAG_LABELS = {
  regulatory: { tr: "düzenleme", en: "regulatory" },
  competition: { tr: "rekabet", en: "competition" },
  financial: { tr: "finansal", en: "financial" },
  legal: { tr: "hukuki", en: "legal" },
  product: { tr: "ürün", en: "product" },
  supply_chain: { tr: "tedarik", en: "supply chain" },
  macro: { tr: "makro", en: "macro" },
  reputation: { tr: "itibar", en: "reputation" },
};
export function flagLabel(f) {
  const e = FLAG_LABELS[f];
  return e ? e[getLang()] || e.tr : f;
}
export function FlagChip({ flag }) {
  return (
    <span className="rounded border border-ink-500 bg-ink-700 px-1.5 py-0.5 text-[10px] text-slate-300">
      {flagLabel(flag)}
    </span>
  );
}

const EVENT_LABELS = {
  earnings: { tr: "bilanço", en: "earnings" }, product: { tr: "ürün", en: "product" },
  regulation: { tr: "düzenleme", en: "regulation" }, lawsuit: { tr: "dava", en: "lawsuit" },
  partnership: { tr: "ortaklık", en: "partnership" }, funding: { tr: "yatırım", en: "funding" },
  macro: { tr: "makro", en: "macro" }, leadership: { tr: "yönetim", en: "leadership" },
  other: { tr: "diğer", en: "other" },
};
export function eventLabel(e) {
  const x = EVENT_LABELS[e];
  return x ? x[getLang()] || x.tr : e || "–";
}

