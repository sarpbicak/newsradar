// Analiz edilmiş makalelerin duygu dağılımı — recharts BarChart.
import React from "react";
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function color(v) {
  return v > 0.15 ? "#34d399" : v < -0.15 ? "#f87171" : "#94a3b8";
}

export default function SentimentChart({ articles }) {
  const data = articles
    .filter((a) => a.analyzed && a.sentiment != null)
    .slice(0, 30)
    .reverse()
    .map((a, i) => ({ i: i + 1, sentiment: a.sentiment, title: a.title }));

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 text-sm text-slate-500">
        Grafik için analiz edilmiş makale yok.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-2 text-[11px] uppercase text-slate-500">
        Haber duygusu (analiz edilmiş, eski → yeni)
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
          <XAxis dataKey="i" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis
            domain={[-1, 1]}
            ticks={[-1, 0, 1]}
            tick={{ fill: "#64748b", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <ReferenceLine y={0} stroke="#2a3446" />
          <Tooltip
            cursor={{ fill: "rgba(79,140,255,0.08)" }}
            contentStyle={{ background: "#0f1420", border: "1px solid #2a3446", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#94a3b8" }}
            formatter={(v) => [v.toFixed(2), "duygu"]}
            labelFormatter={(_, p) => p?.[0]?.payload?.title?.slice(0, 60) || ""}
          />
          <Bar dataKey="sentiment" radius={[2, 2, 2, 2]}>
            {data.map((d, idx) => (
              <Cell key={idx} fill={color(d.sentiment)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
