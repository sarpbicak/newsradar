// Landing kaydırma motoru: Lenis (ataletli kaydırma, yalnızca masaüstü) + GSAP ScrollTrigger
// (kaydırmaya bağlı/scrub animasyonlar). İkisi de YALNIZCA landing'de ve ilk boyamadan SONRA
// dinamik import ile yüklenir (ayrı paketler; /app'e girmez, ilk yüklemeyi büyütmez).
//
// İlke: her animasyon kaydırma ilerlemesinin saf bir fonksiyonudur — aşağı kaydırınca ileri,
// yukarı kaydırınca geri sarar. "Scrub" yumuşatması tek ortak eğriyle (motion.ease) yapılır.
// Varsayılan DOM hali = SON hal: motor yüklenmeden, yüklenemezse ya da prefers-reduced-motion
// açıkken sayfa statik ve eksiksiz görünür. Tetik aralığının tamamen altında (ekran dışında)
// kalan öğeler de son halde bekletilir; ekrana girdikleri an başlangıç karesine geçerler.
//
// Dokunmatik / dar ekran (Lenis yok, yerel kaydırma): belirme animasyonları TEK YÖNLÜ — her öğe
// bir kez belirir ve kalır (geri kaydırınca sönmez). iOS Safari'nin adres çubuğu açılıp
// kapanınca yükseklik değişir; bu yenileme sayılmaz, yalnızca genişlik değişince (döndürme)
// tetik noktaları yeniden hesaplanır. Çubuk küçülünce görünen alan tetik noktasının altına
// uzar; öğe son halden başlangıç karesine bu yüzden adres çubuğu payı (BAR) kadar ÖNCE, hâlâ
// en büyük viewport'un da altındayken geçer — ekranda görünürken asla.
import { createContext, useContext, useEffect, useLayoutEffect, useState } from "react";
import { DUR, INTRO_AT, clamp01, ease, prefersReducedMotion, seg } from "../../motion.js";

export const DESKTOP_MQ = "(min-width: 1024px)";
const LENIS_MQ = "(min-width: 1024px) and (pointer: fine)"; // dışı: dokunmatik / dar ekran
const MIN_BAR = 120; // px; adres çubuğu payının alt sınırı (ölçülemezse de yeter)

// Adres çubuğu payı: en büyük ile en küçük viewport farkı (100lvh − 100svh).
function addressBar() {
  if (!window.CSS?.supports?.("height", "1lvh")) return MIN_BAR;
  const probe = document.createElement("div");
  probe.style.cssText = "position:fixed;top:0;width:0;visibility:hidden;height:calc(100lvh - 100svh)";
  document.body.appendChild(probe);
  const h = probe.offsetHeight;
  probe.remove();
  return Math.max(MIN_BAR, h);
}

export const EngineContext = createContext(null);

async function startEngine(root) {
  if (prefersReducedMotion()) return null;
  const [{ gsap }, { ScrollTrigger }] = await Promise.all([import("gsap"), import("gsap/ScrollTrigger")]);
  gsap.registerPlugin(ScrollTrigger);
  const touch = !window.matchMedia(LENIS_MQ).matches;
  let lenis = null;
  let tick = null;
  let width = window.innerWidth;
  const onResize = () => {
    if (window.innerWidth === width) return; // adres çubuğu: yalnızca yükseklik değişti
    width = window.innerWidth;
    ScrollTrigger.refresh();
  };
  if (touch) {
    ScrollTrigger.config({ ignoreMobileResize: true, autoRefreshEvents: "visibilitychange,DOMContentLoaded,load" });
    window.addEventListener("resize", onResize);
  } else {
    const { default: Lenis } = await import("lenis");
    lenis = new Lenis({ lerp: 0.09 });
    lenis.on("scroll", ScrollTrigger.update);
    tick = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
  }
  // İçerik yüksekliği değişince (veri geldi, font yüklendi) tetik noktaları yeniden hesaplanır.
  // Masaüstünde pencere yeniden boyutlanınca ScrollTrigger zaten kendisi yeniler.
  let timer;
  let height = root?.offsetHeight;
  const ro = new ResizeObserver(() => {
    if (root.offsetHeight === height) return;
    height = root.offsetHeight;
    clearTimeout(timer);
    timer = setTimeout(() => ScrollTrigger.refresh(), 150);
  });
  if (root) ro.observe(root);
  return {
    gsap,
    ScrollTrigger,
    lenis,
    touch,
    bar: touch ? addressBar() : 0,
    stop() {
      ro.disconnect();
      clearTimeout(timer);
      window.removeEventListener("resize", onResize);
      if (touch) ScrollTrigger.config({ autoRefreshEvents: "visibilitychange,DOMContentLoaded,load,resize" });
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
//  once: dokunmatikte tek yönlü belirme (varsayılan: son hali 1 olan belirmeler); çift yönlü
//        olması gerekenler (hero çıkışı, yatay kayma, adım adım anlatım) false verir
export function scrub(engine, { trigger, start = "top bottom", end = "top 70%", endTrigger, render, rest = 1, restOffscreen = true, smooth = DUR.scrub, once = rest === 1 }) {
  const { gsap, ScrollTrigger, touch } = engine;
  const oneShot = touch && once;
  // Dokunmatikte aralık BAR kadar erken başlar; ilk BAR px başlangıç karesidir (ekran dışı).
  const band = touch && restOffscreen && start.endsWith("bottom") ? engine.bar : 0;
  const state = { p: 0 };
  let tween = null;
  let goal = 0; // tek yönlüde ulaşılan en yüksek ilerleme
  const range = band ? (self) => ({ start: self.start + band, end: self.end }) : (self) => self; // render'a asıl aralık
  const prog = (self) => (band ? clamp01((self.progress * (self.end - self.start) - band) / Math.max(1, self.end - self.start - band)) : self.progress);
  const offscreen = (st) => restOffscreen && st.progress === 0 && !st.isActive && !(oneShot && goal > 0);
  const paint = (st) => (offscreen(st) ? render(rest, range(st), true) : render(state.p, range(st), false));
  const drive = (self, to) => {
    tween?.kill();
    tween = gsap.to(state, {
      p: to,
      duration: smooth,
      ease,
      onUpdate: () => render(state.p, range(self), false),
      onComplete: () => offscreen(self) && render(rest, range(self), true),
    });
  };
  const st = ScrollTrigger.create({
    trigger,
    start: band ? `${start}+=${band}` : start,
    end,
    endTrigger,
    onUpdate: (self) => {
      if (!oneShot) return drive(self, prog(self));
      if (prog(self) > goal) drive(self, (goal = prog(self)));
      else if (goal === 0 && self.isActive) paint(self); // ekran altı payı: başlangıç karesi
    },
    onRefresh: (self) => {
      if (oneShot && goal > 0) {
        if (prog(self) > goal) drive(self, (goal = prog(self)));
        return;
      }
      tween?.kill();
      state.p = prog(self);
      paint(self);
    },
  });
  // Tek yönlüde: motor yüklendiğinde ekranda ya da üstte olan öğe son halde kalır; yalnızca
  // henüz altta (görünmeyen) olanlar başlangıç karesine geçip ekrana girince belirir.
  tween?.kill();
  if (oneShot && prog(st) > 0) goal = 1;
  state.p = oneShot ? goal : prog(st);
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
