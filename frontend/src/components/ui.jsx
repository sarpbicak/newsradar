// Paylaşılan UI atomları: rozetler, göstergeler, çipler.
import React, { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ArrowDown, ArrowUp, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { fmtDateTime, fmtPct, getLang, tt, timeAgo as _timeAgo } from "../i18n.jsx";
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
// from: ilk gösterimde sayılmaya başlanacak değer (ör. 0 → landing rakamları kısa bir sayma
// animasyonuyla gelir). Verilmezse ilk değer doğrudan gösterilir, yalnızca DEĞİŞİMLER sayılır.
// format: görüntüleme biçimi (varsayılan toFixed). prefers-reduced-motion → animasyonsuz.
export function AnimatedNumber({ value, decimals = 0, prefix = "", suffix = "", from, format }) {
  const [display, setDisplay] = useState(from ?? value ?? 0);
  const fromRef = useRef(from ?? value ?? 0);
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
      {format ? format(display) : display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

// Skeleton kutusu — ortak bileşen kütüphanesinden (geri uyum için buradan da dışa açık).
export { Skeleton } from "./kit.jsx";

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
// Gösterilen analist hedefi: medyan (varsa) ya da FMP konsensüs ortalaması. Kart, detay ve
// "Nasıl çalışır" aynı değeri ve aynı kaynak notunu kullanır ("Medyan hedef, FMP").
export const targetOf = (a) => a?.target ?? a?.target_mean ?? null;
export const isMedianTarget = (a) => a?.target_kind === "median";
export const targetSourceLabel = (a) => tt(isMedianTarget(a) ? "an.srcMedian" : "an.srcAvg");

export function evidenceLabel(e) {
  return ["strong", "medium", "weak"].includes(e) ? tt(`evidence.${e}`) : "—";
}
export function evidenceColor(e) {
  return { strong: C.pos, medium: C.warn, weak: C.neg }[e] || C.neutral;
}

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
          className="absolute bottom-full left-1/2 z-30 mb-1.5 w-52 max-w-[60vw] -translate-x-1/2 rounded-lg border border-ink-500 bg-ink-800 px-3 py-2 text-[11px] font-normal normal-case leading-snug tracking-normal text-slate-300"
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

// Durum etiketi: köşeli (4px), ince renkli kenar + renkli nokta + metin; büyük harf yok.
// Güçlü uçlar hafif dolgulu ve yarı kalın, ortalar yalnızca kenarlı. Metin rengi anlamsal ton:
// iki temada yüzeylerde AA (≥4.5:1) — renkler src/index.css'te.
const PILL_STYLE = {
  "2": { color: C.posStrong, bg: cssColor("pos", 0.1), border: cssColor("pos", 0.45), strong: true },
  "1": { color: C.pos, bg: "transparent", border: cssColor("pos", 0.35) },
  "0": { color: C.neutral, bg: "transparent", border: cssColor("neutral", 0.35) },
  "-1": { color: C.neg, bg: "transparent", border: cssColor("neg", 0.35) },
  "-2": { color: C.negStrong, bg: cssColor("neg", 0.08), border: cssColor("neg", 0.45), strong: true },
};

function TagShell({ st, children }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2 py-0.5 text-micro ${st.strong ? "font-semibold" : "font-medium"}`}
      style={{ background: st.bg, color: st.color, borderColor: st.border }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: st.color }} aria-hidden="true" />
      {children}
    </span>
  );
}

// --- Kısa / uzun vade (haber yönü) ---
// Seçim cihaz tercihi: tüm kartlar ve detay aynı vadeyi gösterir; localStorage'da saklanır
// (gizli pencere / kapalı depolama → bellekte "short").
const HZ_KEY = "nr_horizon";
let _hz = "short";
try {
  if (localStorage.getItem(HZ_KEY) === "long") _hz = "long";
} catch {
  /* depolama kapalı */
}
const _hzSubs = new Set();
export function setHorizon(h) {
  _hz = h === "long" ? "long" : "short";
  try {
    localStorage.setItem(HZ_KEY, _hz);
  } catch {
    /* depolama kapalı — yalnızca bu oturum */
  }
  _hzSubs.forEach((f) => f());
}
export function useHorizon() {
  const h = useSyncExternalStore(
    (cb) => {
      _hzSubs.add(cb);
      return () => _hzSubs.delete(cb);
    },
    () => _hz,
    () => "short",
  );
  return [h, setHorizon];
}

const VERDICT_LEVEL = { very_negative: -2, negative: -1, neutral: 0, positive: 1, very_positive: 2 };
const LEVEL_KEY = { "-2": "verdict.veryNeg", "-1": "verdict.neg", 0: "verdict.neutral", 1: "verdict.pos", 2: "verdict.veryPos" };
export const levelLabel = (level) => tt(LEVEL_KEY[level]);
export const levelColor = (level) => (SIGNAL_LEVELS.find((l) => l.key === level) || NEUTRAL).color;
export const hasHorizons = (a) => !!(a?.short_term || a?.long_term);
export const horizonOf = (a, h) => (h === "long" ? a?.long_term : a?.short_term);
export const horizonName = (h) => tt(h === "long" ? "hz.long" : "hz.short");

// Vade hükmü → { level (-2..2 | null), label }. mixed / insufficient_data → level null.
export function verdictInfo(v) {
  if (v && v.verdict in VERDICT_LEVEL) {
    const level = VERDICT_LEVEL[v.verdict];
    return { level, label: levelLabel(level) };
  }
  if (v?.verdict === "mixed") return { level: null, label: tt("verdict.mixed"), mixed: true };
  return { level: null, label: tt("verdict.noData"), noData: true };
}

// Haber etiketi: "Haberler · kısa vade: Olumsuz". Vadesiz (eski) analiz → "Haberler: Olumlu"
// (yön + kanıt gücünden tek etiket). level: renk ve ayrışma hesabı için.
export function newsSignal(a, evidence, horizon) {
  if (hasHorizons(a)) {
    const v = verdictInfo(horizonOf(a, horizon));
    return { ...v, text: tt("news.labelH", { h: horizonName(horizon), v: v.label }), color: v.level == null ? C.neutral : levelColor(v.level) };
  }
  const sig = overallSignal(a?.stance, evidence);
  return { level: sig.key, label: sig.label, text: tt("news.label", { v: sig.label }), color: sig.color };
}

// Analist görüşü: Finnhub tavsiyelerinin ağırlıklı skoru (güçlü al +2 … güçlü sat −2) → 5 kademe.
export function analystLevel(an) {
  const total = an?.total || 0;
  if (!total) return null;
  const score = (2 * an.strong_buy + an.buy - an.sell - 2 * an.strong_sell) / total;
  const level = score <= -1.2 ? -2 : score <= -0.4 ? -1 : score < 0.4 ? 0 : score < 1.2 ? 1 : 2;
  return { level, score, label: levelLabel(level) };
}

// Ayrışma: kısa↔uzun vade ve/veya haber↔analist yönleri ZIT mı (nötr ayrışma sayılmaz)?
export function divergence(a, evidence, analyst, horizon) {
  const s = verdictInfo(a?.short_term).level;
  const l = verdictInfo(a?.long_term).level;
  const news = newsSignal(a, evidence, horizon).level;
  const al = analystLevel(analyst)?.level;
  return { horizons: s != null && l != null && s * l < 0, vsAnalysts: news != null && al != null && news * al < 0 };
}

// Ayrışma notu (tek satır; kart). Detayda göstergelerin altındaki not kullanılır.
export function divergenceText(a, evidence, analyst, horizon) {
  const { horizons, vsAnalysts } = divergence(a, evidence, analyst, horizon);
  if (horizons && vsAnalysts) return tt("div.both");
  if (horizons) return tt("div.horizons");
  if (vsAnalysts) return tt("div.newsAnalysts");
  return null;
}

// Haber etiketi (kart, satır, detay aynı).
export function NewsPill({ a, evidence, horizon }) {
  const sig = newsSignal(a, evidence, horizon);
  const st = sig.level == null ? PILL_STYLE["0"] : PILL_STYLE[String(sig.level)];
  return <TagShell st={st}>{sig.text}</TagShell>;
}

// Kısa / uzun vade seçici (iki düğme, aria-pressed). Kart bir role=button olduğundan tık ve
// klavye olayları karta taşmaz. compact: kartta "Kısa | Uzun".
export function HorizonToggle({ value, onChange, compact = false, className = "" }) {
  return (
    <div role="group" aria-label={tt("hz.toggle")} className={`inline-flex shrink-0 rounded-control border border-ink-600 p-0.5 ${className}`}>
      {["short", "long"].map((h) => (
        <button
          key={h}
          type="button"
          aria-pressed={value === h}
          onClick={(e) => {
            e.stopPropagation();
            onChange(h);
          }}
          onKeyDown={(e) => e.stopPropagation()}
          className={`min-h-7 rounded-[5px] px-2.5 text-micro font-medium transition-colors duration-hover ease-std ${
            value === h ? "bg-ink-700 text-slate-100" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {tt(compact ? (h === "long" ? "hz.longC" : "hz.shortC") : h === "long" ? "hz.longBtn" : "hz.shortBtn")}
        </button>
      ))}
    </div>
  );
}

// TEK durum etiketi: yön · güç ("Olumlu · orta"). Güç YALNIZCA evidence_strength'ten
// (kanaat + haber sayısı + tutarlılıktan türetilen kanonik alan; genel bakış kartıyla aynı)
// — conviction ayrıca gösterilmez, çelişki olmaz. Renk overallSignal ile aynı.
export function StatusTag({ stance, evidence }) {
  const sig = overallSignal(stance, evidence);
  return (
    <TagShell st={PILL_STYLE[String(sig.key)] || PILL_STYLE["0"]}>
      {stanceLabel(stance)}
      {evidence && <span className="font-normal">· {evidenceLabel(evidence)}</span>}
    </TagShell>
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
            <span className="text-micro font-medium text-slate-500">
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
        className="relative h-2 rounded-[2px]"
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
// Haber duygusu (-1..1) → etiket. Eşik ±0.15 (haber listesi, özet dağılımı, grafikler ortak).
export function sentimentLabel(v) {
  if (v == null) return "neutral";
  return v > 0.15 ? "positive" : v < -0.15 ? "negative" : "neutral";
}

// RİSK DEĞİŞİMİ KURALI (tek yer): |değişim| < 5 → yalnızca "sabit"; değilse yalnızca ok + fark.
// Risk ARTIŞI kırmızı (kötü), AZALIŞI yeşil. Ok ile "sabit" asla aynı anda görünmez.
export const RISK_STABLE_BAND = 5;
export function riskChange(delta) {
  const d = delta?.risk_delta;
  if (d == null) return null;
  if (Math.abs(d) < RISK_STABLE_BAND) return { kind: "stable", diff: d };
  return { kind: d > 0 ? "up" : "down", diff: d };
}
export function RiskChange({ delta }) {
  const ch = riskChange(delta);
  if (!ch) return null;
  if (ch.kind === "stable")
    return (
      <span className="inline-flex items-center gap-1 text-micro font-medium text-slate-500" title={tt("sum.riskStableTitle")}>
        <Minus className="h-3.5 w-3.5" aria-hidden="true" />
        {tt("sum.riskStable")}
      </span>
    );
  const up = ch.kind === "up";
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className={`inline-flex items-center gap-0.5 text-micro font-semibold tabular-nums ${up ? "text-rose-600" : "text-emerald-600"}`} title={tt("sum.riskDeltaTitle")}>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {up ? "+" : "−"}
      {Math.abs(ch.diff)}
    </span>
  );
}

// Göreli zaman ("2 saat önce"); üzerine gelince dile uygun tam tarih/saat.
export function RelTime({ iso, className = "" }) {
  if (!iso) return null;
  return (
    <time dateTime={iso} title={fmtDateTime(iso)} className={className}>
      {_timeAgo(iso)}
    </time>
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
      <div className="text-micro leading-tight text-slate-400">
        <div className="font-medium text-slate-300">{tt("sum.riskLabel")}</div>
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
      <div className="relative h-1.5 w-full rounded-[2px] bg-ink-600">
        <div className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-ink-800"
             style={{ left: `calc(${pct}% - 6px)`, background: color }} />
      </div>
    </div>
  );
}

// --- Trend oku ---
export function TrendArrow({ trend }) {
  const icons = { improving: TrendingUp, stable: Minus, deteriorating: TrendingDown };
  const clsMap = { improving: "text-emerald-600", stable: "text-slate-500", deteriorating: "text-rose-600" };
  const key = icons[trend] ? trend : "stable";
  const Icon = icons[key];
  return (
    <span className="inline-flex items-center gap-1 text-micro">
      <Icon className={`h-3.5 w-3.5 ${clsMap[key]}`} aria-hidden="true" />
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

