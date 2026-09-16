// Tarama animasyonu — "haberler akıyor → analiz ediliyor → sonuç çıkıyor".
// Tamamen CSS (keyframe'ler index.css'te); soyut/geometrik, sakin, premium.
// prefers-reduced-motion'da otomatik olarak belirli ilerleme çubuğuna döner.
import React from "react";

const SIG = { green: "#0F8A4C", red: "#C62828", gray: "#7A7770" };

// Parçacık düzenleri (deterministik — rastgele yok). Soldan merkeze haber akışı,
// merkezden sağa renkli sonuç noktaları.
const CFG = {
  desktop: {
    w: 280, h: 64, core: 130, newsDist: 110, resStart: 152, resDist: 116,
    news: [
      { top: 15, w: 18, dur: 2.4, delay: 0, op: 0.5 },
      { top: 30, w: 13, dur: 2.9, delay: 0.7, op: 0.35 },
      { top: 45, w: 20, dur: 2.2, delay: 1.2, op: 0.45 },
      { top: 23, w: 11, dur: 2.7, delay: 1.7, op: 0.3 },
      { top: 38, w: 16, dur: 3.1, delay: 0.4, op: 0.4 },
    ],
    results: [
      { top: 20, dur: 2.3, delay: 0.5, c: SIG.green },
      { top: 34, dur: 2.7, delay: 1.1, c: SIG.red },
      { top: 45, dur: 2.0, delay: 1.6, c: SIG.gray },
      { top: 26, dur: 2.5, delay: 0.9, c: SIG.green },
    ],
  },
  mobile: {
    w: 150, h: 56, core: 66, newsDist: 52, resStart: 84, resDist: 58,
    news: [
      { top: 13, w: 12, dur: 2.4, delay: 0, op: 0.5 },
      { top: 26, w: 10, dur: 2.9, delay: 0.8, op: 0.35 },
      { top: 39, w: 14, dur: 2.2, delay: 1.3, op: 0.4 },
    ],
    results: [
      { top: 17, dur: 2.3, delay: 0.6, c: SIG.green },
      { top: 33, dur: 2.6, delay: 1.2, c: SIG.red },
      { top: 40, dur: 2.0, delay: 1.5, c: SIG.gray },
    ],
  },
};

export default function ScanStrip({ progress = 0, isMobile = false, fading = false }) {
  const c = isMobile ? CFG.mobile : CFG.desktop;
  const p = Math.min(1, Math.max(0, progress));
  const speed = 1 - 0.4 * p; // ilerledikçe akış hızlanır (hoş detay)
  return (
    <>
      <div
        className={`nr-scan ${fading ? "nr-scan--fade" : ""}`}
        style={{ width: c.w, height: c.h }}
        aria-hidden="true"
      >
        {c.news.map((n, i) => (
          <span
            key={`n${i}`}
            className="nr-scan__p nr-news"
            style={{
              left: 6, top: n.top, width: n.w,
              "--dist": `${c.newsDist}px`, "--op": n.op,
              animationDuration: `${(n.dur * speed).toFixed(2)}s`,
              animationDelay: `${n.delay}s`,
            }}
          />
        ))}
        <span className="nr-core" style={{ left: c.core }} />
        {c.results.map((r, i) => (
          <span
            key={`r${i}`}
            className="nr-scan__p nr-result"
            style={{
              left: c.resStart, top: r.top, background: r.c,
              "--dist": `${c.resDist}px`, "--op": 0.8,
              animationDuration: `${(r.dur * speed).toFixed(2)}s`,
              animationDelay: `${r.delay}s`,
            }}
          />
        ))}
      </div>

      {/* reduced-motion: belirli ilerleme çubuğu */}
      <div className="nr-scan-bar w-full max-w-[280px]">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-600">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-500"
            style={{ width: `${Math.round(p * 100)}%` }}
          />
        </div>
      </div>
    </>
  );
}
