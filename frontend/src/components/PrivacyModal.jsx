// GDPR — kısa gizlilik notu (Almanya'da yaşayan kullanıcı için). Ne topluyoruz,
// neden, ne kadar saklıyoruz. Kişisel veri en aza indirgenir (IP kimlik olarak yok).
import React from "react";
import { X, ShieldCheck } from "lucide-react";

export default function PrivacyModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card-hover">
        <button
          onClick={onClose}
          aria-label="Kapat"
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-3 flex items-center gap-2 font-display text-lg font-bold text-slate-100">
          <ShieldCheck className="h-5 w-5 text-accent" /> Gizlilik
        </div>

        <div className="space-y-3 text-[13px] leading-relaxed text-slate-300">
          <p>
            NewsRadar kişisel veriyi en aza indirir. Misafir kullanımda hesap ya da e-posta
            istemeyiz.
          </p>
          <div>
            <div className="font-semibold text-slate-200">Ne topluyoruz?</div>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-400">
              <li>
                <strong>Cihaz kimliği:</strong> tarayıcına yazılan rastgele bir kimlik
                (HttpOnly cookie). Kim olduğunu söylemez; yalnızca aynı cihazda listeni
                hatırlamak için. IP adresin kimlik olarak KULLANILMAZ ve saklanmaz.
              </li>
              <li>
                <strong>İzleme listen ve kullanım olayların</strong> (hangi şirketleri
                ekledin, ne zaman yeniledin) — hizmeti sağlamak ve kötüye kullanımı önlemek için.
              </li>
              <li>
                <strong>Hesap oluşturursan:</strong> seçtiğin kullanıcı adı ve şifrenin
                güvenli özeti (düz şifre asla saklanmaz).
              </li>
            </ul>
          </div>
          <div>
            <div className="font-semibold text-slate-200">Ne kadar saklıyoruz?</div>
            <p className="mt-1 text-slate-400">
              Cihaz kimliği cookie'si ~1 yıl. Verilerini silmek istersen hesap menüsünden
              çıkış yapıp cookie'yi silmen yeterli; kayıtlı hesap silme için yöneticiyle
              iletişime geçebilirsin.
            </p>
          </div>
          <p className="text-slate-400">
            Üçüncü taraflar: haber ve analist verisi Finnhub/NewsAPI/FMP'den, analiz için
            metin OpenRouter (LLM) üzerinden işlenir. Verini reklam için kullanmayız, satmayız.
          </p>
        </div>
      </div>
    </div>
  );
}
