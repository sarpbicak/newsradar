// Risk skoru zaman grafiği — recharts LineChart. X=tarih, Y=0-100.
// Noktalar yöne (stance) göre renklendirilir; yön DEĞİŞTİĞİ nokta beyaz halkayla işaretlenir.
import React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { stanceLabel } from "./ui.jsx";

const STANCE_COLOR = { bullish: "#0F8A4C", neutral: "#7A7770", bearish: "#C62828" };

function fmtDate(iso) {
  const d = new Date(iso);
  return (
    d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" }) +
    " " +
    d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
  );
}

export default function RiskHistoryChart({ history }) {
  // Karşılaştırma için en az 2 nokta gerekir — yoksa sessiz bilgi durumu.
  if (!history || history.length < 2) {
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 text-sm text-slate-500">
        Risk geçmişi grafiği için en az 2 tarama gerekli — karşılaştırma için yeterli geçmiş yok.
      </div>
    );
  }

  const data = history.map((h, i) => ({
    i,
    date: fmtDate(h.created_at),
    risk: h.risk_score,
    stance: h.stance,
  }));

  // Yöne göre renkli nokta; önceki noktadan yön değiştiyse büyük + beyaz halka.
  const renderDot = (props) => {
    const { cx, cy, index } = props;
    const cur = data[index];
    const prev = data[index - 1];
    const changed = prev && prev.stance !== cur.stance;
    return (
      <circle
        key={index}
        cx={cx}
        cy={cy}
        r={changed ? 5 : 3}
        fill={STANCE_COLOR[cur.stance] || "#7A7770"}
        stroke={changed ? "#1A1A18" : "none"}
        strokeWidth={changed ? 1.5 : 0}
      />
    );
  };

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-2 text-[11px] uppercase text-slate-500">
        Risk skoru geçmişi (0–100, eski → yeni)
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="#E7E3DA" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#8A867E", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 50, 100]}
            tick={{ fill: "#8A867E", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <ReferenceLine y={50} stroke="#E7E3DA" />
          <Tooltip
            contentStyle={{
              background: "#FFFFFF",
              border: "1px solid #E4E8EF",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#6B6862" }}
            formatter={(v, _n, p) => [`${v} · ${stanceLabel(p.payload.stance)}`, "risk"]}
          />
          <Line
            type="monotone"
            dataKey="risk"
            stroke="#6D4AFF"
            strokeWidth={2}
            dot={renderDot}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-slate-500">
        <span><span style={{ color: STANCE_COLOR.bullish }}>●</span> yükseliş</span>
        <span><span style={{ color: STANCE_COLOR.neutral }}>●</span> nötr</span>
        <span><span style={{ color: STANCE_COLOR.bearish }}>●</span> düşüş</span>
        <span className="text-slate-400">○ beyaz halka = yön değişimi</span>
      </div>
    </div>
  );
}
