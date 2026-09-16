// Etkileşimli zaman serisi grafikleri: (1) Risk + haber havası birleşik, (2) Fiyat.
// - GÜNLÜK ORTALAMA (testere dişi gürültüsünü öldürür) + gerçek takvim ekseni (her satır
//   1 gün; veri olmayan gün = boşluk, çizgi zorla birleşmez).
// - Zaman aralığı seçici (7g/30g/90g/Tümü) her iki grafiğe birden uygulanır.
// - Brush şeridi (sürükle→yakınlaştır/kaydır) + fare tekerleği zoom + çift tık sıfırla.
// - Nokta işaretçisi yok, efsane yok (çizgi ucu/köşe etiketi), ızgara yalnızca yatay.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { tt } from "../i18n.jsx";

const DAY = 86400000;
const NAVY = "#1E3A5F";   // vurgu — grafik ana çizgisi
const GRID = "#EDEAE3";   // çok soluk yatay ızgara
const ZERO = "#D8D3C7";   // sentiment sıfır çizgisi
const MUTED = "#8A867E";  // eksen etiketi / haber havası
const RANGES = [["chart.r7", 7], ["chart.r30", 30], ["chart.r90", 90], ["chart.rangeAll", Infinity]];

function dayKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtLabel(ts) {
  return new Date(ts).toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
}

// Nokta işaretçisi YOK — AMA yalnız (komşusu boş) bir gün nokta olmadan görünmez olur
// (connectNulls=false + dot=false). Bu yüzden SADECE izole noktalara küçük nokta koy;
// ardışık günler düz çizgi olarak kalır (spec: "sadece çizgi").
function isolatedDot(data, key, color) {
  return (props) => {
    const { cx, cy, index } = props;
    const v = data[index] && data[index][key];
    if (v == null) return null;
    const prev = index > 0 ? data[index - 1][key] : null;
    const next = index < data.length - 1 ? data[index + 1][key] : null;
    if (prev != null || next != null) return null; // komşusu var → çizgi çizilir, nokta gerekmez
    return <circle key={index} cx={cx} cy={cy} r={2.5} fill={color} stroke="none" />;
  };
}

// Ham snapshot'ları GÜNLÜK ortalamaya indir + eksik günleri null satır olarak doldur
// (gerçek takvim aralığı; boşluklar çizgide kopukluk yaratır).
function buildDaily(riskHistory, articles, priceHistory) {
  const sum = { risk: {}, riskN: {}, sent: {}, sentN: {}, price: {}, priceN: {} };
  (riskHistory || []).forEach((r) => {
    const k = dayKey(r.created_at);
    sum.risk[k] = (sum.risk[k] || 0) + r.risk_score; sum.riskN[k] = (sum.riskN[k] || 0) + 1;
  });
  (articles || []).forEach((a) => {
    if (a.analyzed && a.sentiment != null && a.published_at) {
      const k = dayKey(a.published_at);
      sum.sent[k] = (sum.sent[k] || 0) + a.sentiment; sum.sentN[k] = (sum.sentN[k] || 0) + 1;
    }
  });
  (priceHistory || []).forEach((p) => {
    const k = dayKey(p.fetched_at);
    sum.price[k] = (sum.price[k] || 0) + p.price; sum.priceN[k] = (sum.priceN[k] || 0) + 1;
  });
  const keys = new Set([...Object.keys(sum.risk), ...Object.keys(sum.sent), ...Object.keys(sum.price)]);
  if (keys.size === 0) return [];
  const tsList = [...keys].map((k) => new Date(k + "T00:00:00").getTime()).sort((a, b) => a - b);
  const minTs = tsList[0], maxTs = tsList[tsList.length - 1];
  const rows = [];
  for (let t = minTs; t <= maxTs + DAY / 2; t += DAY) {
    const k = dayKey(t);
    rows.push({
      ts: t, label: fmtLabel(t),
      risk: sum.riskN[k] ? sum.risk[k] / sum.riskN[k] : null,
      sentiment: sum.sentN[k] ? sum.sent[k] / sum.sentN[k] : null,
      price: sum.priceN[k] ? sum.price[k] / sum.priceN[k] : null,
    });
  }
  return rows;
}

// Tooltip: "14 Eyl · risk 52 · havası +0.3" / "14 Eyl · $338.19"
function ChartTip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const get = (k) => {
    const p = payload.find((x) => x.dataKey === k);
    return p && p.value != null ? p.value : null;
  };
  const risk = get("risk"), sent = get("sentiment"), price = get("price");
  const parts = [];
  if (risk != null) parts.push(tt("chart.tipRisk", { v: Math.round(risk) }));
  if (sent != null) parts.push(tt("chart.tipMood", { v: `${sent >= 0 ? "+" : ""}${sent.toFixed(1)}` }));
  if (price != null) parts.push(`$${price.toFixed(2)}`);
  return (
    <div className="rounded-lg border border-ink-500 bg-ink-800 px-2.5 py-1.5 text-[11px] text-slate-300 shadow-card-hover">
      <span className="font-medium text-slate-100">{label}</span>
      {parts.length ? ` · ${parts.join(" · ")}` : ""}
    </div>
  );
}

const Panel = ({ children }) => (
  <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">{children}</div>
);
const Empty = ({ text }) => (
  <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 text-sm text-slate-500">{text}</div>
);

// Brush + fare tekerleği zoom + çift tık sıfırla için ortak sarmalayıcı.
function useZoom(len) {
  const [range, setRange] = useState({ s: 0, e: Math.max(0, len - 1) });
  useEffect(() => { setRange({ s: 0, e: Math.max(0, len - 1) }); }, [len]);
  const wrapRef = useRef(null);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || len < 2) return;
    const onWheel = (ev) => {
      ev.preventDefault();
      setRange((r) => {
        const span = r.e - r.s;
        const step = Math.max(1, Math.round(span * 0.15));
        if (ev.deltaY < 0) {  // yakınlaştır (daralt)
          const ns = Math.min(r.s + step, r.e - 1);
          const ne = Math.max(r.e - step, ns + 1);
          return { s: ns, e: ne };
        }
        // uzaklaştır (genişlet)
        return { s: Math.max(0, r.s - step), e: Math.min(len - 1, r.e + step) };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [len]);
  const reset = () => setRange({ s: 0, e: Math.max(0, len - 1) });
  return { range, setRange, wrapRef, reset };
}

// Grafik 1 — Risk (lacivert çizgi, sol eksen) + haber havası (soluk alan, sağ eksen).
function RiskSentimentChart({ data, isMobile }) {
  const { range, setRange, wrapRef, reset } = useZoom(data.length);
  const hasRisk = data.some((d) => d.risk != null);
  const hasSent = data.some((d) => d.sentiment != null);
  return (
    <Panel>
      <div className="mb-1 text-[13px] font-medium text-slate-300">{tt("chart.riskSent")}</div>
      <div ref={wrapRef} onDoubleClick={reset} className="relative select-none">
        {/* Çizgi ucu yerine köşe etiketleri (efsane yok) */}
        <span className="pointer-events-none absolute left-8 top-1 z-10 text-[10px] font-semibold" style={{ color: NAVY }}>{tt("chart.risk")}</span>
        {hasSent && (
          <span className="pointer-events-none absolute right-7 top-1 z-10 text-[10px] font-semibold" style={{ color: MUTED }}>{tt("chart.newsMood")}</span>
        )}
        <ResponsiveContainer width="100%" height={isMobile ? 190 : 210}>
          <ComposedChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -18 }} syncId="ts">
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tick={{ fill: MUTED, fontSize: 10 }} axisLine={false} tickLine={false}
                   minTickGap={isMobile ? 52 : 34} interval="preserveStartEnd" />
            <YAxis yAxisId="risk" domain={[0, 100]} ticks={[0, 50, 100]} tick={{ fill: MUTED, fontSize: 10 }}
                   axisLine={false} tickLine={false} width={30} />
            <YAxis yAxisId="sent" orientation="right" domain={[-1, 1]} ticks={[-1, 0, 1]}
                   tick={{ fill: MUTED, fontSize: 10 }} axisLine={false} tickLine={false} width={24} />
            <ReferenceLine yAxisId="sent" y={0} stroke={ZERO} />
            <Tooltip content={<ChartTip />} />
            <Area yAxisId="sent" type="monotone" dataKey="sentiment" stroke="none" fill={MUTED}
                  fillOpacity={0.14} connectNulls={false} isAnimationActive={false}
                  dot={isolatedDot(data, "sentiment", MUTED)} />
            <Line yAxisId="risk" type="monotone" dataKey="risk" stroke={NAVY} strokeWidth={2}
                  dot={isolatedDot(data, "risk", NAVY)} connectNulls={false} isAnimationActive={false} />
            <Brush dataKey="label" height={16} stroke="#CBC6BB" fill="#FAF8F4" travellerWidth={8}
                   startIndex={range.s} endIndex={range.e}
                   onChange={(r) => setRange({ s: r.startIndex, e: r.endIndex })}
                   tickFormatter={() => ""} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {!hasRisk && (
        <div className="mt-1 text-[11px] text-slate-500">{tt("chart.riskNeed2")}</div>
      )}
    </Panel>
  );
}

// Grafik 2 — Fiyat (tek lacivert çizgi, son değer ucunda etiketli).
function PriceChart({ data, updatedNote }) {
  const { range, setRange, wrapRef, reset } = useZoom(data.length);
  const lastPt = [...data].reverse().find((d) => d.price != null);
  return (
    <Panel>
      <div className="mb-1 text-[13px] font-medium text-slate-300">{tt("chart.price")}</div>
      <div ref={wrapRef} onDoubleClick={reset} className="select-none">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 8, right: 42, bottom: 0, left: -6 }} syncId="ts">
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tick={{ fill: MUTED, fontSize: 10 }} axisLine={false} tickLine={false}
                   minTickGap={40} interval="preserveStartEnd" />
            <YAxis domain={["auto", "auto"]} tick={{ fill: MUTED, fontSize: 10 }} axisLine={false}
                   tickLine={false} width={46} tickFormatter={(v) => `$${v}`} />
            <Tooltip content={<ChartTip />} />
            <Line type="monotone" dataKey="price" stroke={NAVY} strokeWidth={2}
                  dot={isolatedDot(data, "price", NAVY)} connectNulls={false} isAnimationActive={false} />
            {lastPt && (
              <ReferenceDot x={lastPt.label} y={lastPt.price} r={3} fill={NAVY} stroke="none"
                            label={{ value: `$${lastPt.price.toFixed(2)}`, position: "right", fill: NAVY, fontSize: 11, fontWeight: 600 }} />
            )}
            <Brush dataKey="label" height={16} stroke="#CBC6BB" fill="#FAF8F4" travellerWidth={8}
                   startIndex={range.s} endIndex={range.e}
                   onChange={(r) => setRange({ s: r.startIndex, e: r.endIndex })}
                   tickFormatter={() => ""} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 text-[10px] text-slate-500">
        {tt("chart.priceNote")}
        {updatedNote}
      </div>
    </Panel>
  );
}

export default function TimeSeriesCharts({ riskHistory, priceHistory, articles, isTicker, isMobile = false }) {
  const [rangeDays, setRangeDays] = useState(30);
  const [showCombo, setShowCombo] = useState(false); // mobil: risk+havası gizli başlar

  const daily = useMemo(
    () => buildDaily(riskHistory, articles, priceHistory),
    [riskHistory, priceHistory, articles]
  );
  const dataDays = daily.filter((d) => d.risk != null || d.sentiment != null || d.price != null).length;

  const windowed = useMemo(() => {
    if (!daily.length) return [];
    if (rangeDays === Infinity) return daily;
    const last = daily[daily.length - 1].ts;
    const cutoff = last - (rangeDays - 1) * DAY;
    return daily.filter((d) => d.ts >= cutoff);
  }, [daily, rangeDays]);
  const windowedHasData = windowed.some((d) => d.risk != null || d.sentiment != null || d.price != null);

  // Seçici (her iki grafiğe birden uygulanır)
  const selector = (
    <div className="flex items-center gap-1">
      <span className="mr-1 text-[11px] text-slate-500">{tt("chart.range")}</span>
      {RANGES.map(([label, days]) => {
        const on = rangeDays === days;
        return (
          <button
            key={label}
            onClick={() => setRangeDays(days)}
            className={`min-h-[32px] rounded-md px-2.5 text-[12px] font-medium transition ${
              on ? "bg-accent text-white" : "text-slate-500 hover:bg-ink-700 hover:text-slate-300"
            }`}
          >
            {tt(label)}
          </button>
        );
      })}
    </div>
  );

  if (dataDays < 2) {
    return (
      <div className="space-y-3">
        {selector}
        <Empty text={tt("chart.need2days")} />
      </div>
    );
  }

  const body = !windowedHasData ? (
    <Empty text={tt("chart.noDataRange")} />
  ) : isMobile ? (
    // MOBİL: önce fiyat; risk+havası "göster" ile açılır. Ticker değilse combo birincil.
    <div className="space-y-4">
      {isTicker && <PriceChart data={windowed} />}
      {(showCombo || !isTicker) && <RiskSentimentChart data={windowed} isMobile />}
      {isTicker && (
        <button
          onClick={() => setShowCombo((v) => !v)}
          className="min-h-[44px] w-full rounded-lg border border-ink-500 bg-ink-800 text-sm font-medium text-slate-300 transition hover:bg-ink-700"
        >
          {showCombo ? tt("chart.hideRiskSent") : tt("chart.showRiskSent")}
        </button>
      )}
    </div>
  ) : (
    // MASAÜSTÜ: iki grafik alt alta, aynı boyut/stil.
    <div className="space-y-4">
      <RiskSentimentChart data={windowed} />
      {isTicker && <PriceChart data={windowed} />}
    </div>
  );

  return (
    <div className="space-y-3">
      {selector}
      {body}
    </div>
  );
}
