// Hareket sistemi — TEK kaynak (landing + uygulama): eğri, süreler, scrub yumuşatması.
// CSS tarafı da buradan beslenir: applyMotionVars() açılışta <html>'e --ease / --dur-* değişkenlerini
// koyar (main.jsx); index.css'teki sınıflar ve Tailwind'in duration-*/ease-std sınıfları bunları okur.
// GSAP (landing) ve JS sayaçları aynı eğriyi fonksiyon olarak kullanır (ease).
// Uygulamada yalnızca mikro hareket (≤200ms geçiş, hover, modal); sinematik olan landing'de.

export const EASE_POINTS = [0.22, 1, 0.36, 1];
export const EASE_CSS = `cubic-bezier(${EASE_POINTS.join(", ")})`;

export const DUR = {
  intro: 0.7,        // landing hero açılışı: satır başına süre (s)
  introStagger: 0.08, // satırlar arası gecikme (s)
  hover: 0.2,        // buton/link/kart hover geçişleri (s)
  state: 0.3,        // aktif adım rengi gibi durum geçişleri (s)
  scrub: 0.6,        // landing: kaydırmaya bağlı animasyonların yumuşatması (s)
  page: 0.2,         // uygulama: sayfa / sekme geçişi (fade)
  modal: 0.2,        // uygulama: modal açılışı (ölçek + fade)
  count: 0.5,        // rakamlarda kısa sayma
  move: 0.3,         // liste sıralaması değişince satırların yer değiştirmesi
  shimmer: 1.4,      // iskelet parıltısı (döngü)
};

// Hero açılışında öğelerin başlama anları (s). Son öğe: 0.5 + 0.7 = 1.2 s ≤ 1.5 s.
export const INTRO_AT = { sub: 0.3, cta: 0.4, card: 0.5 };

// cubic-bezier(x1, y1, x2, y2) → t ↦ y. Newton + ikiye bölme (CSS ile aynı eğri).
export function cubicBezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const x = (t) => ((ax * t + bx) * t + cx) * t;
  const y = (t) => ((ay * t + by) * t + cy) * t;
  const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (p) => {
    if (p <= 0) return 0;
    if (p >= 1) return 1;
    let t = p;
    for (let i = 0; i < 6; i++) {
      const d = dx(t);
      if (Math.abs(d) < 1e-6) break;
      const nt = t - (x(t) - p) / d;
      if (nt < 0 || nt > 1) break;
      t = nt;
    }
    let lo = 0, hi = 1;
    for (let i = 0; i < 20 && Math.abs(x(t) - p) > 1e-5; i++) {
      if (x(t) < p) lo = t; else hi = t;
      t = (lo + hi) / 2;
    }
    return y(t);
  };
}

export const ease = cubicBezier(...EASE_POINTS);

export const motionVars = {
  "--ease": EASE_CSS,
  "--dur-intro": `${DUR.intro}s`,
  "--stagger": `${DUR.introStagger}s`,
  "--dur-hover": `${DUR.hover}s`,
  "--dur-state": `${DUR.state}s`,
  "--dur-page": `${DUR.page}s`,
  "--dur-modal": `${DUR.modal}s`,
  "--dur-move": `${DUR.move}s`,
  "--dur-shimmer": `${DUR.shimmer}s`,
  "--at-sub": `${INTRO_AT.sub}s`,
  "--at-cta": `${INTRO_AT.cta}s`,
  "--at-card": `${INTRO_AT.card}s`,
};

// Açılışta bir kez (main.jsx, ilk render'dan önce): değişkenler tüm sayfaya.
export function applyMotionVars(el = document.documentElement) {
  Object.entries(motionVars).forEach(([k, v]) => el.style.setProperty(k, v));
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Ortak yardımcılar: p'nin [a, b] aralığındaki yerel ilerlemesi (0..1).
export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const seg = (p, a, b) => clamp01((p - a) / (b - a));
