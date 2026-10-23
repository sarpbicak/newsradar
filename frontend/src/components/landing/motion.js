// Landing hareket sistemi — TEK kaynak: eğri, süreler, scrub yumuşatması.
// CSS tarafı da buradan beslenir: Landing kökü motionVars'ı satır içi CSS değişkeni olarak
// koyar (--lx-ease, --lx-dur-*); index.css'teki .lx-* sınıfları yalnızca bunları okur.
// GSAP tarafı aynı eğriyi fonksiyon olarak kullanır (ease), böylece iki dünya aynı hissi verir.

export const EASE_POINTS = [0.22, 1, 0.36, 1];
export const EASE_CSS = `cubic-bezier(${EASE_POINTS.join(", ")})`;

export const DUR = {
  intro: 0.7,        // hero açılışı: satır başına süre (s)
  introStagger: 0.08, // satırlar arası gecikme (s)
  hover: 0.2,        // buton/link geçişleri (s)
  state: 0.3,        // aktif adım rengi gibi durum geçişleri (s)
  scrub: 0.6,        // kaydırmaya bağlı animasyonların yumuşatması (s) — "scrub: 0.6"
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
  "--lx-ease": EASE_CSS,
  "--lx-dur-intro": `${DUR.intro}s`,
  "--lx-stagger": `${DUR.introStagger}s`,
  "--lx-dur-hover": `${DUR.hover}s`,
  "--lx-dur-state": `${DUR.state}s`,
  "--lx-at-sub": `${INTRO_AT.sub}s`,
  "--lx-at-cta": `${INTRO_AT.cta}s`,
  "--lx-at-card": `${INTRO_AT.card}s`,
};

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Ortak yardımcılar: p'nin [a, b] aralığındaki yerel ilerlemesi (0..1).
export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const seg = (p, a, b) => clamp01((p - a) / (b - a));
