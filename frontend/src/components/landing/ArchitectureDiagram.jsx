// "Altında ne var" — mimari şeması (HTML + tema tokenları; SVG'de metin mobilde okunmaz
// küçüklüğe inerdi). Katmanlar soldan sağa (masaüstü) / yukarıdan aşağı (mobil) akar.
// Erişilebilirlik: anlamlı liste (ol/li); oklar dekoratif (aria-hidden).
import React from "react";
import { useI18n } from "../../i18n.jsx";

function Node({ title, detail, strong = false }) {
  return (
    <div className={`rounded-lg border bg-ink-800 px-3 py-2 ${strong ? "border-accent/60 shadow-[inset_3px_0_0_rgb(var(--accent))]" : "border-ink-500"}`}>
      <div className="text-[13px] font-semibold text-slate-100">{title}</div>
      {detail && <div className="mt-0.5 font-mono text-[11px] leading-snug text-slate-400">{detail}</div>}
    </div>
  );
}

function Arrow({ label }) {
  return (
    <div className="flex items-center justify-center gap-1 py-1 text-slate-500 md:px-1 md:py-0" aria-hidden="true">
      <span className="md:hidden">↓</span>
      <span className="hidden md:inline">→</span>
      {label && <span className="font-mono text-[10px]">{label}</span>}
    </div>
  );
}

function Lane({ name, children }) {
  return (
    <li className="rounded-xl border border-ink-600 bg-ink-900/60 p-3">
      <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-slate-500">{name}</div>
      <div className="flex flex-col items-stretch md:flex-row md:items-center md:gap-1">{children}</div>
    </li>
  );
}

export default function ArchitectureDiagram() {
  const { t } = useI18n();
  return (
    <ol className="space-y-3" aria-label={t("land.stack.title")}>
      <Lane name={t("land.stack.frontend")}>
        <Node title={t("land.stack.browser")} detail="Vite · Tailwind · i18n" />
        <Arrow label="HTTPS" />
        <Node title="CloudFront" detail="HTTP/2+3 · www → apex" strong />
        <Arrow label="OAC" />
        <Node title="S3" detail="private bucket" />
      </Lane>
      <Lane name={t("land.stack.api")}>
        <Node title="Caddy" detail="api.newsradarapp.com · auto TLS" />
        <Arrow />
        <Node title="FastAPI" detail="Docker · EC2 t4g (arm64)" strong />
        <Arrow />
        <Node title="Claude API" detail="Anthropic · article + verdict + chat" />
        <Arrow />
        <Node title={t("land.stack.sources")} />
      </Lane>
      <Lane name={t("land.stack.data")}>
        <Node title="SQLite" detail="WAL · Docker volume" strong />
        <Arrow label="sqlite3 .backup" />
        <Node title={t("land.stack.backup")} detail="S3 · versioned · 30d" />
        <Arrow />
        <Node title="SSM Parameter Store" detail="secrets · KMS" />
      </Lane>
      <Lane name={t("land.stack.delivery")}>
        <Node title="GitHub Actions" detail={t("land.stack.noKeys")} strong />
        <Arrow label="arm64" />
        <Node title="ECR" detail="scan on push" />
        <Arrow label="SSM" />
        <Node title="EC2" detail={t("land.stack.rollback")} />
      </Lane>
    </ol>
  );
}
