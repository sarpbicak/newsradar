// "Nasıl çalışır" — kaydırmayla ilerleyen anlatım.
// Masaüstü: bölüm ekrana sabitlenir (CSS sticky; uzun kap = 4 adımlık kaydırma aralığı, ilerlemeyi
// ScrollTrigger ölçer). Solda 4 adım + ilerleme çizgisi, sağda tek uygulama penceresi; pencere
// adımlar arasında crossfade + hafif ölçekle geçer, sahneler tamamen kaydırmayla oynar/geri sarar.
// Mobil (ve reduced-motion): sabitleme yok; her adımın altında kendi penceresi, o adımın kaydırma
// aralığında scrub ile oynar. Motor yoksa her şey son karede, statik.
// Erişilebilirlik: soluk adım metni de AA (renk geçişi, opaklık değil); pencere içeriği tek
// görünür sahne dışında aria-hidden.
import React, { useLayoutEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n.jsx";
import { clamp01, ease, prefersReducedMotion, seg } from "./motion.js";
import { SCENES } from "./Scenes.jsx";
import { DESKTOP_MQ, scrub, useMedia, useScrub } from "./scroll.js";
import { Lines } from "./Type.jsx";

const STEPS = [1, 2, 3, 4];
const STEP_VH = 85;   // masaüstünde adım başına kaydırma (vh)
const HOLD = 0.72;    // adım aralığının sahneye ayrılan kısmı; kalanında son kare bekler
const FADE = 0.1;     // adım sınırında geçiş: önce eski sahne söner, sonra yenisi gelir (adım birimi)

export function AppWindow({ children, className = "" }) {
  return (
    <div className={`lx-window overflow-hidden rounded-2xl border border-ink-600 bg-ink-800 ${className}`}>
      <div className="flex items-center gap-3 border-b border-ink-600 bg-ink-900/70 px-4 py-3" aria-hidden="true">
        <span className="flex gap-1.5">
          {[0, 1, 2].map((i) => <span key={i} className="h-3 w-3 rounded-full bg-ink-500" />)}
        </span>
        <span className="mx-auto flex h-7 w-full max-w-[260px] items-center justify-center rounded-md bg-ink-700 font-mono text-xs text-slate-500">
          newsradarapp.com/app
        </span>
        <span className="w-[48px]" />
      </div>
      <div className="p-5 sm:p-6">{children}</div>
    </div>
  );
}

// pinned: boyutlar ekran YÜKSEKLİĞİNE göre akışkan — 4 adım kısa dizüstü ekranına da sığsın.
function StepText({ n, t, pinned = false }) {
  return (
    <>
      <div className="lx-step-num lx-num text-sm font-medium">0{n}</div>
      <h3 className={`lx-display ${pinned ? "mt-2 text-[clamp(1.75rem,1rem+2.6vh,3rem)]" : "mt-3 text-[2rem]"}`}>{t(`land.step${n}.title`)}</h3>
      <p className={`lx-step-body mt-3 max-w-md ${pinned ? "text-[clamp(1rem,0.55rem+1.25vh,1.25rem)] leading-relaxed" : "lx-body"}`}>
        {t(`land.step${n}.body`)}
      </p>
    </>
  );
}

// Sahnenin pencerede görünürlüğü (u: 0..4 adım birimi).
function visibility(u, i) {
  const fin = i === 0 ? 1 : seg(u, i, i + FADE);
  const fout = i === STEPS.length - 1 ? 1 : 1 - seg(u, i + 1 - FADE, i + 1);
  return ease(Math.min(fin, fout));
}

// Pencere ekrana sığmıyorsa (kısa ekran) yalnızca görsel olarak küçült — transform, düzen değişmez.
function useFitHeight(ref) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const fit = () => {
      const avail = window.innerHeight - 64 - 40;
      const h = el.offsetHeight;
      el.style.transform = h > avail ? `scale(${avail / h})` : "";
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    window.addEventListener("resize", fit);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", fit);
    };
  });
}

function Pinned({ demo }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const [u, setU] = useState(null); // null = dinlenme hali: tüm adımlar tam renk, son kare
  const win = useRef(null);
  const drift = useRef(null);
  useFitHeight(win);
  useScrub(
    ref,
    (engine, el) =>
      scrub(engine, {
        trigger: el,
        start: "top bottom",
        end: "bottom bottom",
        render: (p, st, rest) => {
          if (rest) {
            if (drift.current) drift.current.style.transform = "";
            return setU(null);
          }
          // Aralık kap ekrana girdiğinde başlar; sabitlenme (top = 0) bir ekran sonra.
          const total = st.end - st.start;
          const vh = window.innerHeight;
          const sp = clamp01((p * total - vh) / Math.max(1, total - vh));
          setU(Math.round(sp * STEPS.length * 100) / 100);
          // İnce parallax: pencere sabit bölüm içinde metinden biraz farklı hızda kayar.
          if (drift.current) drift.current.style.transform = `translate3d(0, ${(0.5 - sp) * 40}px, 0)`;
        },
      }),
    [demo]
  );
  const active = u == null ? -1 : Math.min(STEPS.length - 1, Math.floor(u));
  return (
    <div ref={ref} className="relative" style={{ height: `${100 + STEPS.length * STEP_VH}vh` }}>
      <div className="sticky top-0 flex h-screen items-center">
        <div className="mx-auto grid w-full max-w-[1360px] grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] items-center gap-16 px-10 pt-16">
          <ol className="relative pl-10">
            <span className="absolute inset-y-0 left-0 w-px bg-ink-600" aria-hidden="true" />
            <span
              className="absolute inset-y-0 left-0 w-px origin-top bg-signal"
              style={{ transform: `scaleY(${u == null ? 1 : u / STEPS.length})` }}
              aria-hidden="true"
            />
            {STEPS.map((n, i) => (
              <li key={n} className="lx-step py-[clamp(0.6rem,1.8vh,1.25rem)]" data-active={active === -1 || active === i} aria-current={active === i ? "step" : undefined}>
                <StepText n={n} t={t} pinned />
              </li>
            ))}
          </ol>
          {demo ? (
            <div ref={drift}>
              <div ref={win}>
                <AppWindow>
                  <div className="grid">
                    {SCENES.map((Scene, i) => {
                      const vis = u == null ? (i === STEPS.length - 1 ? 1 : 0) : visibility(u, i);
                      const lp = u == null ? 1 : clamp01((u - i) / HOLD);
                      return (
                        <div
                          key={i}
                          className="self-start"
                          style={{
                            gridArea: "1 / 1",
                            opacity: vis,
                            visibility: vis === 0 ? "hidden" : undefined,
                            transform: vis === 1 ? undefined : `scale(${0.96 + 0.04 * vis})`,
                          }}
                          aria-hidden={vis < 0.5}
                          aria-label={t("land.window", { n: i + 1, title: t(`land.step${i + 1}.title`) })}
                          role="group"
                        >
                          <Scene data={demo} p={lp} />
                        </div>
                      );
                    })}
                  </div>
                </AppWindow>
              </div>
            </div>
          ) : demo === null ? (
            <div className="skeleton h-[560px] w-full rounded-2xl" aria-hidden="true" />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function StackedScene({ index, demo }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const [p, setP] = useState(1);
  useScrub(
    ref,
    (engine, el) =>
      scrub(engine, {
        trigger: el,
        start: "top bottom",
        end: "center 45%",
        render: (q) => setP(Math.round(q * 200) / 200),
      }),
    [demo]
  );
  const Scene = SCENES[index];
  return (
    <div ref={ref} className="mt-10" role="group" aria-label={t("land.window", { n: index + 1, title: t(`land.step${index + 1}.title`) })}>
      <AppWindow>
        <Scene data={demo} p={p} />
      </AppWindow>
    </div>
  );
}

function Stacked({ demo }) {
  const { t } = useI18n();
  return (
    <ol className="mx-auto mt-16 max-w-[760px] space-y-24 px-5 sm:px-8">
      {STEPS.map((n, i) => (
        <li key={n} className="lx-step" data-active="true">
          <StepText n={n} t={t} />
          {demo ? <StackedScene index={i} demo={demo} /> : demo === null ? <div className="skeleton mt-10 h-[360px] w-full rounded-2xl" aria-hidden="true" /> : null}
        </li>
      ))}
    </ol>
  );
}

export default function Walkthrough({ demo }) {
  const { t } = useI18n();
  const desktop = useMedia(DESKTOP_MQ);
  const pinned = desktop && !prefersReducedMotion();
  return (
    <section id="how-it-works" tabIndex={-1} className="scroll-mt-16 pt-28 outline-none lg:pt-40" aria-labelledby="how-title">
      <div className="mx-auto max-w-[1360px] px-5 sm:px-8 lg:px-10">
        <Lines id="how-title" lines={[t("land.how.title")]} className="lx-h2 text-slate-100" />
      </div>
      {pinned ? <Pinned demo={demo} /> : <Stacked demo={demo} />}
      {!pinned && <div className="h-28 lg:h-40" />}
    </section>
  );
}
