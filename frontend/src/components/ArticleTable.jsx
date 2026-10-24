// Haberler sekmesi — her satırda ortak etiket çipi (olumlu/olumsuz/nötr), başlık, kaynak,
// zaman; gerekçe açılır-kapanır. Tablo yerine tek liste düzeni (mobilde yatay kaydırma yok).
// risk_flag ve event_type filtreleriyle (ortak Select).
import React, { useMemo, useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import { RelTime, eventLabel, flagLabel, sentimentLabel } from "./ui.jsx";
import { getLang, tt, useI18n } from "../i18n.jsx";
import { Button, Card, Chip, LabelChip, Select } from "./kit.jsx";

const RISK_FLAGS = ["regulatory","competition","financial","legal","product","supply_chain","macro","reputation"];
const EVENT_TYPES = ["earnings","product","regulation","lawsuit","partnership","funding","macro","leadership","other"];

// Duygu → ortak haber etiketi (olumlu / olumsuz / nötr); sayısal değer title'da.
const labelOf = sentimentLabel;

// "N kaynak" — aynı haber birden çok kaynakta çıktıysa (önem sinyali).
function SourceCount({ n }) {
  if (!n || n <= 1) return null;
  return <span title={tt("art.sourcesTitle", { n })}> · {tt("art.sources", { n })}</span>;
}

// Seçenek metnini cümle başı büyük harfle göster ("Tüm risk bayrakları", "Makro").
const cap = (s) => (s ? s.charAt(0).toLocaleUpperCase(getLang() === "tr" ? "tr-TR" : "en-US") + s.slice(1) : s);

export default function ArticleTable({ articles }) {
  const { t } = useI18n();
  const [flag, setFlag] = useState("");
  const [event, setEvent] = useState("");

  const rows = useMemo(
    () =>
      articles.filter((a) => {
        if (flag && !(a.risk_flags || []).includes(flag)) return false;
        if (event && a.event_type !== event) return false;
        return true;
      }),
    [articles, flag, event]
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={flag} onChange={(e) => setFlag(e.target.value)} aria-label={t("art.allFlags")} wrapClassName="w-full sm:w-auto" className="sm:w-48">
          <option value="">{cap(t("art.allFlags"))}</option>
          {RISK_FLAGS.map((f) => (
            <option key={f} value={f}>{cap(flagLabel(f))}</option>
          ))}
        </Select>
        <Select value={event} onChange={(e) => setEvent(e.target.value)} aria-label={t("art.allEvents")} wrapClassName="w-full sm:w-auto" className="sm:w-48">
          <option value="">{cap(t("art.allEvents"))}</option>
          {EVENT_TYPES.map((e) => (
            <option key={e} value={e}>{cap(eventLabel(e))}</option>
          ))}
        </Select>
        {(flag || event) && (
          <Button variant="ghost" size="sm" onClick={() => { setFlag(""); setEvent(""); }}>
            {t("art.clear")}
          </Button>
        )}
        <span className="ml-auto text-micro text-slate-500">{t("art.count", { n: rows.length })}</span>
      </div>

      {rows.length === 0 ? (
        <Card className="p-6 text-center text-body text-slate-500">{t("art.none")}</Card>
      ) : (
        <ul className="divide-y divide-ink-600 border-y border-ink-600">
          {rows.map((a) => {
            // Olay tipiyle aynı adı taşıyan risk bayrağı ikinci kez gösterilmez (ör. "makro").
            const ev = a.event_type ? eventLabel(a.event_type) : null;
            const flags = (a.risk_flags || []).filter((f) => !ev || flagLabel(f).toLocaleLowerCase() !== ev.toLocaleLowerCase());
            return (
            <li key={a.id} className="px-2 py-4 transition-colors duration-hover ease-std hover:bg-ink-800 sm:px-3">
              <div className="flex items-start gap-3">
                {/* Sabit genişlikli duygu sütunu: başlıklar aynı hizadan başlar. */}
                <span title={a.sentiment != null ? a.sentiment.toFixed(2) : undefined} className="w-[5.5rem] shrink-0 pt-0.5">
                  <LabelChip label={labelOf(a.sentiment)} t={t} />
                </span>
                <div className="min-w-0 flex-1">
                  <a href={a.url} target="_blank" rel="noreferrer" className="group inline font-medium text-slate-100 transition-colors duration-hover ease-std hover:text-accent">
                    {a.title}
                    <ExternalLink className="ml-1 inline h-3 w-3 align-baseline opacity-0 transition-opacity group-hover:opacity-60" aria-hidden="true" />
                  </a>
                  <p className="mt-1 text-micro text-slate-500">
                    {a.source || t("art.noSource")}
                    <SourceCount n={a.source_count} />
                    {a.published_at && <> · <RelTime iso={a.published_at} /></>}
                    {ev && <> · {ev}</>}
                  </p>
                  {flags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {flags.map((f) => (
                        <Chip key={f} tone="neutral">{flagLabel(f)}</Chip>
                      ))}
                    </div>
                  )}
                  {a.rationale && (
                    <details className="group mt-2">
                      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-micro font-medium text-slate-400 transition-colors hover:text-slate-200 [&::-webkit-details-marker]:hidden">
                        <ChevronRight className="h-3.5 w-3.5 transition-transform duration-hover ease-std group-open:rotate-90" aria-hidden="true" />
                        {t("art.rationale")}
                      </summary>
                      <p className="mt-1.5 max-w-3xl text-meta leading-relaxed text-slate-400">{a.rationale}</p>
                    </details>
                  )}
                </div>
              </div>
            </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
