// Hero (tam ekran). Açılış BİR KEZ oynar (CSS, ≤1.5 s): başlık satırları maskeden, ardından cümle,
// buton ve canlı kart. Çıkış kaydırmaya bağlı (scrub): başlık hafifçe küçülüp yukarı kayar ve
// soluklaşır; radar ve kart farklı hızlarda kayar (parallax). Geri kaydırınca eski haline döner.
// Canlı kart ve etrafında akan başlıklar GERÇEK veri (/public/how-it-works); örnek yoksa yalnızca
// radar kalır. Sürekli döngüler (radar taraması, akan başlıklar) hero ekran dışındayken durur.
import React, { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { fmtPct, useI18n } from "../../i18n.jsx";
import { Button, LabelChip } from "../kit.jsx";
import { StatusTag, riskColor } from "../ui.jsx";
import { clamp01 } from "../../motion.js";
import { scrub, useScrub } from "./scroll.js";

function Radar() {
  return (
    <div className="absolute inset-0" aria-hidden="true">
      <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full text-signal-ink" fill="none" stroke="currentColor">
        {[49.5, 37, 24.5, 12].map((r) => (
          <circle key={r} cx="50" cy="50" r={r} strokeWidth="0.12" strokeOpacity="0.28" />
        ))}
        <path d="M50 0.5V99.5M0.5 50H99.5" strokeWidth="0.1" strokeOpacity="0.16" />
        {[[66, 30], [31, 62], [72, 71]].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="0.7" fill="currentColor" fillOpacity="0.5" stroke="none" />
        ))}
      </svg>
      <div className="lx-sweep" />
    </div>
  );
}

function LiveCard({ demo, t }) {
  const e = demo.entity;
  const a = e.analysis || {};
  const risk = a.risk_score;
  return (
    <div className="relative rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card">
      <div className="flex items-center gap-2 font-mono text-xs font-medium uppercase tracking-wider text-accent">
        <span className="relative flex h-2 w-2" aria-hidden="true">
          <span className="absolute inset-0 rounded-full bg-signal opacity-60 motion-safe:animate-ping" />
          <span className="relative h-2 w-2 rounded-full bg-signal" />
        </span>
        {t("land.hero.live", { name: e.name })}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className="lx-display text-[2rem] text-slate-100">{e.name}</span>
        <span className="font-mono text-sm text-slate-500">{e.type === "ticker" ? "$" : "#"}{e.query}</span>
        {e.analysis && <StatusTag stance={a.stance} evidence={e.evidence_strength} />}
      </div>
      {a.headline_verdict && (
        <p className="mt-4 font-display text-[1.375rem] font-medium leading-snug tracking-[-0.01em] text-slate-100">{a.headline_verdict}</p>
      )}
      {risk != null && (
        <div className="mt-6 flex items-center gap-3">
          <span className="text-sm text-slate-400">{t("land.hero.risk")}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-600">
            <div className="h-full origin-left rounded-full" style={{ transform: `scaleX(${risk / 100})`, background: riskColor(risk) }} />
          </div>
          <span className="lx-num text-sm font-semibold" style={{ color: riskColor(risk) }}>{risk}/100</span>
        </div>
      )}
      {e.price != null && (
        <p className="mt-3 flex items-baseline gap-2 font-mono text-sm">
          <span className="font-semibold text-slate-100">${e.price.toFixed(2)}</span>
          {e.change_percent != null && (
            <span className={e.change_percent >= 0 ? "text-emerald-500" : "text-rose-500"}>{fmtPct(e.change_percent, { digits: 2 })}</span>
          )}
        </p>
      )}
    </div>
  );
}

// Kartın arkasında yavaşça yukarı akan gerçek başlıklar (kesintisiz döngü için liste iki kez).
function Flow({ headlines, t }) {
  const items = [...headlines, ...headlines, ...headlines].slice(0, Math.max(6, headlines.length * 2));
  const loop = [...items, ...items];
  return (
    <div className="lx-fade-y pointer-events-none absolute -inset-x-3 -inset-y-8 -z-10 overflow-hidden sm:-inset-x-6 lg:-inset-y-28" aria-hidden="true">
      <div className="lx-flow space-y-3">
        {loop.map((h, i) => (
          <div key={i} className={`flex items-center gap-3 rounded-xl border border-ink-600 bg-ink-800 px-4 py-3 ${i % 2 ? "ml-6" : "mr-6"}`}>
            <LabelChip label={h.label} t={t} />
            <span className="truncate text-sm text-slate-300">{h.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Hero({ demo, onAnchor, onApp }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const title = useRef(null);
  const rest = useRef(null);
  const radar = useRef(null);
  const visual = useRef(null);
  const cue = useRef(null);
  const [paused, setPaused] = useState(false);

  // Döngüler yalnızca hero görünürken çalışsın.
  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return undefined;
    const io = new IntersectionObserver(([en]) => setPaused(!en.isIntersecting));
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useScrub(ref, (engine, el) =>
    scrub(engine, {
      trigger: el,
      start: "top top",
      end: "bottom top",
      rest: 0,
      restOffscreen: false,
      render: (p) => {
        const set = (node, tr, op) => {
          if (!node) return;
          node.style.transform = p === 0 ? "" : tr;
          node.style.opacity = p === 0 ? "" : op;
        };
        set(title.current, `translate3d(0, ${-p * 110}px, 0) scale(${1 - 0.1 * p})`, 1 - 0.8 * p);
        set(rest.current, `translate3d(0, ${-p * 70}px, 0)`, clamp01(1 - 1.6 * p));
        set(radar.current, `translate3d(0, ${p * 180}px, 0) scale(${1 + 0.08 * p})`, 1 - 0.5 * p);
        set(visual.current, `translate3d(0, ${-p * 60}px, 0)`, clamp01(1 - 1.1 * p));
        set(cue.current, "", clamp01(1 - 5 * p));
      },
    })
  );

  const lines = [t("land.hero.l1"), t("land.hero.l2"), t("land.hero.l3")];
  return (
    <section ref={ref} className={`relative flex min-h-[100svh] items-center overflow-clip ${paused ? "lx-paused" : ""}`}>
      <div className="mx-auto grid w-full max-w-[1360px] items-center gap-16 px-5 pb-28 pt-28 sm:px-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:gap-8 lg:px-10 lg:pb-24">
        <div className="relative z-10">
          <h1 ref={title} className="lx-display lx-h1 origin-left text-slate-100">
            {lines.map((line, i) => (
              <span key={i} className="lx-line">
                <span className="lx-intro-line" style={{ "--i": i }}>
                  {line}
                </span>
              </span>
            ))}
          </h1>
          <div ref={rest}>
            <p className="lx-body lx-intro-up mt-8 max-w-[34rem] text-slate-400" style={{ "--at": "var(--at-sub)" }}>
              {t("land.hero.sub")}
            </p>
            <div className="lx-intro-up mt-10 flex flex-wrap items-center gap-x-8 gap-y-5" style={{ "--at": "var(--at-cta)" }}>
              <Button as="a" href="/app" onClick={onApp} variant="primary" size="lg">
                {t("land.openApp")} <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </Button>
              <a href="#how-it-works" onClick={onAnchor} className="lx-link text-[17px] font-medium text-slate-200">
                {t("land.hero.how")} <span className="lx-arrow" aria-hidden="true">↓</span>
              </a>
            </div>
          </div>
        </div>
        <div className="relative mx-auto w-full max-w-[460px] lg:max-w-none">
          <div ref={radar} className="pointer-events-none absolute left-1/2 top-1/2 -z-20 aspect-square w-[170%]" style={{ marginLeft: "-85%", marginTop: "-85%" }}>
            <Radar />
          </div>
          <div ref={visual} className="relative mx-auto max-w-[440px]">
            {demo ? (
              <div className="lx-intro-up" style={{ "--at": "var(--at-card)" }}>
                <Flow headlines={demo.headlines} t={t} />
                <LiveCard demo={demo} t={t} />
              </div>
            ) : demo === null ? (
              <div className="skeleton h-[300px] w-full rounded-2xl" aria-hidden="true" />
            ) : null}
          </div>
        </div>
      </div>
      <div ref={cue} className="absolute bottom-7 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 sm:flex" aria-hidden="true">
        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500">{t("land.hero.scroll")}</span>
        <span className="relative h-8 w-px overflow-hidden bg-ink-500">
          <span className="lx-cue-dot absolute left-0 top-0 h-2 w-px bg-signal" />
        </span>
      </div>
    </section>
  );
}
