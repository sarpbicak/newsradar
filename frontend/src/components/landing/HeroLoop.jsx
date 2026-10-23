// Hero'nun TEK imza animasyonu: "Nasıl çalışır?" akışı (gerçek başlıklar → AI etiketi →
// alakasızlar düşer → karar kartı) sakin, sürekli bir döngü halinde. Veri GERÇEK:
// /public/how-it-works (seed listesindeki örnek şirket; Landing bir kez çekip verir).
// Örnek yoksa uydurma yapılmaz — Landing bu bileşeni hiç göstermez.
// Performans: yalnızca opacity/transform animasyonu (CSS sınıfları, HowItWorks ile aynı);
// döngü ekran dışındayken ve sekme arka plandayken durur; alan önceden ayrılır (CLS yok).
// prefers-reduced-motion: animasyon yok, son hal (etiketli başlıklar + kart) statik.
import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n.jsx";
import { HeadlineCards, MiniCard } from "../HowItWorks.jsx";

const PHASE_MS = [2000, 2600, 4200]; // başlıklar · etiketler (+ alakasız düşer) · karar
const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function useInView(ref) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return setInView(true);
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return inView;
}

export default function HeroLoop({ data }) { // data: null = yükleniyor
  const { t } = useI18n();
  const [phase, setPhase] = useState(0);
  const [cycle, setCycle] = useState(0);
  const wrap = useRef(null);
  const inView = useInView(wrap);
  const still = reduced();

  // Faz ilerletme: yalnızca görünürken ve sekme öndeyken.
  useEffect(() => {
    if (!data || still || !inView) return undefined;
    let timer;
    const tick = () => {
      if (document.hidden) { timer = setTimeout(tick, 1000); return; }
      setPhase((p) => {
        const next = (p + 1) % PHASE_MS.length;
        if (next === 0) setCycle((c) => c + 1);
        return next;
      });
    };
    timer = setTimeout(tick, PHASE_MS[phase]);
    return () => clearTimeout(timer);
  }, [data, still, inView, phase]);

  const captions = [t("land.hero.p0"), t("land.hero.p1"), t("land.hero.p2")];
  const shown = still ? 2 : phase;

  return (
    <div
      ref={wrap}
      className="relative w-full rounded-2xl border border-ink-600 bg-ink-800/70 p-4 shadow-card sm:p-5"
      aria-label={data ? t("land.hero.live", { name: data.entity.name }) : undefined}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">
          {data ? t("land.hero.live", { name: data.entity.name }) : " "}
        </span>
        <span className="flex items-center gap-1.5" aria-hidden="true">
          {captions.map((_, i) => (
            <span key={i} className={`h-1.5 rounded-full transition-all duration-300 ${i === shown ? "w-4 bg-accent" : "w-1.5 bg-ink-500"}`} />
          ))}
        </span>
      </div>
      <p className="mb-3 text-[13px] text-slate-400" aria-live="off">{captions[shown]}</p>
      {/* Alan sabit: fazlar üst üste, yalnızca opaklık değişir (düzen kayması yok). */}
      <div className={still ? "space-y-3" : "relative h-[300px] sm:h-[290px]"}>
        {!data ? (
          <div className="space-y-2" aria-hidden="true">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-[52px] w-full" />)}
          </div>
        ) : (
          <>
            <div className={still ? "" : `absolute inset-0 transition-opacity duration-300 ${shown < 2 ? "opacity-100" : "opacity-0"}`}>
              <HeadlineCards key={`h${cycle}-${shown >= 1}`} headlines={data.headlines} withLabels={shown >= 1} t={t} />
            </div>
            <div className={still ? "" : `absolute inset-0 flex items-center transition-opacity duration-300 ${shown === 2 ? "opacity-100" : "pointer-events-none opacity-0"}`}>
              {(shown === 2 || still) && <div className="w-full"><MiniCard key={`c${cycle}`} entity={data.entity} t={t} animate={!still} /></div>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
