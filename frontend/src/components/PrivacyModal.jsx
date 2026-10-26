// GDPR — kısa gizlilik notu (Almanya'da yaşayan kullanıcı için). Ne topluyoruz,
// neden, ne kadar saklıyoruz. Metin KODLA birebir uyumlu: LLM/barındırma sağlayıcısı,
// iletişim adresi ve IP saklama süresi backend'den (/privacy-info) gelir — env değişince
// metin de değişir. Uç ulaşılamazsa sağlayıcı adı uydurulmaz, genel ifadeler kullanılır.
import React, { useEffect, useState } from "react";
import { ShieldHalf } from "lucide-react"; // App ile paylaşılmayan simge: ayrı minik paket oluşmasın
import { api } from "../api.js";
import { addStrings, useI18n } from "../i18n.jsx";
import { Modal, ModalHeader } from "./kit.jsx";

// Gizlilik metinleri yalnızca bu (tembel) pakette: landing ve panonun ilk paketi küçük kalır.
addStrings({
  "privacy.intro": { tr: "NewsRadar kişisel veriyi en aza indirir. Misafir kullanımda hesap ya da e-posta istemeyiz.", en: "NewsRadar minimizes personal data. In guest use we ask for no account or email." },
  "privacy.collectTitle": { tr: "Ne topluyoruz?", en: "What we collect" },
  "privacy.c1": { tr: "Cihaz kimliği: tarayıcına yazılan rastgele bir kimlik (HttpOnly cookie). Kim olduğunu söylemez; yalnızca aynı cihazda listeni hatırlamak için.", en: "Device ID: a random identifier stored in your browser (HttpOnly cookie). It doesn't say who you are; it only remembers your list on this device." },
  "privacy.cIp": { tr: "IP adresin yalnızca kötüye kullanımı önlemek için (hız sınırı, giriş kilidi, başarısız giriş kaydı) en fazla {days} gün tutulur, kimlik olarak kullanılmaz; süre dolunca otomatik silinir.", en: "Your IP address is kept for at most {days} days and only to prevent abuse (rate limiting, login lockout, failed-login records); it is not used as identity and is deleted automatically afterwards." },
  "privacy.c2": { tr: "İzleme listen ve kullanım olayların (hangi şirketleri ekledin, ne zaman yeniledin). Hizmeti sağlamak ve kötüye kullanımı önlemek için.", en: "Your watchlist and usage events (which companies you added, when you refreshed). Used to run the service and prevent abuse." },
  "privacy.c3": { tr: "Hesap oluşturursan: seçtiğin kullanıcı adı, e-posta adresin ve şifrenin güvenli özeti (düz şifre asla saklanmaz). E-postayı yalnızca adresini doğrulamak ve istediğinde şifre sıfırlama bağlantısı göndermek için kullanırız. Bağlantılardaki tek kullanımlık kodun yalnızca özeti saklanır (doğrulama 24 saat, sıfırlama 1 saat geçerli). E-postanı kimseyle paylaşmayız, pazarlama e-postası göndermeyiz; hesabınla birlikte silinir (aşağıdaki adres).", en: "If you create an account: your chosen username, your email address and a secure hash of your password (the plain password is never stored). We use the email only to verify your address and, when you ask, to send a password reset link. Only a hash of the one-time code in those links is stored (verification valid 24 hours, reset 1 hour). We never share your email and don't send marketing email; it is deleted together with your account (see the address below)." },
  "privacy.cVisits": { tr: "Ziyaret sayımı: çerez kullanmadan, kaç kişinin hangi sayfaları (giriş sayfası, pano, şirket detayı) açtığını ve siteye hangi alan adından geldiğini (ör. linkedin.com) sayarız. Aynı gün aynı kişiyi bir kez saymak için IP adresin ve tarayıcı bilgin, her gün yenilenen ve ertesi gün silinen gizli bir değerle tek yönlü özetlenir; IP adresin ve tarayıcı bilgin saklanmaz, günler arasında seni tanıyamayız. Ülke tutulmaz, üçüncü parti analitik yoktur.", en: "Visit counting: without cookies, we count how many people open which pages (landing page, dashboard, company detail) and which domain they came from (e.g. linkedin.com). To count the same person once per day, your IP address and browser details are hashed one-way with a secret value that changes daily and is deleted the next day; your IP address and browser details are not stored, and we can't recognize you across days. No country is kept and there is no third-party analytics." },
  "privacy.cMail": { tr: "Hesap e-postaları {mail} üzerinden gönderilir.", en: "Account emails are sent via {mail}." },
  "privacy.cFeedback": { tr: "Geri bildirim gönderirsen: mesajın, isteğe bağlı yazdığın e-posta/kullanıcı adı ve tarayıcı türün (mobil/masaüstü ayrımı için). Yalnızca site yöneticisi okur, e-postanı sadece sana yanıt vermek için kullanırız; IP adresin geri bildirimle saklanmaz. Silinmesini istediğinde silinir.", en: "If you send feedback: your message, the email/username you optionally enter, and your browser type (to tell mobile from desktop). Only the site admin reads it; we use your email only to reply to you, and your IP address is not stored with feedback. It is deleted when you ask." },
  "privacy.retainTitle": { tr: "Ne kadar saklıyoruz?", en: "How long we keep it" },
  "privacy.retainBody": { tr: "Cihaz kimliği cookie'si ~1 yıl. Kötüye kullanım önleme kayıtlarındaki IP adresleri {days} gün sonra otomatik silinir. Misafir verilerini silmek için hesap menüsünden çıkış yapıp cookie'yi silmen yeterli.", en: "The device-ID cookie lasts ~1 year. IP addresses in abuse-prevention records are deleted automatically after {days} days. To erase guest data, log out and clear the cookie." },
  "privacy.contactPre": { tr: "Kayıtlı hesabını ya da verilerini sildirmek için", en: "To delete your registered account or your data, write to" },
  "privacy.contactPost": { tr: " adresine yazabilirsin.", en: "." },
  "privacy.contactNone": { tr: "Kayıtlı hesabını sildirmek için site yöneticisiyle iletişime geçebilirsin.", en: "To delete your registered account, contact the site admin." },
  "privacy.llmGeneric": { tr: "LLM sağlayıcımız", en: "our LLM provider" },
  "privacy.hostingGeneric": { tr: "bir bulut sağlayıcı", en: "a cloud provider" },
  "privacy.thirdParty": { tr: "Üçüncü taraflar: fiyat ve analist verisi Finnhub/FMP'den, haberler Finnhub, GNews ve GDELT'ten gelir; analiz için metin {llm} üzerinden işlenir. Site {hosting} üzerinde barındırılır; sunucu kayıtları (istek IP'leri dahil) barındırma sağlayıcısının saklama kurallarına tabidir. Verini reklam için kullanmayız, satmayız.", en: "Third parties: price and analyst data come from Finnhub/FMP, news from Finnhub, GNews and GDELT; text is processed for analysis via {llm}. The site is hosted on {hosting}; server logs (including request IPs) follow the hosting provider's retention rules. We don't use your data for ads, and we don't sell it." },
});

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
      <ModalHeader id="privacy-title" title={t("footer.privacy")} icon={ShieldHalf} onClose={onClose} />
      <div className="space-y-4 text-meta leading-relaxed text-slate-300">
        <p>{t("privacy.intro")}</p>
        <div>
          <h3 className="font-medium text-slate-100">{t("privacy.collectTitle")}</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-slate-400">
            <li>{t("privacy.c1")}</li>
            <li>{t("privacy.cIp", vars)}</li>
            <li>{t("privacy.c2")}</li>
            <li>{t("privacy.cVisits")}</li>
            <li>
              {t("privacy.c3")}
              {info?.email_provider && <> {t("privacy.cMail", { mail: info.email_provider })}</>}
            </li>
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
