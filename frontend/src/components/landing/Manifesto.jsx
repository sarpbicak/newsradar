// Manifesto: ekranı kaplayan tek cümle. Masaüstünde bölüm sabitlenir (CSS sticky) ve kaydırdıkça
// kelimeler tek tek soluk halden tam renge geçer; geri kaydırınca yeniden soluklaşır. Mobilde
// sabitleme yok, aynı geçiş bölümün kendi kaydırma aralığında. [köşeli parantez] = vurgu.
// Motor yoksa / reduced-motion: tüm kelimeler tam renkte.
import React, { useRef } from "react";
import { useI18n } from "../../i18n.jsx";
import { clamp01, prefersReducedMotion } from "../../motion.js";
import { DESKTOP_MQ, scrub, useMedia, useScrub } from "./scroll.js";

const DIM = 0.16;

function parse(text) {
  const out = [];
  text.split(/(\[[^\]]+\])/).forEach((part) => {
    const accent = part.startsWith("[");
    part.replace(/[[\]]/g, "").split(/\s+/).filter(Boolean).forEach((w) => out.push({ w, accent }));
  });
  return out;
}

export default function Manifesto() {
  const { t } = useI18n();
  const ref = useRef(null);
  const pinned = useMedia(DESKTOP_MQ) && !prefersReducedMotion();
  const text = t("land.manifesto");
  const words = parse(text);

  useScrub(
    ref,
    (engine, el) => {
      const nodes = [...el.querySelectorAll("[data-w]")];
      const n = nodes.length;
      return scrub(engine, {
        trigger: el,
        start: "top bottom",
        end: pinned ? "bottom bottom" : "bottom 60%",
        render: (p, st, rest) => {
          let q = 1;
          if (!rest) {
            if (pinned) {
              const total = st.end - st.start;
              const vh = window.innerHeight;
              q = clamp01((p * total - vh) / Math.max(1, total - vh));
            } else q = p;
          }
          nodes.forEach((node, i) => {
            const o = clamp01((q * (n + 2) - i) / 2);
            node.style.opacity = o === 1 ? "" : DIM + (1 - DIM) * o;
          });
        },
      });
    },
    [text, pinned]
  );

  return (
    <section ref={ref} className="relative" style={pinned ? { height: "260vh" } : undefined}>
      <div className={pinned ? "sticky top-0 flex h-svh items-center" : "py-32"}>
        <p className="lx-display lx-mega mx-auto w-full max-w-[1360px] px-5 text-slate-100 sm:px-8 lg:px-10">
          {words.map(({ w, accent }, i) => (
            <React.Fragment key={i}>
              <span data-w className={accent ? "text-accent" : undefined}>
                {w}
              </span>{" "}
            </React.Fragment>
          ))}
        </p>
      </div>
    </section>
  );
}
