// Analiz edilmiş haberler — masaüstünde tablo, MOBİLDE kart (yatay kaydırma YOK).
// risk_flag ve event_type filtreleriyle.
import React, { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { FlagChip, eventLabel, flagLabel } from "./ui.jsx";
import { tt, useI18n, fmtDate, fmtDateTime } from "../i18n.jsx";
import { C } from "../theme.js";

const RISK_FLAGS = ["regulatory","competition","financial","legal","product","supply_chain","macro","reputation"];
const EVENT_TYPES = ["earnings","product","regulation","lawsuit","partnership","funding","macro","leadership","other"];

function sentimentColor(v) {
  if (v == null) return C.neutral;
  return v > 0.15 ? C.pos : v < -0.15 ? C.neg : C.neutral;
}
function sentimentLabel(v) {
  if (v == null) return "—";
  return tt(v > 0.15 ? "sent.pos" : v < -0.15 ? "sent.neg" : "sent.neu");
}

// Duygu rozeti — renkli nokta + etiket (mobil kart + tablo ortak).
function SentimentBadge({ value }) {
  const c = sentimentColor(value);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ background: `${c}14`, color: c }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
      {sentimentLabel(value)}
      {value != null && <span className="font-mono text-[10px] font-normal">{value.toFixed(2)}</span>}
    </span>
  );
}

// "N kaynak" rozeti — aynı haber birden çok kaynakta çıktıysa (önem sinyali).
function SourceCount({ n }) {
  if (!n || n <= 1) return null;
  return (
    <span
      className="inline-flex items-center rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500"
      title={`Bu haber ${n} kaynakta çıktı — önem sinyali (kopyalar tek sayıldı)`}
    >
      {tt("art.sources", { n })}
    </span>
  );
}

function Title({ a }) {
  return (
    <a
      href={a.url}
      target="_blank"
      rel="noreferrer"
      className="group inline-flex items-start gap-1 font-medium text-slate-200 hover:text-accent"
    >
      <span>{a.title}</span>
      <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 opacity-0 transition group-hover:opacity-60" />
    </a>
  );
}

export default function ArticleTable({ articles }) {
  const { t } = useI18n();
  const [flag, setFlag] = useState("");
  const [event, setEvent] = useState("");

  const rows = useMemo(() => {
    return articles.filter((a) => {
      if (flag && !(a.risk_flags || []).includes(flag)) return false;
      if (event && a.event_type !== event) return false;
      return true;
    });
  }, [articles, flag, event]);

  const selectCls =
    "min-h-[40px] rounded-lg border border-ink-500 bg-ink-800 px-2 py-2 text-slate-300 outline-none focus:border-accent";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-500">{t("art.filter")}</span>
        <select value={flag} onChange={(e) => setFlag(e.target.value)} className={selectCls}>
          <option value="">{t("art.allFlags")}</option>
          {RISK_FLAGS.map((f) => (
            <option key={f} value={f}>{flagLabel(f)}</option>
          ))}
        </select>
        <select value={event} onChange={(e) => setEvent(e.target.value)} className={selectCls}>
          <option value="">{t("art.allEvents")}</option>
          {EVENT_TYPES.map((e) => (
            <option key={e} value={e}>{eventLabel(e)}</option>
          ))}
        </select>
        {(flag || event) && (
          <button
            onClick={() => { setFlag(""); setEvent(""); }}
            className="min-h-[40px] px-2 text-slate-500 hover:text-slate-300"
          >
            {t("art.clear")}
          </button>
        )}
        <span className="ml-auto text-slate-500">{t("art.count", { n: rows.length })}</span>
      </div>

      {rows.length === 0 && (
        <div className="rounded-xl border border-ink-600 bg-ink-800 px-4 py-6 text-center text-sm text-slate-500">
          {t("art.none")}
        </div>
      )}

      {/* MOBİL: kart listesi (tablo değil → yatay kaydırma yok) */}
      <div className="space-y-3 md:hidden">
        {rows.map((a) => (
          <div key={a.id} className="rounded-xl border border-ink-600 bg-ink-800 p-4 shadow-card">
            <Title a={a} />
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
              <span>{a.source || t("art.noSource")}</span>
              <SourceCount n={a.source_count} />
              {a.published_at && (
                <>
                  <span className="text-slate-600">·</span>
                  <span>{fmtDate(a.published_at)}</span>
                </>
              )}
              <span className="text-slate-600">·</span>
              <span>{eventLabel(a.event_type)}</span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <SentimentBadge value={a.sentiment} />
              {(a.risk_flags || []).map((f) => (
                <FlagChip key={f} flag={f} />
              ))}
            </div>
            {a.rationale && (
              <p className="mt-3 text-sm leading-relaxed text-slate-400">{a.rationale}</p>
            )}
          </div>
        ))}
      </div>

      {/* MASAÜSTÜ: tablo */}
      <div className="hidden overflow-hidden rounded-xl border border-ink-600 md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-700/50 text-left text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-medium">{t("art.title")}</th>
              <th className="px-4 py-3 font-medium">{t("art.source")}</th>
              <th className="px-4 py-3 font-medium">{t("art.sentiment")}</th>
              <th className="px-4 py-3 font-medium">{t("art.event")}</th>
              <th className="px-4 py-3 font-medium">{t("art.risks")}</th>
              <th className="px-4 py-3 font-medium">{t("art.rationale")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} className="border-b border-ink-700 align-top last:border-0 hover:bg-ink-700/40">
                <td className="max-w-[280px] px-4 py-3">
                  <Title a={a} />
                  {a.published_at && (
                    <div className="mt-0.5 text-[10px] text-slate-500">
                      {fmtDateTime(a.published_at)}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  <span className="inline-flex items-center gap-1.5">{a.source || "–"}<SourceCount n={a.source_count} /></span>
                </td>
                <td className="px-4 py-3"><SentimentBadge value={a.sentiment} /></td>
                <td className="px-4 py-3 text-slate-400">{eventLabel(a.event_type)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {(a.risk_flags || []).map((f) => <FlagChip key={f} flag={f} />)}
                    {(!a.risk_flags || a.risk_flags.length === 0) && <span className="text-slate-600">–</span>}
                  </div>
                </td>
                <td className="max-w-[240px] px-4 py-3 text-slate-400">{a.rationale || "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
