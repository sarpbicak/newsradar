// "Bunları da izlemek ister misin?" — co-mentioned şirket önerileri.
// Öneri yoksa hiç render edilmez (boş başlık durmasın).
import React, { useState } from "react";
import { Plus } from "lucide-react";
import { useI18n } from "../i18n.jsx";
import { Button, Card, Chip } from "./kit.jsx";

export default function SuggestionsSection({ suggestions, onAdd, onDismiss, embedded = false }) {
  const { t } = useI18n();
  const [busyId, setBusyId] = useState(null);

  if (!suggestions || suggestions.length === 0) return null;

  async function handle(action, id) {
    setBusyId(id);
    try {
      await action(id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={embedded ? "" : "rounded-card bg-ink-800 p-5"}>
      {!embedded && <div className="mb-1 font-display text-base font-medium text-slate-100">{t("sug.title")}</div>}
      <p className="mb-4 text-meta text-slate-500">{t("sug.subtitle")}</p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {suggestions.map((s) => {
          const busy = busyId === s.id;
          return (
            <Card key={s.id} className="flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-display text-base font-medium text-slate-100">{s.name}</span>
                  {s.ticker && <span className="tabular-nums text-micro text-slate-500">${s.ticker}</span>}
                </div>
                <Chip tone="neutral">{t("sug.mentioned", { n: s.mention_count })}</Chip>
              </div>
              {s.why_relevant && <p className="text-meta leading-relaxed text-slate-400">{s.why_relevant}</p>}
              <p className="text-micro text-slate-500">
                {s.source_entity_names?.length > 0 && <>{t("sug.inNews", { names: s.source_entity_names.join(", ") })} · </>}
                {s.add_as_type === "ticker" ? t("sug.addTicker") : t("sug.addKeyword", { lang: s.add_as_language ? ` (${s.add_as_language})` : "" })}
              </p>
              <div className="mt-auto flex gap-2">
                <Button variant="primary" size="sm" icon={Plus} onClick={() => handle(onAdd, s.id)} disabled={busy}>
                  {busy ? "…" : t("sug.add")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handle(onDismiss, s.id)} disabled={busy}>
                  {t("sug.hide")}
                </Button>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
