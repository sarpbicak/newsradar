// Analist verisi — GERÇEK: tavsiye (al/tut/sat) Finnhub, HEDEF FİYAT FMP. NewsRadar ÜRETMEZ.
// Veri yoksa: kartta (compact) sessizce gizlenir; detayda BOŞLUK yerine NEDEN veri
// olmadığını düz Türkçe açıklayan bir not gösterilir (özel şirket / desteklenmeyen borsa).
// compact=true: kart için kısa gösterim. false: detay için tam gösterim + hedef aralık barı.
import React from "react";
import { fmtDate, fmtMonth, fmtPct, tt } from "../i18n.jsx";
import { C, cssColor } from "../theme.js";
import { Card } from "./kit.jsx";

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
  if (buyish > a.hold && buyish >= sellish) return { text: tt("card.buyLean"), color: C.pos };
  if (sellish > a.hold && sellish > buyish) return { text: tt("card.sellLean"), color: C.neg };
  return { text: tt("card.holdLean"), color: C.neutral };
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

// Hedef fiyat aralığı: düşük — ortalama — yüksek + güncel fiyat işareti (görsel bar).
function TargetRangeBar({ low, high, mean, price }) {
  if (low == null || high == null || high <= low) return null;
  const lo = Math.min(low, price ?? low);
  const hi = Math.max(high, price ?? high);
  const span = hi - lo || 1;
  const pos = (v) => `${((v - lo) / span) * 100}%`;
  return (
    <div className="mb-3">
      <div className="relative h-1.5 rounded-[2px] bg-ink-700">
        {/* düşük–yüksek analist aralığı */}
        <div
          className="absolute top-0 h-1.5 rounded-[2px]"
          style={{ left: pos(low), width: `${((high - low) / span) * 100}%`, background: cssColor("slate-500", 0.45) }}
        />
        {/* güncel fiyat işareti (dikey çizgi) */}
        {price != null && (
          <div
            className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-slate-100"
            style={{ left: pos(price) }}
            title={`${tt("an.curPrice")} $${price.toFixed(2)}`}
          />
        )}
        {/* ortalama hedef işareti (nokta) */}
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-800"
          style={{ left: pos(mean), background: C.line }}
          title={`${tt("an.avgTarget")} $${mean.toFixed(2)}`}
        />
      </div>
      <div className="mt-2 flex justify-between font-mono text-micro tabular-nums text-slate-500">
        <span>{tt("an.low")} ${low.toFixed(0)}</span>
        <span className="font-semibold text-slate-200">{tt("an.avg")} ${mean.toFixed(0)}</span>
        <span>{tt("an.high")} ${high.toFixed(0)}</span>
      </div>
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
export default function AnalystConsensus({ analyst, price, type, compact = false, stale = false }) {
  const hasRec = analyst && analyst.total > 0;
  const hasTarget = analyst && analyst.target_mean != null;

  // Hiç veri yok: kartta gizle; detayda NEDEN yok açıklaması.
  if (!hasRec && !hasTarget) {
    if (compact) return null;
    return (
      <Card className="p-5">
        <h3 className="mb-1 font-display text-sm font-medium text-slate-200">{tt("an.title")}</h3>
        <p className="text-body text-slate-400">{noDataNote(type, price != null)}</p>
      </Card>
    );
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

  // ---- DETAY (full): aralık barı + tavsiye dağılımı + kaynak. Fiyat → hedef satırı YOK —
  // detay başlığında zaten gösteriliyor (bilgi tek yerde). ----
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="font-display text-sm font-medium text-slate-200">{tt("an.title")}</h3>
        {hasRec && (
          <span className="text-meta font-medium" style={{ color: lean.color }}>
            {lean.text} · <span className="tabular-nums">{tt("card.analysts", { n: analyst.total })}</span>
          </span>
        )}
      </div>
      <div className={stale ? "opacity-50" : ""}>
        {/* GERÇEK hedef fiyat aralığı (FMP): düşük / ortalama / yüksek + güncel fiyat */}
        {hasTarget && <TargetRangeBar low={analyst.target_low} high={analyst.target_high} mean={analyst.target_mean} price={curPrice} />}
        {/* Tavsiye dağılımı (Finnhub) */}
        {hasRec && <Bar analyst={analyst} />}
      </div>
      {hasRec && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-micro">
          {SEGMENTS.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5 text-slate-400">
              <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden="true" />
              {tt(s.tkey)} <span className="font-mono font-semibold tabular-nums text-slate-200">{analyst[s.key] || 0}</span>
            </span>
          ))}
        </div>
      )}
      {stale && <p className="mt-3 text-micro text-slate-500">{tt("detail.targetStale")}</p>}
      {/* Net kaynak: bu rakamlar AI'dan değil, gerçek analistlerden gelir. */}
      <p className="mt-4 text-micro text-slate-500">{tt("an.source", { period: fmtMonth(analyst.period), date: fmtDate(analyst.fetched_at) })}</p>
    </Card>
  );
}
