// Hero (tam ekran). Açılış BİR KEZ oynar (CSS, ≤1.5 s): başlık satırları maskeden, ardından cümle,
// buton ve canlı kart. Çıkış kaydırmaya bağlı (scrub): başlık hafifçe küçülüp yukarı kayar ve
// en fazla ~0,6 opaklığa iner; radar ve kart farklı hızlarda kayar (parallax). Mobilde/dokunmatikte
// içerik hiç solmaz (opaklık 1), yalnızca birkaç piksel kayar. Geri kaydırınca eski haline döner.
// Canlı kart ve etrafında akan başlıklar GERÇEK veri (/public/how-it-works); örnek yoksa yalnızca
// radar kalır. Sürekli döngüler (radar taraması, akan başlıklar) hero ekran dışındayken durur.
import React, { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { fmtPct, useI18n } from "../../i18n.jsx";
import { fmtMoney } from "../../money.js";
import { Button, LabelChip } from "../kit.jsx";
import { NewsPill, riskColor } from "../ui.jsx";
import { clamp01 } from "../../motion.js";
import { scrub, useScrub } from "./scroll.js";

// Teknik radar: ince halkalar, dış halkada ölçek işaretleri (5°'de bir, 30°'de uzun), artı
// çizgileri ve dönen tek bir ince çizgi. Işıma/dolgu yok. Mobilde (index.css .lx-radar) dış halka
// ve işaretler gizlenir, kalan çizgiler incelir.
const TICKS = Array.from({ length: 72 }, (_, i) => i * 5);
function Radar() {
  return (
    <div className="absolute inset-0" aria-hidden="true">
      <svg viewBox="0 0 100 100" className="lx-radar absolute inset-0 h-full w-full text-signal-ink" fill="none" stroke="currentColor">
        {[49.5, 37, 24.5, 12].map((r, i) => (
          <circle key={r} className={i === 0 ? "lx-radar-outer" : "lx-radar-line"} cx="50" cy="50" r={r} strokeWidth="0.1" strokeOpacity="0.3" />
        ))}
        {TICKS.map((d) => {
          const long = d % 30 === 0;
          const a = (d * Math.PI) / 180;
          const r1 = 49.5, r2 = long ? 47.3 : 48.4;
          return (
            <line key={d} className="lx-radar-outer" x1={50 + r1 * Math.sin(a)} y1={50 - r1 * Math.cos(a)} x2={50 + r2 * Math.sin(a)} y2={50 - r2 * Math.cos(a)}
              strokeWidth={long ? 0.16 : 0.09} strokeOpacity={long ? 0.5 : 0.3} />
          );
        })}
        <path className="lx-radar-line" d="M50 0.5V99.5M0.5 50H99.5" strokeWidth="0.08" strokeOpacity="0.2" strokeDasharray="0.6 0.9" />
        {[[66, 30], [31, 62], [72, 71]].map(([x, y]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="0.7" fill="currentColor" fillOpacity="0.5" stroke="none" />
        ))}
      </svg>
      <div className="lx-sweep" />
    </div>
  );
}

// Çıkışta içerik masaüstünde en fazla bu opaklığa iner; mobil/dokunmatikte hiç solmaz.
const MIN_OPACITY = 0.6;
const CALM_MQ = "(max-width: 768px), (hover: none)";

function LiveCard({ demo, t, lang }) {
  const e = demo.entity;
  const a = e.analysis || {};
  const risk = a.risk_score;
  return (
    <div className="relative rounded-card border border-ink-600 bg-ink-800 p-6">
      <div className="flex items-center gap-2 text-meta font-medium text-accent">
        <span className="relative flex h-2 w-2" aria-hidden="true">
          <span className="absolute inset-0 rounded-full bg-signal opacity-60 motion-safe:animate-ping" />
          <span className="relative h-2 w-2 rounded-full bg-signal" />
        </span>
        {t("land.hero.live", { name: e.name })}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className="lx-display text-[2rem] text-slate-100">{e.name}</span>
        <span className="tabular-nums text-sm text-slate-500">{e.type === "ticker" ? "$" : "#"}{e.query}</span>
        {e.analysis && <NewsPill a={a} evidence={e.evidence_strength} horizon="short" />}
      </div>
      {a.headline_verdict && (
        <p className="mt-4 font-display text-[1.375rem] font-medium leading-snug tracking-[-0.01em] text-slate-100">{a.headline_verdict}</p>
      )}
      {risk != null && (
        <div className="mt-6 flex items-center gap-3">
          <span className="text-sm text-slate-400">{t("land.hero.risk")}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-[2px] bg-ink-600">
            <div className="h-full origin-left" style={{ transform: `scaleX(${risk / 100})`, background: riskColor(risk) }} />
          </div>
          <span className="lx-num text-sm font-semibold" style={{ color: riskColor(risk) }}>{risk}/100</span>
        </div>
      )}
      {e.price != null && (
        <p className="mt-3 flex items-baseline gap-2 tabular-nums text-sm">
          <span className="font-semibold text-slate-100">{fmtMoney(e.price, e.currency || "USD", lang)}</span>
          {e.change_percent != null && (
            <span className={e.change_percent >= 0 ? "text-emerald-500" : "text-rose-500"}>{fmtPct(e.change_percent, { digits: 2 })}</span>
          )}
        </p>
      )}
    </div>
  );
}

// Kartın arkasında yavaşça yukarı akan gerçek başlıklar (kesintisiz döngü için liste iki kez).
// Mobilde kart genişliğinde kırpılır (yanlardan taşmaz), daha soluktur ve kartın üst/altında
// yalnızca kısa bir şerit görünür; kart opak olduğundan metinle üst üste binmez.
function Flow({ headlines, t }) {
  const items = [...headlines, ...headlines, ...headlines].slice(0, Math.max(6, headlines.length * 2));
  const loop = [...items, ...items];
  return (
    <div className="lx-fade-y lx-flow-band pointer-events-none absolute -inset-y-14 inset-x-0 -z-10 overflow-hidden opacity-50 sm:-inset-x-6 sm:-inset-y-8 sm:opacity-100 lg:-inset-y-28" aria-hidden="true">
      <div className="lx-flow space-y-3">
        {loop.map((h, i) => (
          <div key={i} className={`flex items-center gap-3 rounded-card border border-ink-600 bg-ink-800 px-4 py-3 ${i % 2 ? "ml-4 sm:ml-6" : "mr-4 sm:mr-6"}`}>
            <LabelChip label={h.label} t={t} />
            <span className="truncate text-sm text-slate-300">{h.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Hero({ demo, onAnchor, onApp }) {
  const { t, lang } = useI18n();
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

  useScrub(ref, (engine, el) => {
    const calm = window.matchMedia(CALM_MQ);
    return scrub(engine, {
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
        if (calm.matches) {
          // Mobil/dokunmatik: okunabilirlik önce — solma yok, yalnızca birkaç piksel kayma.
          set(title.current, `translate3d(0, ${-p * 12}px, 0) scale(${1 - 0.02 * p})`, 1);
          set(rest.current, `translate3d(0, ${-p * 8}px, 0)`, 1);
          set(radar.current, `translate3d(0, ${p * 40}px, 0)`, 1);
          set(visual.current, `translate3d(0, ${-p * 6}px, 0)`, 1);
          return;
        }
        set(title.current, `translate3d(0, ${-p * 110}px, 0) scale(${1 - 0.1 * p})`, 1 - (1 - MIN_OPACITY) * p);
        set(rest.current, `translate3d(0, ${-p * 70}px, 0)`, Math.max(MIN_OPACITY, 1 - 1.6 * p));
        set(radar.current, `translate3d(0, ${p * 180}px, 0) scale(${1 + 0.08 * p})`, 1 - 0.4 * p);
        set(visual.current, `translate3d(0, ${-p * 60}px, 0)`, Math.max(MIN_OPACITY, 1 - 1.1 * p));
        set(cue.current, "", clamp01(1 - 5 * p)); // "kaydır" işareti (dekoratif) tamamen kaybolur
      },
    });
  });

  const lines = [t("land.hero.l1"), t("land.hero.l2"), t("land.hero.l3")].filter(Boolean);
  return (
    // clip-path: radar/ızgara/akan başlıklar header bandına (üst 64px + güvenli alan) taşmasın.
    <section
      ref={ref}
      className={`relative flex min-h-[100svh] items-center overflow-clip ${paused ? "lx-paused" : ""}`}
      style={{ clipPath: "inset(calc(4rem + env(safe-area-inset-top)) 0 0 0)" }}
    >
      <div className="grid-bg" aria-hidden="true" />
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
              <a href="#how-it-works" onClick={onAnchor} className="link-u tap inline-flex items-center gap-1.5 text-[17px] font-medium text-slate-200">
                {t("land.hero.how")} <span className="lx-arrow" aria-hidden="true">↓</span>
              </a>
            </div>
          </div>
        </div>
        <div className="relative mx-auto w-full max-w-[460px] lg:max-w-none">
          {/* Mobilde merkez sabit noktada (kart yüksekliğine bağlı değil): iskelet → kart geçişinde
              radar kaymasın (CLS). Geniş ekranda kartın dikey ortası. */}
          <div ref={radar} className="pointer-events-none absolute left-1/2 top-[11.25rem] -z-20 aspect-square w-[170%] lg:top-1/2" style={{ marginLeft: "-85%", marginTop: "-85%" }}>
            <Radar />
          </div>
          <div ref={visual} className="relative mx-auto max-w-[440px]">
            {demo ? (
              <div className="lx-intro-up" style={{ "--at": "var(--at-card)" }}>
                <Flow headlines={demo.headlines} t={t} />
                <LiveCard demo={demo} t={t} lang={lang} />
              </div>
            ) : demo === null ? (
              <div className="skeleton h-[300px] w-full rounded-card" aria-hidden="true" />
            ) : null}
          </div>
        </div>
      </div>
      <div ref={cue} className="absolute bottom-7 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 sm:flex" aria-hidden="true">
        <span className="text-micro text-slate-500">{t("land.hero.scroll")}</span>
        <span className="relative h-8 w-px overflow-hidden bg-ink-500">
          <span className="lx-cue-dot absolute left-0 top-0 h-2 w-px bg-signal" />
        </span>
      </div>
    </section>
  );
}
