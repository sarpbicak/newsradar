// Landing'in kaydırmaya bağlı yapı taşları:
//  <Lines>  büyük başlık; masaüstünde satırlar maskeden aşağıdan çıkar (geri kaydırınca iner),
//           drift verilirse kaydırma boyunca yatayda hafifçe kayar. Dokunmatikte maske yok:
//           başlık <Rise> sarmalayıcısıyla gelir.
//  <Rise>   yalnızca dokunmatik: başlık sarmalayıcısı; ekranın alt kenarından girerken opaklık
//           0 → 1 ve 40px alttan yukarı, üstü yükleme viewport'unun %60'ına gelince tam (adres
//           çubuğu küçülmüşken ekranın ~%53'ü; tetikler yüklemedeki küçük viewport'la ölçülür
//           ve yükseklik değişince yenilenmez). Yalnızca transform +
//           opacity (iOS'ta maske/overflow kalkışı çubuğun arkasında bitip görünmüyordu).
//  <Reveal> paragraf/kart/rakam; belirip 20px yukarı kayar (masaüstünde geri kaydırınca geri gider).
// Dokunmatikte hepsi kaydırmaya bağlı ve çift yönlü, yalnızca konuma göre (scroll.js touchScrub).
// Başlangıç hali CSS'te (data-rv). Motor yoksa / reduced-motion: düz, son halde metin.
import React, { useRef } from "react";
import { ease } from "../../motion.js";
import { paintSegs, scrub, useScrub } from "./scroll.js";

export function Lines({ as: Tag = "h2", lines, className = "", drift = 0, end = "top 55%", ...rest }) {
  const ref = useRef(null);
  useScrub(
    ref,
    (engine, el) => {
      const masks = el.querySelectorAll("[data-fx]");
      const offs = engine.touch ? [] : [scrub(engine, { trigger: el, end, render: (p) => paintSegs(masks, p) })];
      if (drift) {
        // p = 0.5 → yerinde; aralık: başlık ekrana girdiği andan çıktığı ana kadar.
        offs.push(
          scrub(engine, {
            trigger: el,
            start: "top bottom",
            end: "bottom top",
            rest: 0.5,
            render: (p) => {
              el.style.transform = p === 0.5 ? "" : `translate3d(${(0.5 - p) * 2 * drift}%, 0, 0)`;
            },
          })
        );
      }
      return offs;
    },
    [lines.join("|"), drift, end]
  );
  return (
    <Rise>
      <Tag ref={ref} className={`lx-display ${className}`} {...rest}>
        {lines.map((line, i) => (
          <span key={i} className="lx-line">
            <span data-fx="mask" data-seg={`${i * 0.14},${i * 0.14 + 0.6}`}>{line}</span>
          </span>
        ))}
      </Tag>
    </Rise>
  );
}

const RISE = 40; // px

// Dış div tetik (hareketsiz — ScrollTrigger konumu kaymadan ölçer), iç div hareket eder.
export function Rise({ children }) {
  const ref = useRef(null);
  useScrub(ref, (engine, el) => {
    if (!engine.touch) return undefined;
    const body = el.firstElementChild;
    return scrub(engine, {
      trigger: el,
      touchEnd: "top 60%",
      touchBehind: false,
      render: (p) => {
        // Opaklık girişte daha uzun soluk (p^1.5): alt %20'de yarıdan az.
        body.style.opacity = p >= 1 ? "" : p ** 1.5;
        body.style.transform = p >= 1 ? "" : `translate3d(0, ${(1 - p) * RISE}px, 0)`;
      },
    });
  });
  return (
    <div ref={ref} data-rv="rise">
      <div data-rise-body="">{children}</div>
    </div>
  );
}

export function Reveal({ as: Tag = "div", className = "", end = "top 75%", children, ...rest }) {
  const ref = useRef(null);
  useScrub(ref, (engine, el) =>
    scrub(engine, {
      trigger: el,
      end,
      render: (p) => {
        const e = ease(p);
        el.style.opacity = e;
        el.style.transform = e === 1 ? "" : `translate3d(0, ${(1 - e) * 20}px, 0)`;
      },
    })
  );
  return (
    <Tag ref={ref} className={className} data-rv="fade" {...rest}>
      {children}
    </Tag>
  );
}
