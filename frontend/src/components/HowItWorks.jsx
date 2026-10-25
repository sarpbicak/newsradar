// "Nasıl çalışır?" — GERÇEK veriyle 4 adımlık kısa anlatım (statik metin kartının yerine).
// Örnek şirket ve tüm rakamlar backend'den (/how-it-works): son başlıklar, AI etiketleri
// (makale duygusu / LLM'in elediği alakasız), haftalık makale sayısı, kaynaklar, gerçek kart.
// Uygun örnek yoksa uydurma yapılmaz; kısa bir not gösterilir.
// Animasyonlar ≤400ms; prefers-reduced-motion'da animasyonsuz son hal (index.css).
// Mobilde tam ekran. İlk girişte OTOMATİK açılmaz (header / boş ekran bağlantısıyla açılır).
// Landing'deki "Nasıl çalışır" bölümüne bağlanır; HeadlineCards/MiniCard hero döngüsünde de kullanılır.
import React, { useEffect, useState } from "react";
import { MessageSquare, X } from "lucide-react";
import { api } from "../api.js";
import { useI18n, fmtInt, fmtPct, getLang } from "../i18n.jsx";
import { fmtMoney } from "../money.js";
import { StatusTag, stanceLabel, targetOf } from "./ui.jsx";
import { navigate } from "../router.js";
import { Button, LabelChip, Modal, Skeleton } from "./kit.jsx";

const STEPS = 4;

export function HeadlineCards({ headlines, withLabels, t }) {
  return (
    <div className="space-y-2">
      {headlines.map((h, i) => {
        const junk = withLabels && h.label === "irrelevant";
        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded-control bg-ink-800 ring-1 ring-ink-600 px-3 py-2 ${
              withLabels ? (junk ? "hiw-drop" : "") : "hiw-in"
            }`}
            style={withLabels ? (junk ? { animationDelay: "300ms" } : undefined) : { animationDelay: `${i * 80}ms` }}
          >
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-meta font-medium leading-snug text-slate-200">{h.title}</p>
              {h.source && <p className="mt-0.5 text-micro text-slate-500">{h.source}</p>}
            </div>
            {withLabels && (
              <LabelChip label={h.label} t={t} className="hiw-pop" style={{ animationDelay: `${i * 80}ms` }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function MiniCard({ entity, t, animate }) {
  const a = entity.analysis;
  const an = entity.analyst;
  return (
    <div className={`rounded-card bg-ink-800 ring-1 ring-ink-600 p-4 ${animate ? "hiw-card-in" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-base font-medium text-slate-100">{entity.name}</span>
        <span className="font-mono text-xs text-slate-500">
          {entity.type === "ticker" ? "$" : "#"}{entity.query}
        </span>
        {a && <StatusTag stance={a.stance} evidence={entity.evidence_strength} />}
      </div>
      {a?.headline_verdict && (
        <p className="mt-2 font-display text-body font-medium leading-snug text-slate-100">{a.headline_verdict}</p>
      )}
      {entity.price != null && (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-1.5 text-xs">
          <span className="font-mono font-semibold text-slate-100">{fmtMoney(entity.price, entity.currency || "USD", getLang())}</span>
          {entity.change_percent != null && (
            <span className={`font-mono ${entity.change_percent >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
              {fmtPct(entity.change_percent, { digits: 2 })}
            </span>
          )}
          {targetOf(an) != null && (
            <>
              <span className="text-slate-500">→ {t("detail.target")}</span>
              <span className="font-mono font-semibold text-slate-100">{fmtMoney(targetOf(an), entity.currency || "USD", getLang())}</span>
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
    <div className="hiw-card-in rounded-card bg-ink-800 ring-1 ring-ink-600" style={{ animationDelay: "120ms" }}>
      <div className="flex items-center gap-2 border-b border-ink-600 px-3 py-2 text-xs font-semibold text-slate-200">
        <MessageSquare className="h-3.5 w-3.5 text-accent" /> {t("chat.askAi")}
      </div>
      <div className="flex flex-col items-start gap-1.5 p-3">
        {qs.map((q) => (
          <span key={q} className="rounded-control px-2.5 py-1 text-micro text-slate-200 ring-1 ring-inset ring-ink-500">
            {q}
          </span>
        ))}
        <div className="mt-1 w-full rounded-control bg-ink-900 ring-1 ring-inset ring-ink-500 px-2 py-1.5 text-micro text-slate-500">
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

  // ←/→ adım değiştirir (Esc ve odak hapsi ortak Modal'da).
  useEffect(() => {
    const onKey = (e) => {
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
              <LabelChip key={i} label={h.label} t={t} className="hiw-merge" style={{ animationDelay: `${i * 40}ms` }} />
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
    <Modal onClose={onClose} label={t("hiw.dialog")} size="lg">
      <div className="mb-1 flex items-center justify-between gap-3">
        <p className="text-micro font-medium text-accent">{t("hiw.stepOf", { n: step + 1, total: STEPS })}</p>
        <Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label={t("common.close")} className="-mr-2" />
      </div>
      <a
        href="/#how-it-works"
        onClick={(e) => {
          e.preventDefault();
          onClose();
          navigate("/#how-it-works");
        }}
        className="mb-3 inline-block text-meta text-accent underline-offset-2 hover:underline"
      >
        {t("hiw.more")}
      </a>
      {!data && !failed && (
        <div className="space-y-2 py-4" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}
      {(failed || (data && !ready)) && <p className="py-10 text-center text-body text-slate-400">{t("hiw.noData")}</p>}
      {ready && (
        <div key={step}>
          <h2 className="font-display text-title font-semibold text-slate-100">{title}</h2>
          <div className="mt-4">{visual}</div>
          <p className="mt-4 text-meta leading-relaxed text-slate-400">{caption}</p>
        </div>
      )}

      {/* İlerleme noktaları + gezinme */}
      <div className="mt-6 flex items-center justify-center gap-1.5" aria-hidden="true">
        {Array.from({ length: STEPS }).map((_, i) => (
          <span key={i} className={`h-1.5 rounded-[2px] transition-all duration-state ease-std ${i === step ? "w-5 bg-accent" : "w-1.5 bg-ink-500"}`} />
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0} className="disabled:invisible">
          {t("tut.back")}
        </Button>
        {last || !ready ? (
          <Button variant="primary" onClick={onTry}>
            {t("hiw.try")}
          </Button>
        ) : (
          <Button variant="primary" onClick={() => setStep((s) => s + 1)}>
            {t("tut.next")}
          </Button>
        )}
      </div>
    </Modal>
  );
}
