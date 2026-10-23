// Landing'in kaydırmaya bağlı iki yapı taşı:
//  <Lines>  büyük başlık; satırlar maskeden aşağıdan çıkar (geri kaydırınca iner),
//           drift verilirse kaydırma boyunca yatayda hafifçe kayar.
//  <Reveal> paragraf/kart/rakam; belirip 20px yukarı kayar (geri kaydırınca geri gider).
// Motor yoksa / reduced-motion: düz, son halde metin.
import React, { useRef } from "react";
import { ease } from "./motion.js";
import { paintSegs, scrub, useScrub } from "./scroll.js";

export function Lines({ as: Tag = "h2", lines, className = "", drift = 0, end = "top 55%", ...rest }) {
  const ref = useRef(null);
  useScrub(
    ref,
    (engine, el) => {
      const masks = el.querySelectorAll("[data-fx]");
      const offs = [scrub(engine, { trigger: el, end, render: (p) => paintSegs(masks, p) })];
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
    <Tag ref={ref} className={`lx-display ${className}`} {...rest}>
      {lines.map((line, i) => (
        <span key={i} className="lx-line">
          <span data-fx="mask" data-seg={`${i * 0.14},${i * 0.14 + 0.6}`}>{line}</span>
        </span>
      ))}
    </Tag>
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
    <Tag ref={ref} className={className} {...rest}>
      {children}
    </Tag>
  );
}
