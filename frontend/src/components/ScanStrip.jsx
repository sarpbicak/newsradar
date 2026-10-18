// Tarama ilerleme göstergesi — bilgi öncelikli, sade (parçacık/halka/nokta YOK).
// Şu an analiz edilen şirketi ("Tesla analiz ediliyor…") + gerçek ilerleme çubuğunu
// (done/total) + sağda mono sayacı gösterir. Kutu/çerçeve yok; kağıt zemininde durur.
// Bitişte çubuk dolar, kısa gecikmeyle "Tamamlandı · N haber · N analiz"e döner, söner.
// prefers-reduced-motion: parlama (shimmer) durur, çubuk kalır.
import React, { useEffect, useState } from "react";
import { useI18n, refreshParts } from "../i18n.jsx";

export default function ScanStrip({
  phase = "running", // "starting" | "running" | "done"
  currentEntity = null,
  done = 0,
  total = 0,
  summary = null, // { news, analyses } — done fazında
  fading = false,
  isMobile = false,
}) {
  const { t } = useI18n();
  const pct = phase === "done" ? 100 : total > 0 ? Math.round((done / total) * 100) : 0;

  // Bitişte önce çubuk dolsun, ~300ms sonra metin "Tamamlandı…"ya dönsün.
  const [showDone, setShowDone] = useState(false);
  useEffect(() => {
    if (phase !== "done") {
      setShowDone(false);
      return;
    }
    const id = setTimeout(() => setShowDone(true), 300);
    return () => clearTimeout(id);
  }, [phase]);

  // Sol taraftaki durum metni (değişince yumuşak fade — key ile yeniden mount).
  let label, labelKey;
  if (phase === "done") {
    // Önce çubuk dolsun (~300ms boşluk), sonra "Tamamlandı…" belirsin.
    label = showDone && summary
      ? t("notice.scanDone", { parts: refreshParts(summary, t).slice(0, 2).join(" · ") })
      : " ";
    labelKey = showDone ? "done" : "done-fill";
  } else if (phase === "starting") {
    label = t("notice.scanStarting");
    labelKey = "starting";
  } else if (currentEntity) {
    label = t("notice.analyzing", { name: currentEntity });
    labelKey = `e:${currentEntity}`;
  } else {
    label = t("notice.scanWorking");
    labelKey = "working";
  }

  return (
    <div
      className={`w-full max-w-xl ${fading ? "nr-strip--fade" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span
          key={labelKey}
          className={`nr-name-in min-w-0 truncate text-sm ${
            showDone ? "font-medium text-accent" : "text-slate-400"
          }`}
        >
          {label}
        </span>
        {total > 0 && (
          <span className="shrink-0 font-mono text-xs tabular-nums text-slate-500">
            {phase === "done" ? total : done} / {total}
          </span>
        )}
      </div>

      <div className="nr-bar mt-2 bg-accent/15" aria-hidden="true">
        <div className="nr-bar__fill" style={{ width: `${pct}%` }}>
          {phase !== "done" && <span className="nr-bar__shine" />}
        </div>
      </div>
    </div>
  );
}
