// Landing kaydırma motoru: Lenis (ataletli kaydırma, yalnızca masaüstü) + GSAP ScrollTrigger
// (kaydırmaya bağlı/scrub animasyonlar). İkisi de YALNIZCA landing'de ve ilk boyamadan SONRA
// dinamik import ile yüklenir (ayrı paketler; /app'e girmez, ilk yüklemeyi büyütmez).
//
// İlke: her animasyon kaydırma ilerlemesinin saf bir fonksiyonudur — aşağı kaydırınca ileri,
// yukarı kaydırınca geri sarar. "Scrub" yumuşatması tek ortak eğriyle (motion.ease) yapılır.
// Varsayılan DOM hali = SON hal: motor yüklenmeden, yüklenemezse ya da prefers-reduced-motion
// açıkken sayfa statik ve eksiksiz görünür. Tetik aralığının tamamen altında (ekran dışında)
// kalan öğeler de son halde bekletilir; ekrana girdikleri an başlangıç karesine geçerler.
import { createContext, useContext, useEffect, useLayoutEffect, useState } from "react";
import { DUR, INTRO_AT, ease, prefersReducedMotion, seg } from "../../motion.js";

export const DESKTOP_MQ = "(min-width: 1024px)";
const LENIS_MQ = "(min-width: 1024px) and (pointer: fine)";

export const EngineContext = createContext(null);

async function startEngine(root) {
  if (prefersReducedMotion()) return null;
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([import("gsap"), import("gsap/ScrollTrigger")]);
  gsap.registerPlugin(ScrollTrigger);
  let lenis = null;
  let tick = null;
  if (window.matchMedia(LENIS_MQ).matches) {
    const { default: Lenis } = await import("lenis");
    lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    tick = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
  }
  // İçerik yüksekliği değişince (veri geldi, font yüklendi) tetik noktaları yeniden hesaplanır.
  // Pencere yeniden boyutlanınca ScrollTrigger zaten kendisi yeniler.
  let timer;
  const ro = new ResizeObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(() => ScrollTrigger.refresh(), 150);
  });
  if (root) ro.observe(root);
  return {
    gsap,
    ScrollTrigger,
    lenis,
    stop() {
      ro.disconnect();
      clearTimeout(timer);
      if (tick) gsap.ticker.remove(tick);
      lenis?.destroy();
      ScrollTrigger.getAll().forEach((st) => st.kill());
      gsap.ticker.lagSmoothing(500, 33);
    },
  };
}

// Landing kökünde: motoru hero açılışından SONRA yükler — sayfa yüklendikten ~1.6 s sonra boşta,
// ya da kullanıcı daha önce kaydırmaya/tuşa başlarsa hemen. Böylece GSAP/Lenis indirmesi ilk
// boyama ve en büyük içerik (hero başlığı) ile yarışmaz. Ayrılırken (ör. /app) tamamen söker.
const AFTER_INTRO_MS = (INTRO_AT.card + DUR.intro) * 1000 + 400;
const EARLY = ["wheel", "touchstart", "keydown", "scroll"];

export function useEngineLoader(rootRef) {
  const [engine, setEngine] = useState(null);
  useEffect(() => {
    let alive = true;
    let started = false;
    let eng = null;
    let timer = null;
    let idleId = null;
    const go = () => {
      if (started) return;
      started = true;
      EARLY.forEach((type) => window.removeEventListener(type, go));
      startEngine(rootRef.current)
        .then((e) => {
          if (!alive) return e?.stop();
          eng = e;
          setEngine(e);
        })
        .catch(() => {}); // yüklenemezse sayfa statik son halde kalır
    };
    const schedule = () => {
      timer = setTimeout(() => {
        idleId = "requestIdleCallback" in window ? requestIdleCallback(go, { timeout: 1000 }) : setTimeout(go, 0);
      }, AFTER_INTRO_MS);
    };
    EARLY.forEach((type) => window.addEventListener(type, go, { passive: true, once: true }));
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      alive = false;
      clearTimeout(timer);
      if (idleId != null && "cancelIdleCallback" in window) cancelIdleCallback(idleId);
      window.removeEventListener("load", schedule);
      EARLY.forEach((type) => window.removeEventListener(type, go));
      eng?.stop();
    };
  }, [rootRef]);
  return engine;
}

export function useMedia(query) {
  const [match, setMatch] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

// Bir kaydırma aralığını render(p)'ye bağlar (p: 0..1, yumuşatılmış).
//  rest: motor yokken / ekran dışındayken / sökülünce çizilecek hal (varsayılan 1 = son hal)
//  restOffscreen: aralığın başından önce (öğe henüz ekrana girmemişken) rest'te beklet
export function scrub(engine, { trigger, start = "top bottom", end = "top 70%", endTrigger, render, rest = 1, restOffscreen = true, smooth = DUR.scrub }) {
  const { gsap, ScrollTrigger } = engine;
  const state = { p: 0 };
  let tween = null;
  const offscreen = (st) => restOffscreen && st.progress === 0 && !st.isActive;
  const paint = (st) => (offscreen(st) ? render(rest, st, true) : render(state.p, st, false));
  const st = ScrollTrigger.create({
    trigger,
    start,
    end,
    endTrigger,
    onUpdate: (self) => {
      tween?.kill();
      tween = gsap.to(state, {
        p: self.progress,
        duration: smooth,
        ease,
        onUpdate: () => render(state.p, self, false),
        onComplete: () => offscreen(self) && render(rest, self, true),
      });
    },
    onRefresh: (self) => {
      tween?.kill();
      state.p = self.progress;
      paint(self);
    },
  });
  state.p = st.progress;
  paint(st);
  return () => {
    tween?.kill();
    st.kill();
    render(rest, st, true);
  };
}

// Bileşen içinde scrub kurulumu: motor hazır olunca factory(engine, el) çalışır; temizlik döner.
export function useScrub(ref, factory, deps = []) {
  const engine = useContext(EngineContext);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!engine || !el) return undefined;
    const cleanup = factory(engine, el);
    return () => (Array.isArray(cleanup) ? cleanup.forEach((c) => c?.()) : cleanup?.());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine, ...deps]);
  return engine;
}

// data-seg="a,b" + data-fx taşıyan öğeleri p'ye göre boyar — yalnızca transform/opacity.
//  rise: belirip 20px yukarı kayar · fade: yalnızca opaklık · mask: maskeli satır aşağıdan çıkar
//  line / linev: bağlantı çizgisi yatay / dikey çizilir
export function paintSegs(nodes, p) {
  for (const el of nodes) {
    if (!el._seg) el._seg = el.dataset.seg.split(",").map(Number);
    const e = ease(seg(p, el._seg[0], el._seg[1]));
    switch (el.dataset.fx) {
      case "mask":
        el.style.transform = e === 1 ? "" : `translate3d(0, ${(1 - e) * 110}%, 0)`;
        break;
      case "line":
        el.style.transform = `scaleX(${e})`;
        break;
      case "linev":
        el.style.transform = `scaleY(${e})`;
        break;
      case "fade":
        el.style.opacity = e;
        break;
      default: // rise
        el.style.opacity = e;
        el.style.transform = e === 1 ? "" : `translate3d(0, ${(1 - e) * 20}px, 0)`;
    }
  }
}

// Bölüm içi bağlantı (#id): Lenis varsa onunla, yoksa yerel kaydırma; sabit header hesaba katılır
// (yerel kaydırmada scroll-margin-top). Klavye kullanıcıları için odak hedefe taşınır.
export function scrollToId(engine, id) {
  const el = document.getElementById(id);
  if (!el) return;
  const header = document.querySelector("[data-nav-bar]")?.offsetHeight || 0;
  if (engine?.lenis) engine.lenis.scrollTo(el, { offset: -header });
  else el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  window.history.replaceState(null, "", `#${id}`);
  el.focus({ preventScroll: true });
}
