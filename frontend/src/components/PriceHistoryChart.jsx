// Fiyat zaman grafiği — recharts LineChart. X=tarih, Y=fiyat (otomatik ölçek).
// Risk grafiğiyle AYNI tarih biçimi kullanır; detayda üst üste konunca aynı
// zaman ekseninde okunur ("risk arttığında fiyat ne yaptı").
import React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { timeAgo } from "./ui.jsx";

function fmtDate(iso) {
  const d = new Date(iso);
  return (
    d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" }) +
    " " +
    d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
  );
}

export default function PriceHistoryChart({ history, updatedAt, isTicker }) {
  // Keyword entity → fiyat kavramı yok, bileşeni hiç gösterme.
  if (!isTicker) return null;

  if (!history || history.length < 2) {
    return (
      <div className="rounded-xl border border-ink-600 bg-ink-800 p-4 text-sm text-slate-500">
        Fiyat geçmişi için en az 2 snapshot gerekli — bir sonraki yenilemelerde dolacak.
      </div>
    );
  }

  const data = history.map((h, i) => ({ i, date: fmtDate(h.fetched_at), price: h.price }));

  return (
    <div className="rounded-xl border border-ink-600 bg-ink-800 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[11px] uppercase text-slate-500">Fiyat geçmişi (eski → yeni)</span>
        {updatedAt && (
          <span className="text-[10px] text-slate-500" title="son fiyatın çekilme zamanı">
            son: {timeAgo(updatedAt)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="#313747" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#6B6F7E", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: "#6B6F7E", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={(v) => `$${v}`}
          />
          <Tooltip
            contentStyle={{
              background: "#272C3A",
              border: "1px solid #E4E8EF",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#B4B8C4" }}
            formatter={(v) => [`$${v}`, "fiyat"]}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#60A5FA"
            strokeWidth={2}
            dot={{ r: 2, fill: "#60A5FA" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 text-[10px] text-slate-500">
        Not: Fiyat yalnızca haberin fiyatlanıp fiyatlanmadığını görmek için — hedef/tahmin değil.
      </div>
    </div>
  );
}
