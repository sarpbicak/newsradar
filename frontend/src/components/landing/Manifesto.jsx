// Manifesto: ekranı kaplayan tek cümle. Masaüstünde bölüm sabitlenir (CSS sticky) ve kaydırdıkça
// kelimeler tek tek soluk halden tam renge geçer; geri kaydırınca yeniden soluklaşır. Mobilde
// sabitleme yok; her kelime KENDİ konumuna göre: ekranın altından girerken solgun, üstü ekranın
// %60'ına gelince tam renk, geri kaydırınca tersine. [köşeli parantez] = vurgu.
// Motor yoksa / reduced-motion: tüm kelimeler tam renkte.
import React, { useRef } from "react";
import { useI18n } from "../../i18n.jsx";
import { clamp01, prefersReducedMotion } from "../../motion.js";
import { DESKTOP_MQ, scrub, useMedia, useScrub } from "./scroll.js";

const DIM = 0.16;
// Dokunmatikte hafifletilmiş: solgun hal de büyük metin kontrastını (≥3:1, iki tema) sağlar —
// konuma bağlı geçişte ekranın hemen altındaki kelimeler de ara değerde. index.css ile aynı.
const DIM_TOUCH = 0.5;
const DIM_TOUCH_ACCENT = 0.75;

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
      if (engine.touch) {
        // Kelimenin aralığı = bölümün aralığı + kelimenin bölüm içindeki dikey konumu (offsetTop;
        // yalnızca yenilemede ölçülür). Değer yalnızca kaydırma konumundan.
        let offs = null;
        let floor = null;
        let key = null;
        return scrub(engine, {
          trigger: el,
          start: "top bottom",
          touchEnd: "bottom 60%",
          render: (p, st, rest) => {
            if (key !== st.start) [key, offs, floor] = [st.start, nodes.map((w) => w.offsetTop), nodes.map((w) => (w.classList.contains("text-accent") ? DIM_TOUCH_ACCENT : DIM_TOUCH))];
            const len = Math.max(1, st.end - st.start - el.offsetHeight);
            const y = st.start + p * (st.end - st.start);
            nodes.forEach((node, i) => {
              const o = rest ? 1 : clamp01((y - st.start - offs[i]) / len);
              node.style.opacity = o === 1 ? "" : floor[i] + (1 - floor[i]) * o;
            });
          },
        });
      }
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
    <section ref={ref} className="relative" data-rv="" style={pinned ? { height: "260vh" } : undefined}>
      <div className={pinned ? "sticky top-0 flex h-svh items-center" : "py-20 sm:py-32"}>
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
