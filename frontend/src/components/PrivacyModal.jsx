// GDPR — kısa gizlilik notu (Almanya'da yaşayan kullanıcı için). Ne topluyoruz,
// neden, ne kadar saklıyoruz. Metin KODLA birebir uyumlu: LLM/barındırma sağlayıcısı,
// iletişim adresi ve IP saklama süresi backend'den (/privacy-info) gelir — env değişince
// metin de değişir. Uç ulaşılamazsa sağlayıcı adı uydurulmaz, genel ifadeler kullanılır.
import React, { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";
import { Modal, ModalHeader } from "./kit.jsx";

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
    <Modal onClose={onClose} labelledBy="privacy-title" size="lg">
      <ModalHeader id="privacy-title" title={t("footer.privacy")} icon={ShieldCheck} onClose={onClose} />
      <div className="space-y-4 text-meta leading-relaxed text-slate-300">
        <p>{t("privacy.intro")}</p>
        <div>
          <h3 className="font-medium text-slate-100">{t("privacy.collectTitle")}</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-slate-400">
            <li>{t("privacy.c1")}</li>
            <li>{t("privacy.cIp", vars)}</li>
            <li>{t("privacy.c2")}</li>
            <li>{t("privacy.c3")}</li>
            <li>{t("privacy.cFeedback")}</li>
          </ul>
        </div>
        <div>
          <h3 className="font-medium text-slate-100">{t("privacy.retainTitle")}</h3>
          <p className="mt-1.5 text-slate-400">{t("privacy.retainBody", vars)}</p>
          <p className="mt-1.5 text-slate-400">
            {vars.contact ? (
              <>
                {t("privacy.contactPre")}{" "}
                <a href={`mailto:${vars.contact}`} className="text-accent underline underline-offset-2">
                  {vars.contact}
                </a>
                {t("privacy.contactPost")}
              </>
            ) : (
              t("privacy.contactNone")
            )}
          </p>
        </div>
        <p className="text-slate-400">{t("privacy.thirdParty", vars)}</p>
      </div>
    </Modal>
  );
}
