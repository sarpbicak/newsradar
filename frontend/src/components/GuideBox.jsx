// "NewsRadar ne yapar?" — panonun en üstünde, ilk açılışta görünen, kapatılabilir
// açıklama kutusu. Kapatma tercihi backend'de (User.guide_dismissed) saklanır;
// header'daki "Nasıl çalışır?" linki tekrar açar. localStorage KULLANILMAZ.
import React from "react";
import { X, Radar } from "lucide-react";

export default function GuideBox({ onClose }) {
  return (
    <div className="relative mb-6 rounded-xl border border-ink-600 bg-ink-800 p-5 shadow-card sm:p-6">
      <button
        onClick={onClose}
        aria-label="Açıklamayı kapat"
        className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="mb-2 flex items-center gap-2 font-display text-lg font-bold text-slate-100">
        <Radar className="h-5 w-5 text-accent" />
        NewsRadar ne yapar?
      </div>

      <p className="max-w-3xl text-[15px] leading-relaxed text-slate-300">
        NewsRadar, takip ettiğin şirketlerin son haberlerini toplar ve yapay zekâ ile
        analiz eder. Her kart sana o şirket hakkında haberlerin genel havasını
        (olumlu/olumsuz), ne kadar güvenilir olduğunu (kaç habere dayandığını) ve —
        borsada işlem gören şirketler için — analistlerin hedef fiyatını gösterir.
      </p>

      <p className="mt-3 max-w-3xl rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-relaxed text-slate-300">
        <strong className="text-slate-200">Önemli:</strong> Bu bir yatırım tavsiyesi
        değil, haber akışının özetidir. Hedef fiyatlar gerçek analistlerden gelir, bizim
        tahminimiz değildir. Kararlar sana aittir.
      </p>
    </div>
  );
}
