// Makale tablosu: risk_flag ve event_type filtreleriyle.
import React, { useMemo, useState } from "react";
import { FlagChip, eventLabel, flagLabel } from "./ui.jsx";

const RISK_FLAGS = ["regulatory","competition","financial","legal","product","supply_chain","macro","reputation"];
const EVENT_TYPES = ["earnings","product","regulation","lawsuit","partnership","funding","macro","leadership","other"];

function sentimentColor(v) {
  if (v == null) return "#64748b";
  return v > 0.15 ? "#34d399" : v < -0.15 ? "#f87171" : "#94a3b8";
}

export default function ArticleTable({ articles }) {
  const [flag, setFlag] = useState("");
  const [event, setEvent] = useState("");

  const rows = useMemo(() => {
    return articles.filter((a) => {
      if (flag && !(a.risk_flags || []).includes(flag)) return false;
      if (event && a.event_type !== event) return false;
      return true;
    });
  }, [articles, flag, event]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-500">Filtre:</span>
        <select
          value={flag}
          onChange={(e) => setFlag(e.target.value)}
          className="rounded border border-ink-500 bg-ink-900 px-2 py-1 outline-none focus:border-accent"
        >
          <option value="">tüm risk bayrakları</option>
          {RISK_FLAGS.map((f) => (
            <option key={f} value={f}>{flagLabel(f)}</option>
          ))}
        </select>
        <select
          value={event}
          onChange={(e) => setEvent(e.target.value)}
          className="rounded border border-ink-500 bg-ink-900 px-2 py-1 outline-none focus:border-accent"
        >
          <option value="">tüm olay tipleri</option>
          {EVENT_TYPES.map((e) => (
            <option key={e} value={e}>{eventLabel(e)}</option>
          ))}
        </select>
        {(flag || event) && (
          <button onClick={() => { setFlag(""); setEvent(""); }} className="text-slate-500 hover:text-slate-300">
            temizle
          </button>
        )}
        <span className="ml-auto text-slate-500">{rows.length} makale</span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-ink-600">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-800 text-left text-[11px] uppercase text-slate-500">
              <th className="px-3 py-2">Başlık</th>
              <th className="px-3 py-2">Kaynak</th>
              <th className="px-3 py-2">Duygu</th>
              <th className="px-3 py-2">Olay</th>
              <th className="px-3 py-2">Riskler</th>
              <th className="px-3 py-2">Gerekçe</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  Bu filtreyle makale yok.
                </td>
              </tr>
            )}
            {rows.map((a) => (
              <tr key={a.id} className="border-b border-ink-700/60 align-top hover:bg-ink-800/50">
                <td className="px-3 py-2 max-w-[280px]">
                  <a href={a.url} target="_blank" rel="noreferrer" className="text-slate-200 hover:text-accent">
                    {a.title}
                  </a>
                  {a.published_at && (
                    <div className="text-[10px] text-slate-500">
                      {new Date(a.published_at).toLocaleString("tr-TR")}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-400">{a.source || "–"}</td>
                <td className="px-3 py-2 font-mono" style={{ color: sentimentColor(a.sentiment) }}>
                  {a.sentiment == null ? "–" : a.sentiment.toFixed(2)}
                </td>
                <td className="px-3 py-2 text-slate-400">{eventLabel(a.event_type)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {(a.risk_flags || []).map((f) => (
                      <FlagChip key={f} flag={f} />
                    ))}
                    {(!a.risk_flags || a.risk_flags.length === 0) && <span className="text-slate-600">–</span>}
                  </div>
                </td>
                <td className="px-3 py-2 max-w-[240px] text-slate-400">{a.rationale || "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
