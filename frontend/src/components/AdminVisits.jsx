// Admin "Ziyaretler": çerezsiz sayaç (backend app/visits.py) — son 30 gün günlük benzersiz
// ziyaretçi (çizgi) + görüntüleme (sütun), en çok gelen 5 kaynak, landing → uygulama geçişi.
// Grafik pano grafikleriyle aynı yapı (Recharts + tema renkleri). Kendi verisini yükler; hata
// paneli bozmaz.
import React, { useEffect, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { fmtInt, fmtPct, getLang, parseUtc, tt } from "../i18n.jsx";
import { C } from "../theme.js";
import { Card, Skeleton } from "./kit.jsx";

const MONO = { fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11, fill: C.muted };
const fmtDay = (iso) => parseUtc(`${iso}T12:00:00Z`).toLocaleDateString(getLang() === "tr" ? "tr-TR" : "en-US", { day: "numeric", month: "short" });

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-control bg-raised px-3 py-2 text-micro text-slate-300 ring-1 ring-ink-500">
      <div className="font-medium text-slate-100">{fmtDay(r.day)}</div>
      <div className="mt-1 tabular-nums">{tt("vis.visitorsN", { n: r.visitors })} · {tt("vis.viewsN", { n: r.views })}</div>
    </div>
  );
}

function Stat({ label, value, hint }) {
  return (
    <div className="min-w-0">
      <div className="text-micro font-medium text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold tabular-nums text-slate-100">{value}</div>
      {hint && <div className="mt-0.5 text-micro text-slate-500">{hint}</div>}
    </div>
  );
}

export default function AdminVisits() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api.adminVisits().then(setData).catch(() => setFailed(true));
  }, []);
  if (failed) return null;
  if (!data) return <Skeleton className="h-72 w-full" />;
  const rate = data.conversion_rate;
  const summary = tt("vis.aria", { v: data.total_visitors, p: data.total_views });
  return (
    <Card className="p-5">
      <h3 className="font-display text-sm font-medium text-slate-200">{tt("vis.title")}</h3>
      <p className="mt-1 text-micro text-slate-500">{tt("vis.note")}</p>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Stat label={tt("vis.visitors30")} value={fmtInt(data.total_visitors)} hint={tt("vis.visitorsHint")} />
        <Stat label={tt("vis.views30")} value={fmtInt(data.total_views)} />
        <Stat
          label={tt("vis.conversion")}
          value={rate == null ? "—" : fmtPct(rate * 100, { signed: false })}
          hint={tt("vis.conversionHint", { a: data.landing_to_app, l: data.landing_visitors })}
        />
      </div>
      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <div role="img" aria-label={summary} className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.days} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="day" tickFormatter={fmtDay} tick={MONO} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis allowDecimals={false} tick={MONO} tickLine={false} axisLine={false} width={40} />
              <Tooltip content={<Tip />} cursor={{ fill: C.grid }} isAnimationActive={false} />
              <Bar dataKey="views" fill={C.subtle} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Line dataKey="visitors" stroke={C.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h4 className="text-micro font-medium text-slate-500">{tt("vis.topSources")}</h4>
          {data.top_referrers.length ? (
            <ol className="mt-2 divide-y divide-ink-600">
              {data.top_referrers.map((r) => (
                <li key={r.domain} className="flex items-baseline justify-between gap-3 py-2 text-meta">
                  <span className="truncate text-slate-200">{r.domain}</span>
                  <span className="shrink-0 font-mono tabular-nums text-slate-400">{fmtInt(r.visitors)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-meta text-slate-500">{tt("vis.noSources")}</p>
          )}
          <p className="mt-3 flex items-center gap-3 text-micro text-slate-500">
            <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-3" style={{ background: C.accent }} aria-hidden="true" />{tt("vis.legendVisitors")}</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-[2px]" style={{ background: C.subtle }} aria-hidden="true" />{tt("vis.legendViews")}</span>
          </p>
        </div>
      </div>
    </Card>
  );
}
