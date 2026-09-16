// GDPR — kısa gizlilik notu (Almanya'da yaşayan kullanıcı için). Ne topluyoruz,
// neden, ne kadar saklıyoruz. Kişisel veri en aza indirgenir (IP kimlik olarak yok).
import React from "react";
import { X, ShieldCheck } from "lucide-react";
import { useI18n } from "../i18n.jsx";

export default function PrivacyModal({ onClose }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card-hover">
        <button
          onClick={onClose}
          aria-label={t("common.close")}
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-3 flex items-center gap-2 font-display text-lg font-bold text-slate-100">
          <ShieldCheck className="h-5 w-5 text-accent" /> {t("footer.privacy")}
        </div>

        <div className="space-y-3 text-[13px] leading-relaxed text-slate-300">
          <p>{t("privacy.intro")}</p>
          <div>
            <div className="font-semibold text-slate-200">{t("privacy.collectTitle")}</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-400">
              <li>{t("privacy.c1")}</li>
              <li>{t("privacy.c2")}</li>
              <li>{t("privacy.c3")}</li>
            </ul>
          </div>
          <div>
            <div className="font-semibold text-slate-200">{t("privacy.retainTitle")}</div>
            <p className="mt-1 text-slate-400">{t("privacy.retainBody")}</p>
          </div>
          <p className="text-slate-400">{t("privacy.thirdParty")}</p>
        </div>
      </div>
    </div>
  );
}
