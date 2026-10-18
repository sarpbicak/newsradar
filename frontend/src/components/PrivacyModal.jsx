// GDPR — kısa gizlilik notu (Almanya'da yaşayan kullanıcı için). Ne topluyoruz,
// neden, ne kadar saklıyoruz. Metin KODLA birebir uyumlu: LLM/barındırma sağlayıcısı,
// iletişim adresi ve IP saklama süresi backend'den (/privacy-info) gelir — env değişince
// metin de değişir. Uç ulaşılamazsa sağlayıcı adı uydurulmaz, genel ifadeler kullanılır.
import React, { useEffect, useState } from "react";
import { X, ShieldCheck } from "lucide-react";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";

export default function PrivacyModal({ onClose }) {
  const { t } = useI18n();
  const [info, setInfo] = useState(null);
  useEffect(() => {
    let alive = true;
    api.privacyInfo().then((d) => alive && setInfo(d)).catch(() => {});
    return () => { alive = false; };
  }, []);
  const vars = {
    llm: info?.llm_provider || t("privacy.llmGeneric"),
    hosting: info?.hosting_provider || t("privacy.hostingGeneric"),
    days: info?.ip_retention_days ?? 7,
    contact: info?.contact_email || "",
  };
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
              <li>{t("privacy.cIp", vars)}</li>
              <li>{t("privacy.c2")}</li>
              <li>{t("privacy.c3")}</li>
            </ul>
          </div>
          <div>
            <div className="font-semibold text-slate-200">{t("privacy.retainTitle")}</div>
            <p className="mt-1 text-slate-400">{t("privacy.retainBody", vars)}</p>
            <p className="mt-1 text-slate-400">
              {vars.contact ? (
                <>
                  {t("privacy.contactPre")}{" "}
                  <a href={`mailto:${vars.contact}`} className="text-accent underline">{vars.contact}</a>
                  {t("privacy.contactPost")}
                </>
              ) : (
                t("privacy.contactNone")
              )}
            </p>
          </div>
          <p className="text-slate-400">{t("privacy.thirdParty", vars)}</p>
        </div>
      </div>
    </div>
  );
}
