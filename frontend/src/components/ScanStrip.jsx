// Tarama ilerleme göstergesi — bilgi öncelikli, sade (parçacık/halka/nokta YOK).
// Backend her adımı yayınlar ({step, step_entity, step_count, progress_fraction}); metin
// kullanıcının dilinde: "NVIDIA için haberler çekiliyor…", "… 12 yeni haber analiz
// ediliyor…", "… değerlendirme yazılıyor…", kısa süre "Tesla atlandı, yeni veri yok".
// Çubuk entity dilimlerinin ortalamasıyla dolar (entity içindeki adımlarla da ilerler,
// 0'da takılmaz). Süresi belirsiz adımlarda (fiyat/haber çekme) dolu kısımda hafif
// parlama; prefers-reduced-motion'da kapalı (index.css). Sağda done / total sayacı.
import React, { useEffect, useState } from "react";
import { useI18n, refreshParts } from "../i18n.jsx";

const STEP_KEYS = {
  fetch: "notice.stepFetch",
  filter: "notice.stepFilter",
  analyze: "notice.stepAnalyze",
  assess: "notice.stepAssess",
};

export default function ScanStrip({
  phase = "running", // "starting" | "running" | "done"
  currentEntity = null,
  step = null,          // prices | fetch | filter | analyze | assess
  stepEntity = null,
  stepCount = null,
  fraction = null,      // 0..1 (entity dilimlerinin ortalaması)
  skippedEntity = null, // "X atlandı" notu (~3 sn)
  done = 0,
  total = 0,
  summary = null, // { news, analyses } — done fazında
  fading = false,
  isMobile = false,
}) {
  const { t } = useI18n();
  const pct = phase === "done"
    ? 100
    : fraction != null && fraction > 0
      ? Math.round(fraction * 100)
      : total > 0 ? Math.round((done / total) * 100) : 0;
  // Süresi belirsiz adımlar → parlama (donmuş görünmesin).
  const indeterminate = phase === "starting" || step === "prices" || step === "fetch";

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
  } else if (skippedEntity) {
    label = t("notice.stepSkipped", { name: skippedEntity });
    labelKey = `skip:${skippedEntity}`;
  } else if (step === "prices") {
    label = t("notice.stepPrices");
    labelKey = "prices";
  } else if (step && stepEntity && STEP_KEYS[step]) {
    label = t(STEP_KEYS[step], { name: stepEntity, n: stepCount ?? 0 });
    labelKey = `${step}:${stepEntity}`;
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
          {phase !== "done" && indeterminate && <span className="nr-bar__shine" />}
        </div>
      </div>
    </div>
  );
}
