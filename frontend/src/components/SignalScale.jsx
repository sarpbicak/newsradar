// Haberler ve analistler TEK yatay skalada: 5 kademe (Çok olumsuz … Çok olumlu), iki işaret.
// Haberler = dolu daire, Analistler = içi boş eşkenar dörtgen (yalnızca renge dayanmaz); her
// işaretin etiketi kendi şeridinde, işaretin hemen yanında → etiketler hiçbir konumda çakışmaz.
// Aynı kademedeki iki işaret yan yana kayar. Kademe adları yalnızca uçlarda; işaretin kademesi
// kendi etiketinde. Detay: ~120px (SignalScale); pano kartı: tek çizgi ~32px (SignalScaleCompact).
// Analist hedefinin kaynağı (FMP, medyan/ortalama) yalnızca ipucunda ve Analistler sekmesinde.
import React from "react";
import { fmtPct, getLang, localeOf, tt } from "../i18n.jsx";
import { fmtMoney } from "../money.js";
import { analystLevel, hasHorizons, horizonName, levelColor, levelLabel, newsSignal, targetOf, targetSourceLabel } from "./ui.jsx";

const LEVELS = [-2, -1, 0, 1, 2];
const PCT = (level) => (level + 2) * 20 + 10; // kademenin ortası (%)
const SHIFT = 9; // aynı kademedeki iki işaretin yatay aralığı (px, merkezden)

const lower = (s) => s.toLocaleLowerCase(localeOf(getLang()));

// Skalanın verisi: işaretler (haber/analist), haber notu (yetersiz veri), erişilebilir özet.
function scaleModel(a, entity, horizon) {
  const news = newsSignal(a, entity.evidence_strength, horizon);
  const withHz = hasHorizons(a);
  const newsName = withHz ? tt("scale.newsH", { h: horizonName(horizon) }) : tt("scale.news");
  // Karışık: ortada ama hiçbir kademe "seçili" değil; yetersiz veri: işaret yok, not var.
  const newsLevel = news.level ?? (news.mixed ? 0 : null);
  const an = entity.type === "ticker" ? analystLevel(entity.analyst) : null;
  const markers = [];
  if (newsLevel != null) markers.push({ key: "news", level: newsLevel, name: newsName, value: news.label });
  if (an) markers.push({ key: "an", level: an.level, name: tt("scale.analysts", { n: entity.analyst.total }), value: an.label });
  const same = markers.length === 2 && markers[0].level === markers[1].level;
  markers.forEach((m) => { m.offset = same ? (m.key === "news" ? -SHIFT : SHIFT) : 0; });
  const noNews = newsLevel == null;
  const parts = {
    news: noNews ? null : lower(news.label),
    an: an ? lower(an.label) : null,
  };
  const aria = parts.news && parts.an
    ? tt("scale.ariaBoth", { news: parts.news, an: parts.an })
    : parts.news
      ? tt("scale.ariaNews", { news: parts.news })
      : parts.an
        ? tt("scale.ariaNoNews", { an: parts.an })
        : tt("scale.ariaNone");
  return { markers, noNews, newsName, aria, activeLevels: new Set(markers.map((m) => m.level)) };
}

function Shape({ kind, size = 12 }) {
  return kind === "news" ? (
    <span className="block shrink-0 rounded-full bg-slate-100 ring-2 ring-ink-900" style={{ width: size, height: size }} aria-hidden="true" />
  ) : (
    <span className="block shrink-0 rotate-45 border-2 border-accent bg-ink-900" style={{ width: size - 2, height: size - 2 }} aria-hidden="true" />
  );
}

// 5 kademe: ince aralıklar kademe çizgisi işlevi görür; işaretli kademe tam, diğerleri soluk
// (koyu temada da görünür).
function Track({ active, height = "h-2" }) {
  return (
    <div className={`flex ${height} gap-[2px]`} aria-hidden="true">
      {LEVELS.map((lvl) => (
        <span
          key={lvl}
          className="flex-1 first:rounded-l-[2px] last:rounded-r-[2px]"
          style={{ background: levelColor(lvl), opacity: active.has(lvl) ? 0.95 : 0.4 }}
        />
      ))}
    </div>
  );
}

const pos = (m) => `calc(${PCT(m.level)}% + ${m.offset}px)`;

export function SignalScale({ a, entity, horizon }) {
  const { markers, noNews, newsName, aria, activeLevels } = scaleModel(a, entity, horizon);
  const target = targetOf(entity.analyst);
  const up = entity.analyst?.upside_percent;
  const money = target != null ? fmtMoney(target, entity.currency || "USD", getLang(), { digits: 0 }) : null;
  return (
    <section className="rounded-card px-4 py-3 ring-1 ring-inset ring-ink-600 sm:px-5" aria-label={tt("scale.section")}>
      <div role="img" aria-label={aria}>
        {/* Şeritler: her işaretin etiketi kendi satırında; sağ yarıda etiket işaretin soluna geçer. */}
        <div className="space-y-0.5" aria-hidden="true">
          {markers.map((m) => {
            const right = PCT(m.level) > 50;
            return (
              <div key={m.key} className="relative h-[18px]">
                <span
                  className={`absolute top-0 flex h-[18px] items-center gap-1.5 whitespace-nowrap text-micro ${right ? "flex-row-reverse" : ""}`}
                  style={right ? { right: `calc(${100 - PCT(m.level)}% - ${m.offset}px - 6px)` } : { left: `calc(${pos(m)} - 6px)` }}
                >
                  <Shape kind={m.key} size={10} />
                  <span>
                    <span className="font-medium text-slate-200">{m.name}</span>
                    <span className="text-slate-400"> · {m.value}</span>
                  </span>
                </span>
              </div>
            );
          })}
          {noNews && <p className="h-[18px] text-micro leading-[18px] text-slate-400">{tt("scale.noNews", { name: newsName })}</p>}
        </div>
        <div className="relative mt-1 py-[3px]">
          <Track active={activeLevels} />
          {markers.map((m) => (
            <span key={m.key} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: pos(m) }}>
              <Shape kind={m.key} />
            </span>
          ))}
        </div>
        <div className="mt-0.5 flex justify-between text-micro text-slate-500" aria-hidden="true">
          <span>{levelLabel(-2)}</span>
          <span>{levelLabel(2)}</span>
        </div>
      </div>
      {money && (
        <p className="mt-1.5 text-meta text-slate-400" title={targetSourceLabel(entity.analyst)}>
          {tt("scale.target")} <span className="font-mono font-semibold tabular-nums text-slate-100">{money}</span>
          {up != null && <span className="font-mono tabular-nums"> ({fmtPct(up)})</span>}
        </p>
      )}
    </section>
  );
}

// Pano kartı: tek çizgi, iki işaret, küçük açıklama + analist sayısı (~32px). Yalnızca analist
// verisi olan hissede (haber yönü kartın üstündeki etikette zaten var).
export function SignalScaleCompact({ a, entity, horizon }) {
  const { markers, aria, activeLevels } = scaleModel(a, entity, horizon);
  if (!markers.some((m) => m.key === "an")) return null;
  return (
    <div role="img" aria-label={aria}>
      <div className="flex items-center gap-3 text-micro text-slate-500" aria-hidden="true">
        {markers.map((m) => (
          <span key={m.key} className="inline-flex items-center gap-1.5">
            <Shape kind={m.key} size={8} />
            {m.key === "news" ? tt("scale.newsShort") : tt("scale.analystsShort")}
          </span>
        ))}
        <span className="ml-auto tabular-nums">{tt("card.analysts", { n: entity.analyst.total })}</span>
      </div>
      <div className="relative mt-1.5 py-[3px]" aria-hidden="true">
        <Track active={activeLevels} height="h-1" />
        {markers.map((m) => (
          <span key={m.key} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: pos(m) }}>
            <Shape kind={m.key} size={9} />
          </span>
        ))}
      </div>
    </div>
  );
}
