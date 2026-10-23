// Landing "Nasıl çalışır" — 4 animasyonlu sahne. Uygulamanın kendi parçalarıyla (HeadlineCards,
// MiniCard, etiket stilleri, arama kutusu / sohbet işaretlemesi) ve /public/how-it-works'ün
// GERÇEK verisiyle kurulur: başlıklar, kaynaklar, haftalık sayı, karar, risk, AI gerekçesi.
// Uydurma veri yok — örnekte alakasız haber yoksa "elenir" adımı da gösterilmez.
//
// Her sahne kaydırıp görününce BİR KEZ oynar, son karede kalır; köşede "tekrar oynat".
// prefers-reduced-motion: animasyon yok, son kare statik (usePlayback).
// Düzen kayması yok: sahnenin en kalabalık karesi görünmez bir kopya olarak alanı belirler,
// canlı kare onun üstünde oynar (dil/ekran genişliği/başlık uzunluğu ne olursa olsun).
// Hareket yalnızca opacity/transform/genişlik geçişleri (CSS) — kütüphane yok.
import React, { useRef } from "react";
import { MessageSquare, RotateCcw } from "lucide-react";
import { fmtInt, useI18n } from "../../i18n.jsx";
import { HeadlineCards, LABEL_STYLE, MiniCard } from "../HowItWorks.jsx";
import { AnimatedNumber, riskColor, stanceLabel } from "../ui.jsx";
import { steps, usePlayback } from "./usePlayback.js";

function Stage({ stageRef, ghost, live, pb, label }) {
  const { t } = useI18n();
  return (
    <div ref={stageRef} className="relative rounded-2xl border border-ink-600 bg-ink-800/70 p-4 shadow-card sm:p-5">
      <div className="relative">
        <div aria-hidden="true" className="invisible">{ghost}</div>
        {/* key=run: her oynatmada canlı kare sıfırdan kurulur (sayaç/risk barı geriye akmaz) */}
        <div key={pb.run} className="absolute inset-0" aria-label={label}>{live}</div>
      </div>
      {!pb.reduced && pb.started && (
        <button
          type="button"
          onClick={pb.replay}
          aria-label={t("land.replay")}
          title={t("land.replay")}
          className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

function SceneTitle({ children, className = "mb-3" }) {
  return <div className={`${className} pr-9 text-[11px] font-semibold uppercase tracking-wide text-accent`}>{children}</div>;
}

const symbolOf = (e) => `${e.type === "ticker" ? "$" : "#"}${e.query}`;

// ── 1) Şirket ekle: ad harf harf yazılır → öneri listesi → çip eklenir ──────────────────
export function SceneAdd({ data }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const e = data.entity;
  const n = e.name.length;
  const schedule = [...steps(n, 110, 400), 400 + n * 110 + 350, 400 + n * 110 + 1050, 400 + n * 110 + 1650];
  const pb = usePlayback(ref, schedule);

  const frame = (s) => {
    const typedDone = s >= n;
    const open = s === n + 1 || s === n + 2;
    const chip = s >= n + 3;
    const typed = chip ? "" : e.name.slice(0, Math.min(s, n));
    return (
      <div>
        <SceneTitle>{t("wl.title")}</SceneTitle>
        <label className="mb-1 block text-[10px] uppercase text-slate-500">{t("wl.nameSearch")}</label>
        <div className="relative">
          <div className="flex min-h-[44px] w-full items-center rounded-md border border-accent bg-ink-900 px-2 text-sm text-slate-100">
            <span>{typed}</span>
            {!typedDone && <span className="ml-px inline-block h-4 w-px animate-pulse bg-slate-300" aria-hidden="true" />}
          </div>
          {open && (
            <div className="hiw-in absolute top-full z-20 mt-1 w-full overflow-hidden rounded-md border border-ink-500 bg-ink-900 shadow-xl">
              <div className={`flex min-h-[44px] items-center justify-between gap-2 px-3 py-2 text-xs ${s === n + 2 ? "bg-ink-700" : ""}`}>
                <span className="truncate text-slate-200">{e.name}</span>
                <span className="shrink-0 font-mono text-slate-400">{e.query}</span>
              </div>
            </div>
          )}
        </div>
        <div className="mt-5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t("ov.following")}</div>
        <div className="mt-2 flex min-h-[36px] flex-wrap gap-2">
          {chip && (
            <span className="hiw-pop inline-flex items-center gap-1.5 rounded-lg border border-accent/50 bg-ink-800 px-3 py-1.5 text-sm font-medium text-slate-100 shadow-card">
              {e.name}
              <span className="font-mono text-[11px] text-slate-500">{symbolOf(e)}</span>
            </span>
          )}
        </div>
      </div>
    );
  };
  return <Stage stageRef={ref} pb={pb} ghost={frame(pb.last)} live={frame(pb.step)} label={t("land.step1.title")} />;
}

// ── 2) Haberler toplanır: kartlar kaynak adıyla kayarak gelir, "N haber" sayacı artar ─────
export function SceneCollect({ data }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const heads = data.headlines;
  const k = heads.length;
  const pb = usePlayback(ref, steps(k, 480, 300));

  const frame = (s, ghost = false) => {
    const count = Math.round((data.articles_week * Math.min(s, k)) / k);
    return (
      <div>
        <SceneTitle>
          {data.providers.length ? (
            <>{t("land.sc.sources")} <span className="normal-case">{data.providers.join(" · ")}</span></>
          ) : "\u00a0"}
        </SceneTitle>
        <div className="mb-3 font-display text-2xl font-bold text-slate-100">
          {ghost ? fmtInt(count) : <AnimatedNumber value={count} format={(v) => fmtInt(Math.round(v))} />}{" "}
          <span className="text-sm font-medium text-slate-400">{t("land.sc.newsCount", { n: data.articles_week })}</span>
        </div>
        <HeadlineCards headlines={heads.slice(0, ghost ? k : s)} withLabels={false} t={t} />
      </div>
    );
  };
  return <Stage stageRef={ref} pb={pb} ghost={frame(k, true)} live={frame(pb.step)} label={t("land.step2.title")} />;
}

// ── 3) AI okur: etiketler sırayla düşer; alakasızlar soluklaşıp listeden çıkar ─────────────
export function SceneRead({ data }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const heads = data.headlines;
  const k = heads.length;
  const junk = heads.filter((h) => h.label === "irrelevant").length;
  const schedule = [...steps(k, 560, 300), ...(junk ? [300 + k * 560 + 400, 300 + k * 560 + 1100] : [])];
  const pb = usePlayback(ref, schedule);

  const frame = (s, ghost = false) => {
    const fade = !ghost && junk && s >= k + 1;
    const gone = !ghost && junk && s >= k + 2;
    return (
      <div>
        <SceneTitle>{t("land.sc.reading")}</SceneTitle>
        <div className="space-y-2">
          {heads.map((h, i) => {
            const isJunk = h.label === "irrelevant";
            const labeled = ghost || s > i;
            return (
              // grid-rows 1fr → 0fr: kart yüksekliği yumuşakça kapanır (alakasız listeden çıkar)
              <div
                key={i}
                className={`grid transition-all duration-500 ${isJunk && gone ? "-my-1 grid-rows-[0fr] opacity-0" : "grid-rows-[1fr]"}`}
              >
                <div className="min-h-0 overflow-hidden">
                  <div
                    className={`flex items-start gap-2 rounded-lg border border-ink-600 bg-ink-800 px-3 py-2 shadow-card transition-opacity duration-500 ${
                      isJunk && fade ? "opacity-40" : ""
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className={`line-clamp-2 text-[13px] font-medium leading-snug text-slate-200 ${isJunk && fade ? "line-through" : ""}`}>{h.title}</p>
                      {h.source && <p className="mt-0.5 text-[10px] text-slate-500">{h.source}</p>}
                    </div>
                    {labeled && (
                      <span className={`${ghost ? "" : "hiw-pop"} shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${LABEL_STYLE[h.label] || LABEL_STYLE.neutral}`}>
                        {t(`hiw.label.${h.label}`)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {junk > 0 && (ghost || gone) && (
          <p className={`${ghost ? "" : "hiw-in"} mt-3 text-[12px] text-slate-500`}>{t("land.sc.filtered", { n: junk })}</p>
        )}
      </div>
    );
  };
  return <Stage stageRef={ref} pb={pb} ghost={frame(k, true)} live={frame(pb.step)} label={t("land.step3.title")} />;
}

// İlk iki cümle (en fazla ~240 karakter) — AI gerekçesinden.
function leadSentences(text, max = 240) {
  const parts = (text || "").match(/[^.!?]+[.!?]+/g) || [text || ""];
  let out = "";
  for (const p of parts) {
    if ((out + p).length > max && out) break;
    out += p;
    if (out.length >= max * 0.6) break;
  }
  return out.trim();
}

// ── 4) Karar: kartlar karar kartına dönüşür, risk barı dolar, Ask AI'da soru → akan cevap ──
export function SceneVerdict({ data }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const e = data.entity;
  const a = e.analysis || {};
  const kept = data.headlines.filter((h) => h.label !== "irrelevant");
  const question = t("chat.qWhy", { name: e.name, stance: stanceLabel(a.stance).toLowerCase() });
  const answer = leadSentences(a.ai_take || a.summary);
  const words = answer.split(/\s+/).filter(Boolean);
  const qn = question.length;
  // 1 kartlar birleşir · 2 karar kartı · 3 risk dolar · 4..(3+qn) soru yazılır · gönder · cevap akar
  const tq = 2200;
  const tSend = tq + qn * 28 + 350;
  const schedule = [300, 900, 1500, ...steps(qn, 28, tq), tSend, ...steps(words.length, 55, tSend + 500)];
  const pb = usePlayback(ref, schedule);
  const risk = a.risk_score;

  const frame = (s, ghost = false) => {
    const sendStep = 4 + qn;
    const typed = s >= sendStep ? "" : question.slice(0, Math.max(0, s - 3));
    const shownWords = ghost ? words.length : Math.max(0, s - sendStep);
    return (
      <div className="space-y-3">
        <SceneTitle className="">{t("land.hero.p2")}</SceneTitle>
        {/* Kart alanı baştan ayrılır (görünmez); 1. adımda kalan başlıklar onun üstünde birleşir. */}
        <div className="relative">
          <div className={ghost || s >= 2 ? "" : "invisible"}>
            <MiniCard key={ghost || s >= 2 ? "on" : "off"} entity={e} t={t} animate={!ghost} />
          </div>
          {!ghost && s === 1 && (
            <div className="absolute inset-0 space-y-1.5" aria-hidden="true">
              {kept.slice(0, 3).map((h, i) => (
                <div key={i} className="hiw-merge truncate rounded-lg border border-ink-600 bg-ink-800 px-3 py-1.5 text-[12px] text-slate-300"
                     style={{ animationDelay: `${i * 60}ms` }}>
                  {h.title}
                </div>
              ))}
            </div>
          )}
        </div>
        {risk != null && (
          <div className="flex items-center gap-3">
            <span className="w-10 shrink-0 text-xs font-medium text-slate-400">{t("sum.riskLabel")}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-600">
              <div className="h-full rounded-full transition-[width] duration-1000 ease-out"
                   style={{ width: `${ghost || s >= 3 ? risk : 0}%`, background: riskColor(risk) }} />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-xs font-semibold" style={{ color: riskColor(risk) }}>
              {ghost || s >= 3 ? risk : 0}/100
            </span>
          </div>
        )}
        <div className="rounded-xl border border-ink-600 bg-ink-800">
          <div className="flex items-center gap-2 border-b border-ink-600 px-3 py-2 text-xs font-semibold text-slate-200">
            <MessageSquare className="h-3.5 w-3.5 text-accent" /> {t("chat.askAi")}
          </div>
          <div className="space-y-2 p-3">
            {(ghost || s >= sendStep) && (
              <div className="text-right">
                <span className="inline-block max-w-[85%] rounded-lg bg-accent/20 px-3 py-2 text-left text-[13px] text-slate-100">{question}</span>
              </div>
            )}
            {(ghost || shownWords > 0) && (
              <div className="text-left">
                <span className="inline-block max-w-[92%] rounded-lg bg-ink-700 px-3 py-2 text-[13px] leading-relaxed text-slate-200">
                  {words.slice(0, shownWords).join(" ")}
                  {!ghost && shownWords < words.length && <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-slate-400 align-middle" aria-hidden="true" />}
                </span>
              </div>
            )}
          </div>
          <div className="flex gap-2 border-t border-ink-600 p-2.5">
            <div className="flex min-h-[36px] flex-1 items-center truncate rounded-md border border-ink-500 bg-ink-900 px-3 text-[13px]">
              {typed ? <span className="truncate text-slate-100">{typed}</span> : <span className="text-slate-500">{t("chat.ask")}</span>}
            </div>
            <span className="inline-flex items-center rounded-md bg-accent px-3 text-[13px] font-medium text-accent-fg">{t("chat.send")}</span>
          </div>
        </div>
      </div>
    );
  };
  return <Stage stageRef={ref} pb={pb} ghost={frame(pb.last, true)} live={frame(pb.step)} label={t("land.step4.title")} />;
}

export const SCENES = [SceneAdd, SceneCollect, SceneRead, SceneVerdict];
