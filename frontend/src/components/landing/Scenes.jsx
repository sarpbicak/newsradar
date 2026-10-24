// "Nasıl çalışır" — 4 sahne, KAYDIRMAYA BAĞLI: her sahne ilerlemenin (p: 0..1) saf fonksiyonu.
// Aşağı kaydırınca ileri gider, yukarı kaydırınca geri sarar (harfler silinir, etiketler kalkar).
// Uygulamanın kendi işaretlemesi (arama kutusu, etiket stilleri, Ask AI) ve /public/how-it-works'ün
// GERÇEK verisi: başlıklar, kaynaklar, haftalık sayı, karar, risk, AI gerekçesi. Uydurma yok —
// örnekte alakasız haber yoksa "ayıklanır" adımı da yok.
// Düzen sabit: her öğe baştan yerinde durur, yalnızca opacity/transform değişir (kayma yok).
// p = 1 → son kare (reduced-motion, motor yok, ekran dışı).
import React, { useLayoutEffect, useRef, useState } from "react";
import { MessageSquare } from "lucide-react";
import { fmtInt, fmtPct, useI18n } from "../../i18n.jsx";
import { LabelChip } from "../kit.jsx";
import { NewsPill, riskColor, stanceLabel } from "../ui.jsx";
import { ease, seg } from "../../motion.js";

const symbolOf = (e) => `${e.type === "ticker" ? "$" : "#"}${e.query}`;
const shown = (v) => ({ opacity: v, visibility: v === 0 ? "hidden" : undefined });

function SceneTitle({ children }) {
  return <div className="mb-4 text-sm font-medium text-accent">{children}</div>;
}

// ── 1) Şirket ekle: ad harf harf yazılır → öneri listesi → çip eklenir (kutuda ad kalır) ───
export function SceneAdd({ data, p }) {
  const { t } = useI18n();
  const e = data.entity;
  const n = e.name.length;
  const typed = Math.round(seg(p, 0.06, 0.42) * n);
  const list = ease(seg(p, 0.46, 0.54)) * (1 - seg(p, 0.76, 0.82));
  const picked = p >= 0.6 && p < 0.82;
  const chip = ease(seg(p, 0.8, 0.92));
  return (
    <div>
      <SceneTitle>{t("wl.title")}</SceneTitle>
      <div className="mb-1.5 text-micro font-medium text-slate-500">{t("wl.nameSearch")}</div>
      <div className="relative">
        <div className="flex min-h-[52px] items-center rounded-lg border border-accent bg-ink-900 px-3 text-lg text-slate-100">
          <span>{e.name.slice(0, typed)}</span>
          {p < 0.46 && <span className="ml-px inline-block h-5 w-[2px] bg-slate-300" aria-hidden="true" />}
        </div>
        <div
          className="absolute top-full z-20 mt-1.5 w-full overflow-hidden rounded-lg border border-ink-500 bg-ink-900"
          style={{ ...shown(list), transform: `translate3d(0, ${(1 - list) * -6}px, 0)` }}
        >
          <div className={`flex min-h-[52px] items-center justify-between gap-3 px-4 text-base ${picked ? "bg-ink-700" : ""}`}>
            <span className="truncate text-slate-100">{e.name}</span>
            <span className="shrink-0 font-mono text-sm text-slate-400">{e.query}</span>
          </div>
        </div>
      </div>
      <div className="mt-8 text-sm font-medium text-slate-300">{t("ov.following")}</div>
      <div className="mt-3 flex min-h-[50px] items-center">
        <span
          className="inline-flex items-center gap-2 rounded-card border border-accent/50 bg-ink-800 px-4 py-2 text-lg font-medium text-slate-100"
          style={{ ...shown(chip), transform: `scale(${0.85 + 0.15 * chip})` }}
        >
          {e.name}
          <span className="font-mono text-sm text-slate-500">{symbolOf(e)}</span>
        </span>
      </div>
    </div>
  );
}

function HeadlineCard({ h, children, style, cardRef, dim = 1 }) {
  return (
    <div ref={cardRef} className="flex items-start gap-3 rounded-lg border border-ink-600 bg-ink-800 px-4 py-3" style={style}>
      <div className="min-w-0 flex-1" style={dim === 1 ? undefined : { opacity: dim }}>
        <p className="line-clamp-2 text-[15px] font-medium leading-snug text-slate-100">{h.title}</p>
        {h.source && <p className="mt-1 text-xs text-slate-500">{h.source}</p>}
      </div>
      {children}
    </div>
  );
}

// ── 2) Haberler toplanır: kartlar kaynak adıyla kayarak gelir, büyük sayaç artar ───────────
export function SceneCollect({ data, p }) {
  const { t } = useI18n();
  const heads = data.headlines;
  const k = heads.length;
  const count = Math.round(data.articles_week * ease(seg(p, 0.04, 0.9)));
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="lx-num text-6xl font-medium leading-none text-accent">{fmtInt(count)}</span>
        <span className="text-base text-slate-400">{t("land.sc.newsCount", { n: data.articles_week })}</span>
      </div>
      <div className="mb-5 mt-3 text-sm text-slate-500">
        {data.providers.length > 0 && <>{t("land.sc.sources")} {data.providers.join(" · ")}</>}
      </div>
      <div className="space-y-2.5">
        {heads.map((h, i) => {
          const a = 0.1 + (i * 0.7) / k;
          const o = ease(seg(p, a, a + 0.16));
          return <HeadlineCard key={i} h={h} style={{ ...shown(o), transform: `translate3d(${(1 - o) * 28}px, 0, 0)` }} />;
        })}
      </div>
    </div>
  );
}

// ── 3) AI okur: etiketler sırayla düşer; alakasızlar soluklaşıp listeden çıkar ─────────────
// Çıkan kartın yerini alttakiler transform ile doldurur (yükseklikler ölçülür; düzen sabit).
const GAP = 10;
export function SceneRead({ data, p }) {
  const { t } = useI18n();
  const heads = data.headlines;
  const k = heads.length;
  const junk = heads.filter((h) => h.label === "irrelevant").length;
  const cards = useRef([]);
  const [heights, setHeights] = useState([]);
  useLayoutEffect(() => {
    const measure = () => setHeights(cards.current.map((c) => c?.offsetHeight || 0));
    measure();
    const ro = new ResizeObserver(measure);
    cards.current.forEach((c) => c && ro.observe(c));
    return () => ro.disconnect();
  }, [heads]);

  const labelEnd = junk ? 0.62 : 0.9;
  const step = k > 1 ? (labelEnd - 0.16) / (k - 1) : 0;
  const fade = junk ? ease(seg(p, 0.68, 0.78)) : 0;
  const out = junk ? ease(seg(p, 0.8, 0.94)) : 0;
  let lift = 0;
  return (
    <div>
      <SceneTitle>{t("land.sc.reading")}</SceneTitle>
      <div className="space-y-2.5">
        {heads.map((h, i) => {
          const isJunk = h.label === "irrelevant";
          const o = ease(seg(p, 0.06 + i * step, 0.16 + i * step));
          const style = isJunk
            ? { opacity: 1 - out, transform: `translate3d(${out * 56}px, ${-lift}px, 0)` }
            : { transform: lift ? `translate3d(0, ${-lift}px, 0)` : undefined };
          if (isJunk) lift += out * ((heights[i] || 0) + GAP);
          return (
            <HeadlineCard key={i} h={h} style={style} dim={isJunk ? 1 - 0.55 * fade : 1} cardRef={(el) => (cards.current[i] = el)}>
              <LabelChip label={h.label} t={t} size="md" style={{ ...shown(o), transform: `scale(${0.8 + 0.2 * o})` }} />
            </HeadlineCard>
          );
        })}
      </div>
      {junk > 0 && (
        <p className="mt-4 text-sm text-slate-400" style={{ opacity: out, transform: `translate3d(0, ${-lift}px, 0)` }}>
          {t("land.sc.filtered", { n: junk })}
        </p>
      )}
    </div>
  );
}

// AI gerekçesinin ilk iki cümlesi (en fazla ~240 karakter).
function leadSentences(text, max = 240) {
  const parts = (text || "").match(/[^.!?]+[.!?]+/g) || [text || ""];
  let out = "";
  for (const part of parts) {
    if ((out + part).length > max && out) break;
    out += part;
    if (out.length >= max * 0.6) break;
  }
  return out.trim();
}

// ── 4) Karar: kartlar karar kartına dönüşür, risk barı dolar, soru yazılır, cevap akar ──────
export function SceneVerdict({ data, p }) {
  const { t } = useI18n();
  const e = data.entity;
  const a = e.analysis || {};
  const kept = data.headlines.filter((h) => h.label !== "irrelevant").slice(0, 3);
  const question = t("chat.qWhy", { name: e.name, stance: stanceLabel(a.stance).toLowerCase() });
  const words = leadSentences(a.ai_take || a.summary).split(/\s+/).filter(Boolean);
  const risk = a.risk_score;

  const card = ease(seg(p, 0.16, 0.28));
  const fill = ease(seg(p, 0.28, 0.44));
  const typed = question.slice(0, Math.round(seg(p, 0.46, 0.62) * question.length));
  const sent = ease(seg(p, 0.63, 0.67));
  const nWords = Math.round(seg(p, 0.67, 0.97) * words.length);
  return (
    <div className="space-y-4">
      <SceneTitle>{t("land.sc.verdict")}</SceneTitle>
      <div className="relative">
        <div className="rounded-card border border-ink-600 bg-ink-800 p-5" style={{ ...shown(card), transform: `scale(${0.96 + 0.04 * card})` }}>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="font-display text-xl font-semibold text-slate-100">{e.name}</span>
            <span className="font-mono text-sm text-slate-500">{symbolOf(e)}</span>
            {e.analysis && <NewsPill a={a} evidence={e.evidence_strength} horizon="short" />}
          </div>
          {a.headline_verdict && <p className="mt-3 font-display text-xl font-semibold leading-snug text-slate-100">{a.headline_verdict}</p>}
          {e.price != null && (
            <p className="mt-3 flex flex-wrap items-baseline gap-x-2 text-sm">
              <span className="font-mono font-semibold text-slate-100">${e.price.toFixed(2)}</span>
              {e.change_percent != null && (
                <span className={`font-mono ${e.change_percent >= 0 ? "text-emerald-500" : "text-rose-500"}`}>{fmtPct(e.change_percent, { digits: 2 })}</span>
              )}
            </p>
          )}
        </div>
        {/* Kalan başlıklar karar kartının üstünde birleşip kaybolur. */}
        <div className="absolute inset-x-0 top-0 space-y-2" aria-hidden="true">
          {kept.map((h, i) => {
            const m = ease(seg(p, 0.04 + i * 0.03, 0.18 + i * 0.03));
            return (
              <div
                key={i}
                className="truncate rounded-lg border border-ink-600 bg-ink-800 px-4 py-2 text-sm text-slate-200"
                style={{ ...shown(1 - m), transform: `translate3d(0, ${m * 36}px, 0) scale(${1 - 0.3 * m})` }}
              >
                {h.title}
              </div>
            );
          })}
        </div>
      </div>
      {risk != null && (
        <div className="flex items-center gap-3">
          <span className="w-12 shrink-0 text-sm font-medium text-slate-400">{t("sum.riskLabel")}</span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-[2px] bg-ink-600">
            <div className="h-full origin-left" style={{ transform: `scaleX(${(fill * risk) / 100})`, background: riskColor(risk) }} />
          </div>
          <span className="lx-num w-16 shrink-0 text-right text-base font-semibold" style={{ color: riskColor(risk) }}>
            {Math.round(fill * risk)}/100
          </span>
        </div>
      )}
      <div className="rounded-card border border-ink-600 bg-ink-800">
        <div className="flex items-center gap-2 border-b border-ink-600 px-4 py-2.5 text-sm font-semibold text-slate-200">
          <MessageSquare className="h-4 w-4 text-accent" /> {t("chat.askAi")}
        </div>
        <div className="space-y-2.5 p-4">
          <div className="text-right" style={shown(sent)}>
            <span className="inline-block max-w-[88%] rounded-lg bg-accent/20 px-3.5 py-2 text-left text-[15px] text-slate-100">{question}</span>
          </div>
          <div className="text-left" style={shown(nWords > 0 ? 1 : 0)}>
            <span className="inline-block max-w-[94%] rounded-lg bg-ink-700 px-3.5 py-2.5 text-[15px] leading-relaxed text-slate-200">
              {words.map((w, i) => (
                <span key={i} style={i < nWords ? undefined : { opacity: 0 }}>
                  {w}{" "}
                </span>
              ))}
            </span>
          </div>
        </div>
        <div className="flex gap-2 border-t border-ink-600 p-3">
          <div className="flex min-h-[42px] min-w-0 flex-1 items-center rounded-md border border-ink-500 bg-ink-900 px-3 text-[15px]">
            {typed && sent === 0 ? <span className="truncate text-slate-100">{typed}</span> : <span className="truncate text-slate-500">{t("chat.ask")}</span>}
          </div>
          <span className="inline-flex items-center rounded-md bg-accent px-4 text-[15px] font-medium text-accent-fg">{t("chat.send")}</span>
        </div>
      </div>
    </div>
  );
}

export const SCENES = [SceneAdd, SceneCollect, SceneRead, SceneVerdict];
