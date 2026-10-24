// Analist verisi — GERÇEK: tavsiye (al/tut/sat) Finnhub, HEDEF FİYAT FMP. NewsRadar ÜRETMEZ.
// Veri yoksa: kartta (compact) sessizce gizlenir; detayda BOŞLUK yerine NEDEN veri
// olmadığını düz Türkçe açıklayan bir not gösterilir (özel şirket / desteklenmeyen borsa).
// compact=true: kart için kısa gösterim. false: detay için tam gösterim + hedef aralık barı.
import React from "react";
import { BarChart3 } from "lucide-react";
import { fmtDate, fmtMonth, fmtPct, getLang, parseUtc, tt } from "../i18n.jsx";
import { C, cssColor } from "../theme.js";
import { EmptyState } from "./kit.jsx";

// Veri yokken gösterilecek açıklama (boşluk bir eksiklik değil, bir açıklama gibi görünsün).
function noDataNote(type, hasPrice) {
  if (type === "keyword") return tt("an.noKeyword");
  if (!hasPrice) return tt("an.noExchange"); // ABD dışı borsa — kaynağımız kapsamıyor
  return tt("an.noAnalyst");                 // ticker+fiyat var ama analist yok
}

const SEGMENTS = [
  { key: "strong_buy", tkey: "an.segStrongBuy", color: C.posStrong },
  { key: "buy", tkey: "an.segBuy", color: C.pos },
  { key: "hold", tkey: "an.segHold", color: C.neutral },
  { key: "sell", tkey: "an.segSell", color: C.neg },
  { key: "strong_sell", tkey: "an.segStrongSell", color: C.negStrong },
];

function consensusLabel(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: tt("card.buyLean"), short: tt("an.leanBuy"), color: C.pos };
  if (sellish > a.hold && sellish > buyish) return { text: tt("card.sellLean"), short: tt("an.leanSell"), color: C.neg };
  return { text: tt("card.holdLean"), short: tt("an.leanMixed"), color: C.neutral };
}

function Bar({ analyst }) {
  const total = analyst.total || 1;
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-[2px] bg-ink-700">
      {SEGMENTS.map((s) => {
        const n = analyst[s.key] || 0;
        if (!n) return null;
        return (
          <div key={s.key} style={{ width: `${(n / total) * 100}%`, background: s.color }} title={`${tt(s.tkey)}: ${n}`} />
        );
      })}
    </div>
  );
}

const usd = (v) => `$${Math.round(v)}`;

// Manşet: "Analistlerin ortalama hedefi $329, şu anki fiyatın %31 üstünde." Rakamlar mono.
function Headline({ mean, price }) {
  const diff = ((mean - price) / price) * 100;
  const key = Math.abs(diff) < 0.5 ? "an.headlineAt" : diff > 0 ? "an.headlineAbove" : "an.headlineBelow";
  const [pre, mid, post] = tt(key).split(/\{mean\}|\{pct\}/);
  return (
    <h3 className="max-w-3xl font-display text-2xl font-medium leading-snug text-slate-100 sm:text-[1.75rem]">
      {pre}
      <span className="font-mono text-[0.9em] tabular-nums">{usd(mean)}</span>
      {mid}
      {post != null && <span className="font-mono text-[0.9em] tabular-nums">{fmtPct(Math.abs(diff), { signed: false })}</span>}
      {post}
    </h3>
  );
}

// Etiketli hedef aralığı: en düşük → en yüksek; "Şimdi" ince nötr çizgi + etiket (üstte),
// "Ortalama" vurgu renginde nokta + etiket (altta) → etiketler hiç çakışmaz. Şimdi ile
// ortalama arası hafif vurgulu. Kenara yakın etiketler içeri hizalanır (taşmaz).
function LabeledRange({ low, high, mean, price, dim = false }) {
  if (low == null || high == null || high <= low) return null;
  const lo = Math.min(low, price ?? low);
  const hi = Math.max(high, price ?? high);
  const span = hi - lo || 1;
  const p = (v) => ((v - lo) / span) * 100;
  const align = (x) => (x < 12 ? "translate-x-0" : x > 88 ? "-translate-x-full" : "-translate-x-1/2");
  const a = price != null ? Math.min(p(price), p(mean)) : p(mean);
  const b = price != null ? Math.max(p(price), p(mean)) : p(mean);
  return (
    <div className="mt-4 select-none">
      <div className="relative h-14">
        {price != null && (
          <span className={`absolute top-0 whitespace-nowrap text-micro text-slate-300 ${align(p(price))}`} style={{ left: `${p(price)}%` }}>
            {tt("an.now")} <span className="font-mono tabular-nums text-slate-100">{usd(price)}</span>
          </span>
        )}
        <div className={`absolute inset-x-0 top-7 h-2 rounded-[2px] bg-ink-700 ${dim ? "opacity-50" : ""}`}>
          <div className="absolute inset-y-0 rounded-[2px]" style={{ left: `${p(low)}%`, width: `${p(high) - p(low)}%`, background: cssColor("slate-500", 0.35) }} />
          <div className="absolute inset-y-0" style={{ left: `${a}%`, width: `${b - a}%`, background: cssColor("accent", 0.35) }} />
          {price != null && <div className="absolute -top-2 h-6 w-px -translate-x-1/2 bg-slate-100" style={{ left: `${p(price)}%` }} />}
          <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-900" style={{ left: `${p(mean)}%`, background: C.accent }} />
        </div>
      </div>
      <div className="relative h-5">
        <span className={`absolute top-0 whitespace-nowrap text-micro font-medium text-accent ${align(p(mean))}`} style={{ left: `${p(mean)}%` }}>
          {tt("an.average")} <span className="font-mono tabular-nums">{usd(mean)}</span>
        </span>
      </div>
      <div className="mt-2 flex justify-between text-micro text-slate-500">
        <span>{tt("an.lowest")} <span className="font-mono tabular-nums text-slate-300">{usd(low)}</span></span>
        <span>{tt("an.highest")} <span className="font-mono tabular-nums text-slate-300">{usd(high)}</span></span>
      </div>
    </div>
  );
}

// Tavsiye dağılımı: tek yığılmış bar, sığan segmentte yüzde; sığmıyorsa yalnızca ipucu.
function StackedBar({ analyst, dim = false }) {
  const total = analyst.total || 1;
  return (
    <div className={`mt-3 flex h-7 w-full overflow-hidden rounded-[4px] bg-ink-700 ${dim ? "opacity-50" : ""}`}>
      {SEGMENTS.map((sg) => {
        const n = analyst[sg.key] || 0;
        if (!n) return null;
        const pct = (n / total) * 100;
        return (
          <div
            key={sg.key}
            className="flex items-center justify-center font-mono text-micro font-semibold tabular-nums"
            style={{ width: `${pct}%`, background: sg.color, color: C.onStrong }}
            title={`${tt(sg.tkey)}: ${n} (${Math.round(pct)}%)`}
          >
            {pct >= 9 && !dim ? `${Math.round(pct)}%` : ""}
          </div>
        );
      })}
    </div>
  );
}

// Dönemlere göre dağılım: küçük yığılmış sütunlar (Finnhub aylık dönemleri).
function PeriodColumns({ history }) {
  const loc = getLang() === "tr" ? "tr-TR" : "en-US";
  return (
    <div className="mt-3 flex items-end gap-3">
      {history.map((h) => {
        const total = SEGMENTS.reduce((t, sg) => t + (h[sg.key] || 0), 0) || 1;
        const label = parseUtc(h.period).toLocaleDateString(loc, { month: "short", timeZone: "UTC" });
        return (
          <div key={h.period} className="flex w-10 flex-col items-center gap-1.5" title={`${label}: ${total}`}>
            <div className="flex h-20 w-6 flex-col-reverse overflow-hidden rounded-[2px] bg-ink-700">
              {SEGMENTS.map((sg) => (h[sg.key] ? <div key={sg.key} style={{ height: `${(h[sg.key] / total) * 100}%`, background: sg.color }} /> : null))}
            </div>
            <span className="text-micro text-slate-500">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

// Hedef fiyat tek satırı (yalnızca KART): $319 → hedef $412 · +%29 (dile göre yüzde).
function TargetLine({ price, mean, upside, compact }) {
  if (mean == null) return null;
  const up = upside != null ? upside : price ? ((mean - price) / price) * 100 : null;
  const pctColor = up == null ? "" : up >= 0 ? "text-emerald-400" : "text-rose-400";
  return (
    <div className={`flex items-baseline gap-1.5 ${compact ? "text-xs" : "text-sm"}`}>
      {price != null && <span className="tabular-nums text-slate-400">${price.toFixed(compact ? 0 : 2)}</span>}
      <span className="inline-flex items-center gap-0.5 text-slate-500">
        → {tt("detail.target")}
      </span>
      <span className="font-semibold tabular-nums text-slate-100">${mean.toFixed(compact ? 0 : 2)}</span>
      {up != null && (
        <span className={`font-semibold tabular-nums ${pctColor}`}>
          · {fmtPct(up)}
        </span>
      )}
    </div>
  );
}

// stale: veri 30 günden eski → barlar soluk + tarih notu (metin AA kalır).
export default function AnalystConsensus({ analyst, price, type, compact = false, stale = false, history = [] }) {
  const hasRec = analyst && analyst.total > 0;
  const hasTarget = analyst && analyst.target_mean != null;

  // Hiç veri yok: kartta gizle; detayda NEDEN yok açıklaması.
  if (!hasRec && !hasTarget) {
    if (compact) return null;
    return <EmptyState icon={BarChart3} title={tt("an.empty")} body={noDataNote(type, price != null)} />;
  }

  const lean = hasRec ? consensusLabel(analyst) : null;
  const curPrice = analyst.current_price != null ? analyst.current_price : price;

  // ---- KART (compact): tavsiye özeti + hedef satırı + kaynak ----
  if (compact) {
    return (
      <div className="flex flex-col gap-1.5">
        {hasRec && (
          <div className="flex items-center gap-2">
            <span className="text-micro font-semibold" style={{ color: lean.color }}>{lean.text}</span>
            <div className="min-w-[60px] flex-1"><Bar analyst={analyst} /></div>
            <span className="text-micro tabular-nums text-slate-500">{tt("card.analysts", { n: analyst.total })}</span>
          </div>
        )}
        {hasTarget && (
          <>
            <TargetLine price={curPrice} mean={analyst.target_mean} upside={analyst.upside_percent} compact />
            <span className="text-micro text-slate-500">
              {hasRec ? `${tt("card.analysts", { n: analyst.total })} · ` : ""}{tt("an.targetConsensus")}
            </span>
          </>
        )}
      </div>
    );
  }

  // ---- DETAY (full): manşet cümlesi · etiketli hedef aralığı · tavsiye dağılımı · dönemler · kaynak.
  return (
    <div className="space-y-8">
      <section>
        {hasTarget && curPrice != null ? (
          <Headline mean={analyst.target_mean} price={curPrice} />
        ) : (
          <h3 className="font-display text-xl font-medium text-slate-100">{tt("an.title")}</h3>
        )}
        {hasRec && (
          <p className="mt-2 text-meta text-slate-400">
            <span className="font-mono tabular-nums">{analyst.total}</span> {tt("an.analystsWord")} · <span style={{ color: lean.color }}>{lean.short}</span>
          </p>
        )}
      </section>

      {/* Veri eskiyse (30 gün+) yalnızca çubuklar soluk; metin tam renkte kalır (AA). */}
      <div>
        {hasTarget && (
          <section className="border-t border-ink-600 pt-5">
            <h4 className="text-meta font-medium text-slate-300">{tt("an.rangeTitle")}</h4>
            <LabeledRange low={analyst.target_low} high={analyst.target_high} mean={analyst.target_mean} price={curPrice} dim={stale} />
          </section>
        )}
        {hasRec && (
          <section className="mt-8 border-t border-ink-600 pt-5">
            <h4 className="text-meta font-medium text-slate-300">{tt("an.distTitle")}</h4>
            <StackedBar analyst={analyst} dim={stale} />
            <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-micro text-slate-400">
              {SEGMENTS.map((sg) => (
                <span key={sg.key} className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-[2px]" style={{ background: sg.color }} aria-hidden="true" />
                  {tt(sg.tkey)} <span className="font-mono font-semibold tabular-nums text-slate-200">{analyst[sg.key] || 0}</span>
                </span>
              ))}
            </p>
          </section>
        )}
        {history.length >= 2 && (
          <section className="mt-8 border-t border-ink-600 pt-5">
            <h4 className="text-meta font-medium text-slate-300">{tt("an.overTime")}</h4>
            <PeriodColumns history={history} />
          </section>
        )}
      </div>

      <footer className="border-t border-ink-600 pt-4 text-micro text-slate-500">
        {stale && <p className="mb-1">{tt("detail.targetStale")}</p>}
        <p>{tt("an.source", { period: fmtMonth(analyst.period), date: fmtDate(analyst.fetched_at) })}</p>
      </footer>
    </div>
  );
}
