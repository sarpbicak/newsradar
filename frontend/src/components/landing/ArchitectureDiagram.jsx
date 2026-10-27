// "Altında ne var" — sade mimari şeması. Beş şerit, her biri soldan sağa akan üç düğüm.
// Kaydırdıkça şeritler sırayla belirir, düğümler gelir ve aradaki çizgiler çizilir (scrub; geri
// kaydırınca geri sarar). Yalnızca transform/opacity. Model adı ("Claude") landing'de yalnızca burada.
// Erişilebilirlik: anlamlı liste (ol/li); çizgiler dekoratif.
import React, { useRef } from "react";
import { useI18n } from "../../i18n.jsx";
import { paintSegs, scrub, useScrub } from "./scroll.js";

const LANE = 0.16; // şerit başına ilerleme payı

export default function ArchitectureDiagram() {
  const { t } = useI18n();
  const ref = useRef(null);
  const lanes = [
    { name: t("land.stack.frontend"), nodes: ["React · Vite", "CloudFront", "S3"] },
    { name: t("land.stack.api"), nodes: ["Caddy · TLS", "FastAPI · Docker", "EC2"] },
    { name: t("land.stack.ai"), nodes: ["Finnhub · GNews · GDELT", "Claude", t("land.stack.verdict")], key: 1 },
    { name: t("land.stack.data"), nodes: ["SQLite", t("land.stack.nightly"), "S3"] },
    { name: t("land.stack.delivery"), nodes: ["GitHub Actions", "OIDC", t("land.stack.deploy")] },
  ];
  useScrub(
    ref,
    (engine, el) => {
      const nodes = el.querySelectorAll("[data-fx]");
      return scrub(engine, { trigger: el, end: "bottom 75%", render: (p) => paintSegs(nodes, p) });
    },
    [t]
  );
  return (
    <ol ref={ref} data-rv="" className="divide-y divide-ink-600 border-y border-ink-600" aria-label={t("land.stack.title")}>
      {lanes.map((lane, j) => {
        const base = j * LANE;
        return (
          <li key={j} className="grid gap-4 py-6 sm:grid-cols-[10rem_minmax(0,1fr)] sm:items-center sm:py-7">
            <span data-fx="rise" data-seg={`${base},${base + 0.08}`} className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">
              {lane.name}
            </span>
            <div className="flex items-center">
              {lane.nodes.map((node, k) => {
                const at = base + 0.02 + k * 0.045;
                return (
                  <React.Fragment key={k}>
                    {k > 0 && (
                      <span className="relative mx-2 h-px min-w-[14px] flex-1 bg-ink-600 sm:mx-3 sm:max-w-[120px]" aria-hidden="true">
                        <span data-fx="line" data-seg={`${at - 0.03},${at + 0.01}`} className="absolute inset-0 origin-left bg-signal" />
                      </span>
                    )}
                    <span
                      data-fx="rise"
                      data-seg={`${at},${at + 0.06}`}
                      className={`rounded-control border px-3 py-1.5 text-center text-[13px] leading-tight sm:px-4 sm:py-2 sm:text-[15px] ${
                        lane.key === k ? "border-accent text-slate-100" : "border-ink-500 text-slate-300"
                      }`}
                    >
                      {node}
                    </span>
                  </React.Fragment>
                );
              })}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
