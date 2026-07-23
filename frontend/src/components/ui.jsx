// Paylaşılan UI atomları: rozetler, göstergeler, çipler.
import React from "react";

// --- Yön (stance) rozeti ---
const STANCE = {
  bullish: { label: "YÜKSELİŞ", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  neutral: { label: "NÖTR", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
  bearish: { label: "DÜŞÜŞ", cls: "bg-rose-500/15 text-rose-300 border-rose-500/30" },
};
const CONVICTION = { low: "düşük", medium: "orta", high: "yüksek" };

export function stanceLabel(stance) {
  return (STANCE[stance] || STANCE.neutral).label;
}

// Yön/vade/kanıt için renk + etiket yardımcıları (Verdict-First kart).
const STANCE_COLOR = { bullish: "#16a34a", neutral: "#6b7280", bearish: "#dc2626" };
export function stanceColor(stance) {
  return STANCE_COLOR[stance] || STANCE_COLOR.neutral;
}
export function horizonLabel(h) {
  return { short: "Kısa", medium: "Orta", long: "Uzun" }[h] || "—";
}
export function evidenceLabel(e) {
  return { strong: "Güçlü", medium: "Orta", weak: "Zayıf" }[e] || "—";
}
export function evidenceColor(e) {
  return { strong: "#16a34a", medium: "#d97706", weak: "#dc2626" }[e] || "#6b7280";
}

// --- Fiyat gösterimi (yalnızca ticker; price null ise hiç render etme) ---
// Burada fiyat ARTIŞI yeşil (iyi), düşüş kırmızı — risk deltasının TERSİ.
export function PriceDisplay({ price, changePercent, updatedAt, showTime = true }) {
  if (price == null) return null;
  const up = (changePercent ?? 0) >= 0;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="font-semibold text-slate-100">${price.toFixed(2)}</span>
      {changePercent != null && (
        <span className={`text-xs font-medium ${up ? "text-emerald-400" : "text-rose-400"}`}>
          {up ? "+" : ""}
          {changePercent.toFixed(2)}%
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
      {s.label}
      {conviction && <span className="opacity-70 font-normal">· {CONVICTION[conviction] || conviction} kanaat</span>}
    </span>
  );
}

// --- Risk skoru rengi (0 yeşil → 100 kırmızı) ---
export function riskColor(score) {
  if (score == null) return "#64748b";
  if (score < 34) return "#34d399";
  if (score < 67) return "#fbbf24";
  return "#f87171";
}

export function RiskScore({ score }) {
  const color = riskColor(score);
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-9 w-9 shrink-0">
        <svg viewBox="0 0 36 36" className="h-9 w-9 -rotate-90">
          <circle cx="18" cy="18" r="15" fill="none" stroke="#1f2838" strokeWidth="4" />
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
        <div className="text-slate-300 font-medium">Risk</div>
        <div>{score == null ? "analiz yok" : "0–100"}</div>
      </div>
    </div>
  );
}

// --- Duygu göstergesi (-1..1) ---
export function SentimentGauge({ value }) {
  const v = value ?? 0;
  const pct = ((v + 1) / 2) * 100; // -1..1 -> 0..100
  const color = v > 0.15 ? "#34d399" : v < -0.15 ? "#f87171" : "#94a3b8";
  return (
    <div className="w-full">
      <div className="flex justify-between text-[10px] text-slate-500 mb-1">
        <span>−</span>
        <span className="text-slate-400">
          duygu {value == null ? "–" : v.toFixed(2)}
        </span>
        <span>+</span>
      </div>
      <div className="relative h-1.5 w-full rounded-full bg-ink-600">
        <div className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-ink-900"
             style={{ left: `calc(${pct}% - 6px)`, background: color }} />
      </div>
    </div>
  );
}

// --- Trend oku ---
export function TrendArrow({ trend }) {
  const map = {
    improving: { icon: "▲", cls: "text-emerald-400", label: "iyileşiyor" },
    stable: { icon: "▬", cls: "text-slate-400", label: "stabil" },
    deteriorating: { icon: "▼", cls: "text-rose-400", label: "kötüleşiyor" },
  };
  const t = map[trend] || map.stable;
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${t.cls}`}>
      <span>{t.icon}</span>
      <span className="text-slate-400">{t.label}</span>
    </span>
  );
}

// --- Risk bayrağı çipi ---
const FLAG_LABELS = {
  regulatory: "düzenleme",
  competition: "rekabet",
  financial: "finansal",
  legal: "hukuki",
  product: "ürün",
  supply_chain: "tedarik",
  macro: "makro",
  reputation: "itibar",
};
export function flagLabel(f) {
  return FLAG_LABELS[f] || f;
}
export function FlagChip({ flag }) {
  return (
    <span className="rounded border border-ink-500 bg-ink-700 px-1.5 py-0.5 text-[10px] text-slate-300">
      {flagLabel(flag)}
    </span>
  );
}

const EVENT_LABELS = {
  earnings: "bilanço", product: "ürün", regulation: "düzenleme", lawsuit: "dava",
  partnership: "ortaklık", funding: "yatırım", macro: "makro", leadership: "yönetim", other: "diğer",
};
export function eventLabel(e) {
  return EVENT_LABELS[e] || e || "–";
}

export function timeAgo(iso) {
  if (!iso) return "hiç";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "az önce";
  if (diff < 3600) return `${Math.floor(diff / 60)} dk önce`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} sa önce`;
  return `${Math.floor(diff / 86400)} gün önce`;
}
