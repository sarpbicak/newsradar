// Detay Özet sekmesinin üstündeki iki yarım daire gösterge: Haberler (seçili vadenin hükmü) ve
// Analistler (Finnhub tavsiyelerinin ağırlıklı skoru). Aynı 5 kademe: Çok olumsuz … Çok olumlu.
// İnce yay, kademeler arası boşluk, ince ibre; yalnızca etkin kademe tam renkli, diğerleri soluk.
// Degrade yok, al/sat dili yok. Yalnızca SVG (bağımlılık yok).
import React from "react";
import { fmtPct, tt } from "../i18n.jsx";
import { analystLevel, hasHorizons, horizonName, levelColor, levelLabel, newsSignal, targetOf, targetSourceLabel } from "./ui.jsx";

const W = 168;
const CX = W / 2;
const CY = 84;
const R = 72;
const SEG = 36; // derece (5 kademe × 36 = 180)
const GAP = 3;

// θ: soldan (0°) üstten sağa (180°).
const pt = (deg, r = R) => {
  const a = (deg * Math.PI) / 180;
  return [CX - r * Math.cos(a), CY - r * Math.sin(a)];
};
const arc = (from, to) => {
  const [x1, y1] = pt(from);
  const [x2, y2] = pt(to);
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
};

// angle: ibre açısı (0..180) ya da null (veri yok → ibre çizilmez). active: tam renkli kademe.
function Dial({ angle, active }) {
  return (
    <svg width={W} height={CY + 8} viewBox={`0 0 ${W} ${CY + 8}`} aria-hidden="true" className="block">
      {[-2, -1, 0, 1, 2].map((lvl, i) => (
        <path
          key={lvl}
          d={arc(i * SEG + GAP / 2, (i + 1) * SEG - GAP / 2)}
          fill="none"
          stroke={levelColor(lvl)}
          strokeOpacity={lvl === active ? 1 : 0.28}
          strokeWidth={lvl === active ? 4 : 3}
          strokeLinecap="butt"
        />
      ))}
      {angle != null && (
        <g className="text-slate-300 motion-safe:transition-transform motion-safe:duration-500" style={{ transform: `rotate(${angle}deg)`, transformOrigin: `${CX}px ${CY}px` }}>
          <line x1={CX} y1={CY} x2={CX - (R - 12)} y2={CY} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </g>
      )}
      <circle cx={CX} cy={CY} r="3" className="fill-slate-300" />
    </svg>
  );
}

function Gauge({ title, label, sub, angle, active, aria }) {
  return (
    <div role="img" aria-label={aria} className="flex min-w-0 flex-col items-center px-5 py-5 text-center">
      <div className="text-micro font-medium text-slate-500">{title}</div>
      <div className="mt-3">
        <Dial angle={angle} active={active} />
      </div>
      <div className="mt-1 text-body text-slate-100">{label}</div>
      {sub && <div className="mt-1 text-micro tabular-nums text-slate-500">{sub}</div>}
    </div>
  );
}

// Analist kademesine göre gösterge yalnızca hisse için; veri yoksa tek (Haberler) gösterge.
export default function Gauges({ a, entity, horizon }) {
  const news = newsSignal(a, entity.evidence_strength, horizon);
  const withHz = hasHorizons(a);
  const newsTitle = withHz ? `${tt("gauge.news")} · ${horizonName(horizon)}` : tt("gauge.news");
  const newsSub = withHz ? tt(horizon === "long" ? "gauge.windowLong" : "gauge.windowShort") : null;
  // Kesikli kademe: ibre kademenin ortasında. Karışık → ortada ama hiçbir kademe vurgulu değil.
  const newsAngle = news.level != null ? (news.level + 2) * SEG + SEG / 2 : news.mixed ? 90 : null;

  const an = entity.type === "ticker" ? analystLevel(entity.analyst) : null;
  const target = targetOf(entity.analyst);
  const up = entity.analyst?.upside_percent;
  const anSub = target != null
    ? `${targetSourceLabel(entity.analyst)}: $${Math.round(target)}${up != null ? ` · ${fmtPct(up)}` : ""}`
    : null;

  return (
    <section
      className={`grid divide-y divide-ink-600 rounded-card ring-1 ring-inset ring-ink-600 ${an ? "sm:grid-cols-2 sm:divide-x sm:divide-y-0" : ""}`}
      aria-label={tt("gauge.section")}
    >
      <Gauge
        title={newsTitle}
        label={news.label}
        sub={newsSub}
        angle={newsAngle}
        active={news.level}
        aria={tt("gauge.ariaNews", { title: newsTitle, v: news.label })}
      />
      {an && (
        <Gauge
          title={tt("gauge.analysts", { n: entity.analyst.total })}
          label={an.label}
          sub={anSub}
          // Sürekli skor (−2..2) → açı: eşikler (±0,4 / ±1,2) kademe sınırlarına denk gelir.
          angle={((Math.max(-2, Math.min(2, an.score)) + 2) / 4) * 180}
          active={an.level}
          aria={tt("gauge.ariaAnalysts", { n: entity.analyst.total, v: levelLabel(an.level) }) + (anSub ? `. ${anSub}` : "")}
        />
      )}
    </section>
  );
}
