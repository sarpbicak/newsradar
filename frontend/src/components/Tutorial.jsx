// İlk giriş tutorial'ı — yeni kullanıcıya kısa, adım adım tanıtım (kapatılabilir).
// Tamamlanınca/kapatılınca bir daha gösterilmez (backend User.tutorial_done).
import React, { useState } from "react";
import { X, TrendingUp, Sparkles, ShieldCheck } from "lucide-react";
import Logo from "./Logo.jsx";
import { useI18n } from "../i18n.jsx";

const STEPS = [
  { icon: Logo, titleKey: "tut.s1.title", bodyKey: "tut.s1.body" },
  { icon: TrendingUp, titleKey: "tut.s2.title", bodyKey: "tut.s2.body" },
  { icon: Sparkles, titleKey: "tut.s3.title", bodyKey: "tut.s3.body" },
  { icon: ShieldCheck, titleKey: "tut.note.title", bodyKey: "tut.s4.disclaimer" },
];

export default function Tutorial({ onClose }) {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const s = STEPS[step];
  const Icon = s.icon;
  const last = step === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card-hover">
        <button
          onClick={onClose}
          aria-label={t("common.close")}
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
          <Icon className="h-6 w-6" />
        </div>

        <h2 className="mb-2 font-display text-xl font-bold text-slate-100">{t(s.titleKey)}</h2>
        <p className="text-[15px] leading-relaxed text-slate-300">{t(s.bodyKey)}</p>

        {/* Adım göstergesi */}
        <div className="mt-6 flex items-center justify-center gap-1.5">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === step ? "w-5 bg-accent" : "w-1.5 bg-ink-500"
              }`}
            />
          ))}
        </div>

        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            className="text-sm text-slate-500 transition hover:text-slate-300"
          >
            {t("tut.skip")}
          </button>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep((v) => v - 1)}
                className="rounded-lg px-3 py-2 text-sm text-slate-400 transition hover:bg-ink-700 hover:text-slate-200"
              >
                {t("tut.back")}
              </button>
            )}
            <button
              onClick={() => (last ? onClose() : setStep((v) => v + 1))}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:brightness-105"
            >
              {last ? t("tut.start") : t("tut.next")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
