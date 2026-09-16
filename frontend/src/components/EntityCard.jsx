// KESİN SPEC kartı — 4 satır:
// 1) Durum pill (sol, büyük dolgulu) + şirket adı/ticker (sağ, tek satır)
// 2) Hüküm cümlesi (TAM, kesme yok, 3 satıra kadar sarar)
// 3) Fiyat bloğu (çerçeveli kutu: şimdi → analist hedefi + %)
// 4) Meta (küçük soluk: vade · N haber · yön değişti)
// Tüm kartlar aynı yükseklik (h-full + flex; fiyat+meta alta yapışır).
import React from "react";
import { ArrowRight, Lock } from "lucide-react";
import { SignalPill, overallSignal, AnimatedNumber, horizonLabel } from "./ui.jsx";
import { tt } from "../i18n.jsx";

// Kompakt analist barı — al/tut/sat segmentleri + baskın görüş + analist sayısı.
const ANALYST_SEG = [
  { key: "strong_buy", color: "#0B7A42" },
  { key: "buy", color: "#0F8A4C" },
  { key: "hold", color: "#A8A49B" },
  { key: "sell", color: "#C62828" },
  { key: "strong_sell", color: "#A81E1E" },
];
function analystLean(a) {
  const buyish = a.strong_buy + a.buy;
  const sellish = a.sell + a.strong_sell;
  if (buyish > a.hold && buyish >= sellish) return { text: tt("card.buyLean"), color: "#0F8A4C" };
  if (sellish > a.hold && sellish > buyish) return { text: tt("card.sellLean"), color: "#C62828" };
  return { text: tt("card.holdLean"), color: "#7A7770" };
}
function AnalystMiniBar({ a }) {
  const total = a.total || 1;
  const lean = analystLean(a);
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="whitespace-nowrap font-medium" style={{ color: lean.color }}>{lean.text}</span>
      <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700">
        {ANALYST_SEG.map((s) => {
          const n = a[s.key] || 0;
          if (!n) return null;
          return <div key={s.key} style={{ width: `${(n / total) * 100}%`, background: s.color }} />;
        })}
      </div>
      <span className="whitespace-nowrap text-slate-500">{tt("card.analysts", { n: a.total })}</span>
    </div>
  );
}

// Özel (borsada işlem görmeyen) şirket bilgi kutusu — fiyat bloğunun yerini alır.
const PRIVATE_SHELL = "rounded-lg border border-ink-600 bg-ink-900/40 px-3 py-2.5";
function PrivateCompanyBox() {
  return (
    <div className={PRIVATE_SHELL}>
      <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-300">
        <Lock className="h-3.5 w-3.5 text-slate-500" />
        {tt("card.private")}
      </div>
      <div className="mt-1 text-[11px] leading-snug text-slate-500">
        {tt("card.privateBody")}
      </div>
    </div>
  );
}

// Özel şirket kartında analist barının yerini alır: en önemli tek etken.
function TopDriverLine({ text }) {
  return (
    <div className="flex items-baseline gap-1.5 text-[11px]">
      <span className="shrink-0 font-medium text-slate-500">{tt("card.topDriver")}</span>
      <span className="min-w-0 flex-1 truncate text-slate-400">{text}</span>
    </div>
  );
}

// MOBİL tek satır fiyat: "$338.19 −%0.2 → hedef $338" (detay için karta dokun).
function CompactPriceLine({ card }) {
  const price = card.price;
  const chg = card.change_percent;
  const target = card.analyst?.target_mean;
  if (price == null) {
    return <div className="text-[13px] text-slate-500">{tt("card.noPrice")} · {tt("card.newsOnly")}</div>;
  }
  return (
    <div className="flex flex-wrap items-baseline gap-x-1.5 font-mono text-[13px] tabular-nums text-slate-300">
      <span className="font-semibold text-slate-100">${price.toFixed(2)}</span>
      {chg != null && (
        <span className={chg >= 0 ? "text-emerald-400" : "text-rose-400"}>
          {chg >= 0 ? "+" : "−"}%{Math.abs(chg).toFixed(1)}
        </span>
      )}
      {target != null && (
        <span className="text-slate-500">
          → {tt("detail.target")} <span className="font-semibold text-slate-300">${target.toFixed(0)}</span>
        </span>
      )}
    </div>
  );
}

// MOBİL özel şirket tek satırı — fiyat kutusunun yerine kısa not.
function CompactPrivateLine({ drivers }) {
  return (
    <div className="text-[13px] text-slate-500">
      {tt("card.privateShort")}
      {drivers?.[0] && (
        <span className="mt-0.5 block truncate text-slate-400">{tt("card.topDriver")} {drivers[0]}</span>
      )}
    </div>
  );
}

function PriceBox({ card }) {
  const price = card.price;
  const target = card.analyst?.target_mean;
  const upside = card.analyst?.upside_percent;

  // Ortak kutu kabuğu — tüm kartlarda aynı yükseklik.
  const shell = "rounded-lg border border-ink-600 bg-ink-900/40 px-3 py-2.5";

  // Ticker ama fiyat yok: aynı kutu, ortalanmış açıklama.
  if (price == null) {
    return (
      <div className={`${shell} text-center`}>
        <div className="text-sm text-slate-400">{tt("card.noPrice")}</div>
        <div className="mt-0.5 text-[10px] text-slate-500">{tt("card.newsOnly")}</div>
      </div>
    );
  }

  return (
    <div className={shell}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1 text-center">
          <div className="font-mono text-base font-semibold tabular-nums text-slate-100">
            <AnimatedNumber value={price} decimals={2} prefix="$" />
          </div>
          <div className="text-[10px] text-slate-500">{tt("card.now")}</div>
        </div>
        <ArrowRight className="h-4 w-4 shrink-0 text-slate-500" />
        <div className="min-w-0 flex-1 text-center">
          <div className="font-mono text-base font-semibold tabular-nums text-slate-100">
            {target != null ? (
              <>
                ${target.toFixed(0)}
                {upside != null && (
                  <span className={`ml-1 ${upside >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {upside >= 0 ? "+" : "−"}%{Math.abs(Math.round(upside))}
                  </span>
                )}
              </>
            ) : (
              <span className="text-slate-500">—</span>
            )}
          </div>
          <div className="text-[10px] text-slate-500">
            {target != null ? tt("card.analystTarget") : tt("card.noTarget")}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function EntityCard({ card, onOpen, big = false }) {
  const a = card.analysis;
  // Sol şerit rengi: analiz varsa duruma göre (5 durum + nötr gri); YOKSA açık gri.
  // ASLA koyu/siyah — eski #3A4152 fallback'i kağıt temada siyah görünüyordu.
  const stripColor = a ? overallSignal(a.stance, card.evidence_strength).color : "#D8D3C7";
  const changed = a && card.delta?.stance_changed;

  function open() {
    onOpen(card.id);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
      className={`group relative flex h-full cursor-pointer flex-col gap-3 overflow-hidden rounded-xl border bg-ink-800 text-left shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 md:gap-4 ${
        big ? "border-ink-500 p-4 pl-5 md:p-6 md:pl-7" : "border-ink-600 p-4 pl-5 hover:border-accent/60 md:p-5 md:pl-6"
      }`}
    >
      {/* Sol kenar durum şeridi (pill rengiyle aynı; Katman 1'de daha kalın) */}
      <span className={`absolute inset-y-0 left-0 ${big ? "w-2" : "w-1.5"}`} style={{ background: stripColor }} />

      {/* Satır 1 — Durum pill (sol) + ad/ticker (sağ, tek satır) */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {a ? (
            <SignalPill stance={a.stance} evidence={card.evidence_strength} />
          ) : (
            <span className="inline-flex items-center rounded-full bg-ink-700 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
              {tt("card.noAnalysis")}
            </span>
          )}
          {/* Katman 1 nedeni — neden "bugün önemli" (mobilde gizli: sadeleştirme) */}
          {big && card.priority_reason && (
            <span className="hidden items-center rounded-full bg-accent/15 px-2.5 py-1 text-[11px] font-semibold text-accent md:inline-flex">
              {card.priority_reason}
            </span>
          )}
        </div>
        <div className="min-w-0 text-right">
          <div className={`truncate font-display font-semibold text-slate-100 ${big ? "text-lg" : "text-base"}`}>{card.name}</div>
          <div className="font-mono text-[11px] text-slate-500">
            {card.type === "ticker" ? "$" : "#"}{card.query}
          </div>
        </div>
      </div>

      {a ? (
        <>
          {/* Satır 2 — Hüküm cümlesi (SERİF, editöryel; TAM, kesme yok; mobilde
              biraz küçük punto ama okunaklı satır aralığı) */}
          <p className={`font-serif font-semibold leading-snug text-slate-100 ${big ? "text-[19px] md:text-[23px]" : "text-[17px] md:text-[19px]"}`}>
            {a.headline_verdict || a.summary}
          </p>

          {/* Alta yapışan blok — MOBİLDE tek satır (sadeleştirme), MASAÜSTÜNDE tam. */}
          <div className="mt-auto">
            {/* MOBİL: yalnızca tek satır fiyat / özel-şirket notu */}
            <div className="md:hidden">
              {card.type === "ticker" ? (
                <CompactPriceLine card={card} />
              ) : (
                <CompactPrivateLine drivers={a.top_drivers} />
              )}
            </div>

            {/* MASAÜSTÜ: fiyat kutusu + analist barı + meta satırı */}
            <div className="hidden space-y-2.5 md:block">
              {card.type === "ticker" ? (
                <>
                  <PriceBox card={card} />
                  {card.analyst?.total > 0 && <AnalystMiniBar a={card.analyst} />}
                </>
              ) : (
                <>
                  <PrivateCompanyBox />
                  {a.top_drivers?.[0] && <TopDriverLine text={a.top_drivers[0]} />}
                </>
              )}
              <div className="text-xs text-slate-500">
                {tt("card.horizon", { h: horizonLabel(card.horizon) })}
                <span className="text-slate-600"> · </span>
                {tt("card.newsCount", { n: card.evidence_count })}
                {changed && <span className="text-amber-400"> · {tt("card.stanceChanged")}</span>}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="mt-auto text-sm text-slate-400">
          {tt("card.pressRefresh", { refresh: tt("header.refresh") })}
        </div>
      )}
    </div>
  );
}

// Katman 2 — sıkışık tek satır (~48px). Sol şerit + ad + ticker + hüküm (kısaltılmış) + risk.
export function EntityRow({ card, onOpen }) {
  const a = card.analysis;
  const stripColor = a ? overallSignal(a.stance, card.evidence_strength).color : "#D8D3C7";
  const changed = a && card.delta?.stance_changed;
  return (
    <button
      onClick={() => onOpen(card.id)}
      className="group flex min-h-[44px] w-full items-center gap-3 overflow-hidden rounded-lg border border-ink-600 bg-ink-800 py-2 pl-0 pr-3 text-left transition hover:border-accent/50 hover:-translate-y-px hover:shadow-card"
    >
      <span className="w-1.5 shrink-0 self-stretch rounded-r" style={{ background: stripColor }} />
      <span className="w-28 shrink-0 truncate font-display text-sm font-semibold text-slate-100 sm:w-32">
        {card.name}
      </span>
      <span className="hidden w-14 shrink-0 truncate font-mono text-[11px] text-slate-500 sm:block">
        {card.type === "ticker" ? "$" : "#"}{card.query}
      </span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-slate-400">
        {a ? a.headline_verdict || a.summary : tt("card.noAnalysisYet")}
      </span>
      {changed && <span className="hidden shrink-0 text-[11px] font-medium text-amber-400 md:inline">{tt("card.stanceChanged")}</span>}
      {a && (
        <span
          className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums"
          style={{ background: `${stripColor}22`, color: stripColor }}
          title="Risk skoru"
        >
          {a.risk_score}
        </span>
      )}
    </button>
  );
}
