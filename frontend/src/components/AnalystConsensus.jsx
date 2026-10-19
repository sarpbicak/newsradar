// Analist verisi — GERÇEK: tavsiye (al/tut/sat) Finnhub, HEDEF FİYAT FMP. NewsRadar ÜRETMEZ.
// Veri yoksa: kartta (compact) sessizce gizlenir; detayda BOŞLUK yerine NEDEN veri
// olmadığını düz Türkçe açıklayan bir not gösterilir (özel şirket / desteklenmeyen borsa).
// compact=true: kart için kısa gösterim. false: detay için tam gösterim + hedef aralık barı.
import React from "react";
import { fmtPct, tt } from "../i18n.jsx";

// Veri yokken gösterilecek açıklama (boşluk bir eksiklik değil, bir açıklama gibi görünsün).
function noDataNote(type, hasPrice) {
  if (type === "keyword") return tt("an.noKeyword");
  if (!hasPrice) return tt("an.noExchange"); // ABD dışı borsa — kaynağımız kapsamıyor
  return tt("an.noAnalyst");                 // ticker+fiyat var ama analist yok
}

const SEGMENTS = [
  { key: "strong_buy", tkey: "an.segStrongBuy", color: "#0B7A42" },
  { key: "buy", tkey: "an.segBuy", color: "#0F8A4C" },
  { key: "hold", tkey: "an.segHold", color: "#7A7770" },
  { key: "sell", tkey: "an.segSell", color: "#C62828" },
  { key: "strong_sell", tkey: "an.segStrongSell", color: "#A81E1E" },
];

function consensusLabel(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: tt("card.buyLean"), color: "#0F8A4C" };
  if (sellish > a.hold && sellish > buyish) return { text: tt("card.sellLean"), color: "#C62828" };
  return { text: tt("card.holdLean"), color: "#7A7770" };
}

function Bar({ analyst }) {
  const total = analyst.total || 1;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-black/10">
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
      <div className="relative h-2 rounded-full bg-ink-700">
        {/* düşük–yüksek analist aralığı */}
        <div
          className="absolute top-0 h-2 rounded-full"
          style={{ left: pos(low), width: `${((high - low) / span) * 100}%`, background: "rgba(30,58,95,0.30)" }}
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
          style={{ left: pos(mean), background: "#1E3A5F" }}
          title={`${tt("an.avgTarget")} $${mean.toFixed(2)}`}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-500">
        <span>{tt("an.low")} ${low.toFixed(0)}</span>
        <span className="font-semibold text-slate-300">{tt("an.avg")} ${mean.toFixed(0)}</span>
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

export default function AnalystConsensus({ analyst, price, type, compact = false }) {
  const hasRec = analyst && analyst.total > 0;
  const hasTarget = analyst && analyst.target_mean != null;

  // Hiç veri yok: kartta gizle; detayda NEDEN yok açıklaması.
  if (!hasRec && !hasTarget) {
    if (compact) return null;
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
        <div className="mb-1 flex items-center gap-1 text-[11px] uppercase text-slate-500">
          {tt("an.title")}
        </div>
        <p className="text-sm leading-relaxed text-slate-400">{noDataNote(type, price != null)}</p>
      </div>
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
            <span className="text-[11px] font-semibold" style={{ color: lean.color }}>{lean.text}</span>
            <div className="min-w-[60px] flex-1"><Bar analyst={analyst} /></div>
            <span className="text-[10px] tabular-nums text-slate-500">{tt("card.analysts", { n: analyst.total })}</span>
          </div>
        )}
        {hasTarget && (
          <>
            <TargetLine price={curPrice} mean={analyst.target_mean} upside={analyst.upside_percent} compact />
            <span className="text-[10px] text-slate-500">
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
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="inline-flex items-center gap-1 text-[11px] uppercase text-slate-500">
          {tt("an.title")}
        </span>
        {hasRec && (
          <span className="text-xs font-semibold" style={{ color: lean.color }}>{lean.text}</span>
        )}
      </div>

      {/* GERÇEK hedef fiyat aralığı (FMP): düşük / ortalama / yüksek */}
      {hasTarget && (
        <TargetRangeBar
          low={analyst.target_low}
          high={analyst.target_high}
          mean={analyst.target_mean}
          price={curPrice}
        />
      )}

      {/* Tavsiye dağılımı (Finnhub) */}
      {hasRec && (
        <>
          <Bar analyst={analyst} />
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] tabular-nums">
            {SEGMENTS.map((s) => (
              <span key={s.key} className="flex items-center gap-1 text-slate-400">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                {tt(s.tkey)} <span className="font-semibold text-slate-200">{analyst[s.key] || 0}</span>
              </span>
            ))}
          </div>
        </>
      )}

      {/* Net kaynak etiketi — bu rakamlar Claude'dan değil, gerçek analistlerden gelir. */}
      <div className="mt-3 text-[10px] leading-relaxed text-slate-500">
        {tt("an.source", { period: analyst.period ? ` · ${analyst.period}` : "" })}
      </div>
    </div>
  );
}
