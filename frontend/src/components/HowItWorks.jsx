// "Nasıl çalışır?" — GERÇEK veriyle 4 adımlık kısa anlatım (statik metin kartının yerine).
// Örnek şirket ve tüm rakamlar backend'den (/how-it-works): son başlıklar, AI etiketleri
// (makale duygusu / LLM'in elediği alakasız), haftalık makale sayısı, kaynaklar, gerçek kart.
// Uygun örnek yoksa uydurma yapılmaz; kısa bir not gösterilir.
// Animasyonlar ≤400ms; prefers-reduced-motion'da animasyonsuz son hal (index.css).
// Mobilde tam ekran. İlk girişte OTOMATİK açılmaz (header / boş ekran bağlantısıyla açılır).
import React, { useEffect, useState } from "react";
import { MessageSquare, X } from "lucide-react";
import { api } from "../api.js";
import { useI18n, fmtInt, fmtPct } from "../i18n.jsx";
import { StatusTag, stanceLabel } from "./ui.jsx";

const STEPS = 4;
const LABEL_STYLE = {
  positive: "bg-emerald-500/10 text-emerald-600",
  negative: "bg-rose-500/10 text-rose-600",
  neutral: "bg-slate-500/10 text-slate-500",
  irrelevant: "bg-ink-700 text-slate-500",
};

function HeadlineCards({ headlines, withLabels, t }) {
  return (
    <div className="space-y-2">
      {headlines.map((h, i) => {
        const junk = withLabels && h.label === "irrelevant";
        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded-lg border border-ink-600 bg-ink-800 px-3 py-2 shadow-card ${
              withLabels ? (junk ? "hiw-drop" : "") : "hiw-in"
            }`}
            style={withLabels ? (junk ? { animationDelay: "300ms" } : undefined) : { animationDelay: `${i * 80}ms` }}
          >
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-[13px] font-medium leading-snug text-slate-200">{h.title}</p>
              {h.source && <p className="mt-0.5 text-[10px] text-slate-500">{h.source}</p>}
            </div>
            {withLabels && (
              <span
                className={`hiw-pop shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${LABEL_STYLE[h.label] || LABEL_STYLE.neutral}`}
                style={{ animationDelay: `${i * 80}ms` }}
              >
                {t(`hiw.label.${h.label}`)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MiniCard({ entity, t, animate }) {
  const a = entity.analysis;
  const an = entity.analyst;
  return (
    <div className={`rounded-xl border border-ink-600 bg-ink-800 p-4 shadow-card ${animate ? "hiw-card-in" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-base font-bold text-slate-100">{entity.name}</span>
        <span className="font-mono text-xs text-slate-500">
          {entity.type === "ticker" ? "$" : "#"}{entity.query}
        </span>
        {a && <StatusTag stance={a.stance} evidence={entity.evidence_strength} />}
      </div>
      {a?.headline_verdict && (
        <p className="mt-2 font-serif text-[15px] font-semibold leading-snug text-slate-100">{a.headline_verdict}</p>
      )}
      {entity.price != null && (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-1.5 text-xs">
          <span className="font-mono font-semibold text-slate-100">${entity.price.toFixed(2)}</span>
          {entity.change_percent != null && (
            <span className={`font-mono ${entity.change_percent >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
              {fmtPct(entity.change_percent, { digits: 2 })}
            </span>
          )}
          {an?.target_mean != null && (
            <>
              <span className="text-slate-500">→ {t("detail.target")}</span>
              <span className="font-mono font-semibold text-slate-100">${an.target_mean.toFixed(2)}</span>
              {an.upside_percent != null && (
                <span className={`font-mono font-semibold ${an.upside_percent >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                  {fmtPct(an.upside_percent)}
                </span>
              )}
            </>
          )}
        </p>
      )}
    </div>
  );
}

function AskPanel({ entity, t }) {
  const a = entity.analysis;
  const qs = [
    t("chat.qWhy", { name: entity.name, stance: stanceLabel(a?.stance).toLowerCase() }),
    t("chat.qWatch"),
  ];
  return (
    <div className="hiw-card-in rounded-xl border border-ink-600 bg-ink-800 shadow-card" style={{ animationDelay: "120ms" }}>
      <div className="flex items-center gap-2 border-b border-ink-600 px-3 py-2 text-xs font-semibold text-slate-200">
        <MessageSquare className="h-3.5 w-3.5 text-accent" /> {t("chat.askAi")}
      </div>
      <div className="flex flex-col items-start gap-1.5 p-3">
        {qs.map((q) => (
          <span key={q} className="rounded-full border border-accent/30 bg-accent/5 px-2.5 py-1 text-[11px] text-accent">
            {q}
          </span>
        ))}
        <div className="mt-1 w-full rounded-md border border-ink-500 bg-ink-900 px-2 py-1.5 text-[11px] text-slate-500">
          {t("chat.ask")}
        </div>
      </div>
    </div>
  );
}

export default function HowItWorks({ onClose, onTry }) {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api.howItWorks().then((d) => alive && setData(d)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, []);

  // Esc kapatır; ←/→ adım değiştirir.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setStep((s) => Math.min(STEPS - 1, s + 1));
      if (e.key === "ArrowLeft") setStep((s) => Math.max(0, s - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ready = data?.available && data.entity;
  const last = step === STEPS - 1;
  const relevant = ready ? data.headlines.filter((h) => h.label !== "irrelevant") : [];

  let title = "", caption = "", visual = null;
  if (ready) {
    const e = data.entity;
    if (step === 0) {
      title = t("hiw.s1.title");
      caption = t("hiw.s1.caption", {
        sources: data.providers.join(", ") || "—",
        n: data.articles_week,
        count: fmtInt(data.articles_week),
      });
      visual = <HeadlineCards headlines={data.headlines} withLabels={false} t={t} />;
    } else if (step === 1) {
      title = t("hiw.s2.title");
      caption = t("hiw.s2.caption");
      visual = <HeadlineCards headlines={data.headlines} withLabels t={t} />;
    } else if (step === 2) {
      title = t("hiw.s3.title");
      caption = t("hiw.s3.caption");
      visual = (
        // Etiketler kartın ÜSTÜNE bindirilir ve karta "birleşerek" kaybolur — yer kaplamaz.
        <div className="relative">
          <div className="pointer-events-none absolute inset-x-0 top-3 z-10 flex flex-wrap justify-center gap-1.5">
            {relevant.map((h, i) => (
              <span
                key={i}
                className={`hiw-merge rounded-full px-2 py-0.5 text-[10px] font-semibold ${LABEL_STYLE[h.label]}`}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                {t(`hiw.label.${h.label}`)}
              </span>
            ))}
          </div>
          <MiniCard entity={e} t={t} animate />
        </div>
      );
    } else {
      title = t("hiw.s4.title");
      caption = t("hiw.s4.caption");
      visual = (
        <div className="grid gap-3 sm:grid-cols-[1fr_190px]">
          <MiniCard entity={e} t={t} />
          <AskPanel entity={e} t={t} />
        </div>
      );
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex bg-black/30 backdrop-blur-sm sm:items-center sm:justify-center sm:p-4"
      onClick={(ev) => ev.target === ev.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={t("hiw.dialog")}
    >
      <div className="relative flex h-full w-full flex-col bg-ink-900 p-5 pt-12 sm:h-auto sm:max-h-[92vh] sm:max-w-lg sm:rounded-2xl sm:border sm:border-ink-600 sm:pt-6 sm:shadow-card-hover">
        <button
          onClick={onClose}
          aria-label={t("common.close")}
          className="absolute right-3 top-3 inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <p className="text-[11px] font-semibold uppercase tracking-wide text-accent">
          {t("hiw.stepOf", { n: step + 1, total: STEPS })}
        </p>

        <div className="mt-1 min-h-0 flex-1 overflow-y-auto">
          {!data && !failed && <p className="py-10 text-center text-sm text-slate-500">{t("hiw.loading")}</p>}
          {(failed || (data && !ready)) && (
            <p className="py-10 text-center text-sm leading-relaxed text-slate-400">{t("hiw.noData")}</p>
          )}
          {ready && (
            <div key={step}>
              <h2 className="font-display text-lg font-bold text-slate-100">{title}</h2>
              <div className="mt-4">{visual}</div>
              <p className="mt-4 text-[13px] leading-relaxed text-slate-400">{caption}</p>
            </div>
          )}
        </div>

        {/* İlerleme noktaları + gezinme */}
        <div className="mt-5 flex items-center justify-center gap-1.5" aria-hidden="true">
          {Array.from({ length: STEPS }).map((_, i) => (
            <span key={i} className={`h-1.5 rounded-full transition-all ${i === step ? "w-5 bg-accent" : "w-1.5 bg-ink-500"}`} />
          ))}
        </div>
        <div className="mt-4 flex items-center justify-between gap-3 pb-[env(safe-area-inset-bottom)]">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="min-h-[44px] rounded-lg px-3 text-sm text-slate-400 transition hover:bg-ink-700 hover:text-slate-200 disabled:invisible"
          >
            {t("tut.back")}
          </button>
          {last || !ready ? (
            <button
              onClick={onTry}
              className="min-h-[44px] rounded-lg bg-accent px-4 text-sm font-semibold text-white transition hover:brightness-105"
            >
              {t("hiw.try")}
            </button>
          ) : (
            <button
              onClick={() => setStep((s) => s + 1)}
              className="min-h-[44px] rounded-lg bg-accent px-5 text-sm font-semibold text-white transition hover:brightness-105"
            >
              {t("tut.next")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
