// Grafikler sekmesi.
// (1) "Fiyat ve haberler": üst panel (~%70) günlük kapanış fiyatı (doğrusal çizgi, hafif dolgu,
//     son noktada etiket, olay işaretleri), alt panel (~%30) aynı eksende günlük NET haber
//     duygusu çubukları (olumlu yukarı yeşil, olumsuz aşağı kırmızı; opaklık haber sayısıyla).
//     İki panel syncId ile tek dikey imleç ve tek ipucu paylaşır.
// (2) "Risk geçmişi": ~120px, 0–100, basamak çizgi; arkada 0–33 / 33–66 / 66–100 bantları.
//     Fiyat grafiğiyle AYNI günlük satırları kullanır (aynı x başlangıç/bitiş); değerlendirme
//     olmayan günde çizgi yok (tek kalan nokta küçük işaretle görünür).
// Aralık seçici (7g/30g/90g/Tümü): yalnızca VERİ OLAN günler gösterilir (boş gün satırı yok);
// veri olmayan aralık pasif; eksen verinin başladığı günden başlar ("Veri … beri" notu).
// Fırça (brush) ve çift eksen yok. Eksen/ızgara çok soluk, rakamlar mono. Her grafiğin kısa
// metin özeti var (görünür + ekran okuyucu).
import React, { useMemo, useState } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3 } from "lucide-react";
import { tt, parseUtc, getLang, fmtPct } from "../i18n.jsx";
import { fmtMoney } from "../money.js";
import { C } from "../theme.js";
import { Card, EmptyState, Tabs } from "./kit.jsx";
import { sentimentLabel, stanceLabel } from "./ui.jsx";

const DAY = 86400000;
const RANGES = [
  { key: "7", tkey: "chart.r7", days: 7 },
  { key: "30", tkey: "chart.r30", days: 30 },
  { key: "90", tkey: "chart.r90", days: 90 },
  { key: "all", tkey: "chart.rangeAll", days: Infinity },
];
const RISK_JUMP = 15; // ardışık iki değerlendirme arasında bu kadar puan = "risk sıçraması"
const MONO = { fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11, fill: C.muted };

function dayStart(iso) {
  const d = parseUtc(iso);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}
const locale = () => (getLang() === "tr" ? "tr-TR" : "en-US");
const fmtDay = (ts) => new Date(ts).toLocaleDateString(locale(), { day: "numeric", month: "short" });
// Fiyat kendi para biriminde, dile uygun ondalıkla (grafik eksen/ipucu/etiket aynı biçim).
const fmtPrice = (v, cur) => fmtMoney(v, cur, getLang());

// "18 Eki" + Türkçe ayrılma eki ("18 Eki'den beri"); EN "since Oct 18".
const TR_ABL = { oca: "dan", şub: "tan", mar: "tan", nis: "ten", may: "tan", haz: "dan", tem: "den", ağu: "tan", eyl: "den", eki: "den", kas: "tan", ara: "dan" };
function sinceText(ts) {
  const label = fmtDay(ts);
  if (getLang() !== "tr") return tt("chart.since", { date: label });
  const m = label.split(" ").pop().toLocaleLowerCase("tr-TR").replace(".", "");
  return tt("chart.since", { date: `${label}'${TR_ABL[m] || "den"}` });
}

// Günlük satırlar: fiyat (günün son snapshot'ı), günlük değişim, haber duygusu dağılımı ve
// günün en önemli başlığı (en çok kaynakta çıkan, eşitse en güçlü duygu).
function buildDays(priceHistory, articles, riskHistory) {
  const map = new Map();
  const row = (ts) => {
    if (!map.has(ts)) map.set(ts, { ts, price: null, pos: 0, neg: 0, neu: 0, n: 0, top: null, topScore: -1, risk: null, stance: null });
    return map.get(ts);
  };
  (riskHistory || []).forEach((r) => {
    const d = row(dayStart(r.created_at)); // günün SON değerlendirmesi (liste eski → yeni)
    d.risk = r.risk_score;
    d.stance = r.stance;
  });
  [...(priceHistory || [])]
    .sort((a, b) => parseUtc(a.fetched_at) - parseUtc(b.fetched_at))
    .forEach((p) => (row(dayStart(p.fetched_at)).price = p.price));
  (articles || []).forEach((a) => {
    if (!a.analyzed || a.sentiment == null || !a.published_at) return;
    const r = row(dayStart(a.published_at));
    const lbl = sentimentLabel(a.sentiment);
    r[lbl === "positive" ? "pos" : lbl === "negative" ? "neg" : "neu"]++;
    r.n++;
    const score = (a.source_count || 1) * 10 + Math.abs(a.sentiment);
    if (score > r.topScore) {
      r.topScore = score;
      r.top = a.title;
    }
  });
  const rows = [...map.values()].sort((a, b) => a.ts - b.ts);
  let prev = null;
  rows.forEach((r) => {
    r.label = fmtDay(r.ts);
    r.net = r.pos - r.neg;
    r.chg = r.price != null && prev != null ? ((r.price - prev) / prev) * 100 : null;
    if (r.price != null) prev = r.price;
  });
  return rows;
}

// Olaylar: değerlendirmeler arasında yön değişimi ya da ±15 risk sıçraması (sonraki günde).
function buildEvents(riskHistory) {
  const out = new Map();
  (riskHistory || []).forEach((r, i, arr) => {
    if (i === 0) return;
    const p = arr[i - 1];
    const ts = dayStart(r.created_at);
    const list = out.get(ts) || [];
    if (p.stance && r.stance && p.stance !== r.stance)
      list.push(tt("chart.evStance", { from: stanceLabel(p.stance), to: stanceLabel(r.stance) }));
    if (Math.abs(r.risk_score - p.risk_score) >= RISK_JUMP)
      list.push(tt("chart.evRisk", { from: p.risk_score, to: r.risk_score }));
    if (list.length) out.set(ts, list);
  });
  return out;
}

// Yalnızca komşusu boş (tek kalmış) risk noktasına küçük işaret: çizgi kopuk olduğundan
// aksi halde görünmezdi. Ardışık günler düz basamak çizgisi olarak kalır.
function isolatedDot(rows) {
  return ({ cx, cy, index }) => {
    const v = rows[index]?.risk;
    if (v == null || cx == null) return null;
    const lone = rows[index - 1]?.risk == null && rows[index + 1]?.risk == null;
    return lone ? <circle key={index} cx={cx} cy={cy} r={2.5} fill={C.line} stroke="none" /> : null;
  };
}

function inRange(ts, days) {
  if (days === Infinity) return true;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - (days - 1) * DAY;
  return ts >= start;
}

function moodOf(rows) {
  const pos = rows.reduce((s, r) => s + r.pos, 0);
  const neg = rows.reduce((s, r) => s + r.neg, 0);
  const n = rows.reduce((s, r) => s + r.n, 0);
  if (!n) return null;
  if (pos / n >= 0.6) return tt("chart.moodPos");
  if (neg / n >= 0.6) return tt("chart.moodNeg");
  return tt("chart.moodMixed");
}

function priceSummary(rows) {
  const pr = rows.filter((r) => r.price != null);
  const mood = moodOf(rows);
  const parts = [];
  if (pr.length >= 2) {
    const a = pr[0];
    const b = pr[pr.length - 1];
    const pct = ((b.price - a.price) / a.price) * 100;
    const days = Math.max(1, Math.round((b.ts - a.ts) / DAY));
    const dir = Math.abs(pct) < 0.5 ? tt("chart.dirFlat") : pct > 0 ? tt("chart.dirUp") : tt("chart.dirDown");
    parts.push(tt("chart.sumPrice", { days, pct: fmtPct(Math.abs(pct), { digits: 1, signed: false }), dir }));
  }
  if (mood) parts.push(tt("chart.sumMood", { mood }));
  const text = parts.join(", ");
  return text ? text.charAt(0).toLocaleUpperCase(locale()) + text.slice(1) + "." : "";
}

function Tip({ active, payload, events, currency }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const ev = events.get(r.ts) || [];
  return (
    <div className="max-w-72 rounded-control bg-raised px-3 py-2 text-micro text-slate-300 ring-1 ring-ink-500">
      <div className="font-medium text-slate-100">{fmtDay(r.ts)}</div>
      {r.price != null && (
        <div className="mt-1 font-mono tabular-nums">
          {fmtPrice(r.price, currency)}
          {r.chg != null && (
            <span className={r.chg >= 0 ? "text-emerald-600" : "text-rose-600"}> {fmtPct(r.chg, { digits: 1 })}</span>
          )}
        </div>
      )}
      {r.n > 0 && (
        <div className="mt-1">
          {tt("chart.tipNews", { n: r.n })} · <span className="text-emerald-600">+{r.pos}</span> <span className="text-rose-600">−{r.neg}</span> · {tt("chart.tipNeutral", { n: r.neu })}
        </div>
      )}
      {r.top && <div className="mt-1 line-clamp-2 text-slate-400">“{r.top}”</div>}
      {ev.map((e) => (
        <div key={e} className="mt-1 font-medium text-amber-600">{e}</div>
      ))}
    </div>
  );
}

function ChartCard({ title, summary, children, note }) {
  return (
    <Card as="section" className="p-5">
      <h3 className="font-display text-base font-medium text-slate-100">{title}</h3>
      {summary && <p className="mt-1 text-meta text-slate-400">{summary}</p>}
      <div className="mt-4">{children}</div>
      {note && <p className="mt-3 text-micro text-slate-500">{note}</p>}
    </Card>
  );
}

export default function TimeSeriesCharts({ riskHistory = [], priceHistory = [], articles = [], isTicker, isMobile, currency = "USD" }) {
  const allDays = useMemo(() => buildDays(isTicker ? priceHistory : [], articles, riskHistory), [priceHistory, articles, riskHistory, isTicker]);
  const events = useMemo(() => buildEvents(riskHistory), [riskHistory]);

  // Hangi aralıkta veri var: fiyatta ≥2 gün ya da en az 1 duygu günü / risk noktası.
  const has = (days) => {
    const d = allDays.filter((r) => inRange(r.ts, days));
    const prices = d.filter((r) => r.price != null).length;
    return prices >= 2 || d.some((r) => r.n > 0 || r.risk != null);
  };
  const available = RANGES.filter((r) => has(r.days)).map((r) => r.key);
  const [range, setRange] = useState(() => (available.includes("30") ? "30" : available[available.length - 1] || "all"));
  const days = RANGES.find((r) => r.key === range)?.days ?? Infinity;
  const rows = allDays.filter((r) => inRange(r.ts, days));
  const risk = rows.filter((r) => r.risk != null);
  const withPrice = rows.filter((r) => r.price != null);

  if (!allDays.length) {
    return <EmptyState icon={BarChart3} title={tt("chart.noData")} body={tt("chart.need2days")} />;
  }

  const first = Math.min(...rows.map((r) => r.ts));
  const rangeStart = days === Infinity ? null : Date.now() - (days - 1) * DAY;
  const showSince = Number.isFinite(first) && (rangeStart == null || first > rangeStart + DAY);
  const maxN = Math.max(1, ...rows.map((r) => r.n));
  const maxNet = Math.max(1, ...rows.map((r) => Math.abs(r.net)));
  const last = withPrice[withPrice.length - 1];
  const evDots = rows.filter((r) => events.has(r.ts) && r.price != null);
  const hUpper = isMobile ? 190 : 230;
  const hLower = isMobile ? 80 : 96;
  const tickEvery = Math.max(0, Math.ceil(rows.length / (isMobile ? 4 : 8)) - 1);

  const rangeItems = RANGES.map((r) => ({ key: r.key, label: tt(r.tkey), disabled: !available.includes(r.key) }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="text-meta text-slate-500">{tt("chart.range")}</span>
        <Tabs variant="pill" label={tt("chart.range")} value={range} onChange={setRange} items={rangeItems} />
        {showSince && <span className="text-micro text-slate-500">{sinceText(first)}</span>}
      </div>

      {rows.some((r) => r.price != null || r.n > 0) && (
        <ChartCard
          title={isTicker ? tt("chart.mainTitle") : tt("chart.newsTitle")}
          summary={priceSummary(rows)}
          note={isTicker ? tt("chart.priceNote") : null}
        >
          <div role="img" aria-label={`${isTicker ? tt("chart.mainTitle") : tt("chart.newsTitle")}. ${priceSummary(rows)}`}>
            {isTicker && withPrice.length >= 2 && (
              <ResponsiveContainer width="100%" height={hUpper}>
                <ComposedChart data={rows} syncId="nr-price-news" margin={{ top: 10, right: 64, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke={C.grid} />
                  <XAxis dataKey="label" hide />
                  <YAxis domain={["auto", "auto"]} tick={MONO} tickLine={false} axisLine={false} width={52} tickFormatter={(v) => fmtMoney(v, currency, getLang(), { digits: 0 })} />
                  <Tooltip content={<Tip events={events} currency={currency} />} cursor={{ stroke: C.muted, strokeWidth: 1 }} isAnimationActive={false} />
                  <Area
                    type="linear"
                    dataKey="price"
                    stroke={C.accent}
                    strokeWidth={2}
                    fill={C.accent}
                    fillOpacity={0.07}
                    connectNulls
                    dot={false}
                    activeDot={{ r: 3, fill: C.accent, stroke: "none" }}
                    isAnimationActive={false}
                  />
                  {evDots.map((r) => (
                    <ReferenceDot key={r.ts} x={r.label} y={r.price} r={4} fill={C.warn} stroke="none" ifOverflow="extendDomain" />
                  ))}
                  {last && (
                    <ReferenceDot
                      x={last.label}
                      y={last.price}
                      r={3}
                      fill={C.accent}
                      stroke="none"
                      label={{ value: fmtPrice(last.price, currency), position: "right", offset: 8, style: { ...MONO, fill: C.line, fontWeight: 600 } }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            )}
            <ResponsiveContainer width="100%" height={isTicker && withPrice.length >= 2 ? hLower : 160}>
              <ComposedChart data={rows} syncId="nr-price-news" margin={{ top: 4, right: 64, bottom: 0, left: 0 }}>
                <XAxis dataKey="label" tick={MONO} tickLine={false} axisLine={{ stroke: C.grid }} interval={tickEvery} />
                {/* Gizli değil, boş eksen: fiyat ekseniyle aynı genişliği kaplasın ki iki panelin x'leri hizalı olsun. */}
                <YAxis domain={[-maxNet, maxNet]} tick={false} tickLine={false} axisLine={false} width={52} />
                <ReferenceLine y={0} stroke={C.subtle} />
                <Tooltip
                  content={isTicker && withPrice.length >= 2 ? () => null : <Tip events={events} />}
                  cursor={{ stroke: C.muted, strokeWidth: 1 }}
                  isAnimationActive={false}
                />
                <Bar dataKey="net" isAnimationActive={false} maxBarSize={14}>
                  {rows.map((r) => (
                    <Cell key={r.ts} fill={r.net >= 0 ? C.pos : C.neg} fillOpacity={r.n ? 0.35 + 0.65 * (r.n / maxN) : 0} />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
            {/* Sol eksen genişliği kadar boşluk: alt panelin çubukları fiyat ekseniyle hizalı. */}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-[52px] text-micro text-slate-500">
              <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: C.pos }} />{tt("chart.legendPos")}</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: C.neg }} />{tt("chart.legendNeg")}</span>
              {evDots.length > 0 && <span><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: C.warn }} />{tt("chart.legendEvent")}</span>}
            </div>
          </div>
        </ChartCard>
      )}

      {risk.length >= 2 ? (
        <ChartCard
          title={tt("chart.riskTitle")}
          summary={tt("chart.sumRisk", { a: risk[0].risk, b: risk[risk.length - 1].risk, n: risk.length })}
        >
          <div role="img" aria-label={`${tt("chart.riskTitle")}. ${tt("chart.sumRisk", { a: risk[0].risk, b: risk[risk.length - 1].risk, n: risk.length })}`}>
            <ResponsiveContainer width="100%" height={120}>
              <LineChart data={rows} margin={{ top: 6, right: 64, bottom: 0, left: 0 }}>
                <ReferenceArea y1={0} y2={33} fill={C.pos} fillOpacity={0.06} ifOverflow="hidden" />
                <ReferenceArea y1={33} y2={66} fill={C.warn} fillOpacity={0.06} ifOverflow="hidden" />
                <ReferenceArea y1={66} y2={100} fill={C.neg} fillOpacity={0.06} ifOverflow="hidden" />
                <XAxis dataKey="label" tick={MONO} tickLine={false} axisLine={{ stroke: C.grid }} interval={tickEvery} />
                <YAxis domain={[0, 100]} ticks={[0, 33, 66, 100]} tick={MONO} tickLine={false} axisLine={false} width={52} />
                <Tooltip
                  isAnimationActive={false}
                  cursor={{ stroke: C.muted, strokeWidth: 1 }}
                  content={({ active, payload }) =>
                    active && payload?.length && payload[0].payload.risk != null ? (
                      <div className="rounded-control bg-raised px-3 py-2 text-micro text-slate-300 ring-1 ring-ink-500">
                        <span className="font-medium text-slate-100">{fmtDay(payload[0].payload.ts)}</span> · {tt("chart.tipRisk", { v: payload[0].payload.risk })} · {stanceLabel(payload[0].payload.stance)}
                      </div>
                    ) : null
                  }
                />
                <Line
                  type="stepAfter"
                  dataKey="risk"
                  stroke={C.line}
                  strokeWidth={1.75}
                  connectNulls={false}
                  dot={isolatedDot(rows)}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      ) : (
        <Card className="p-5 text-meta text-slate-500">{tt("chart.riskNeed2")}</Card>
      )}
    </div>
  );
}
