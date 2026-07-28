// "Nasıl okunur?" — header'daki "?" ile açılan modal. Sürekli ekranda yer kaplamaz.
import React, { useEffect } from "react";
import { X } from "lucide-react";

export default function HowToModal({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-2xl border border-ink-500 bg-ink-800 p-6 shadow-card-hover"
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-slate-100">Panel nasıl okunur?</h3>
          <button
            onClick={onClose}
            aria-label="kapat"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="text-sm leading-relaxed text-slate-400">
          Her kart bir şirketin son haberlerinin özeti.{" "}
          <strong className="font-semibold text-slate-200">Yön</strong> = haberler olumlu mu
          olumsuz mu. <strong className="font-semibold text-slate-200">Vade</strong> = etkinin ne
          kadar süreceği. <strong className="font-semibold text-slate-200">Kanıt</strong> =
          değerlendirme ne kadar güvenilir (kaç habere dayanıyor).{" "}
          <strong className="font-semibold text-slate-200">Hedef fiyat</strong> = gerçek
          analistlerin beklentisi (bizim tahminimiz değil). En üstteki büyük cümle işin özeti.
        </p>

        {/* Renk anlamları — tutarlı */}
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#3FD68C" }} /> yeşil = olumlu
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#FF6B6B" }} /> kırmızı = olumsuz / risk
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#8B8F9E" }} /> gri = nötr / veri yok
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#7C5CFF" }} /> mor = vurgu / marka
          </span>
        </div>

        <p className="mt-4 border-t border-ink-600 pt-3 text-[11px] leading-relaxed text-slate-500">
          Bu bir yatırım tavsiyesi değil — haber akışının özeti. Kararlar sana ait.
        </p>
      </div>
    </div>
  );
}
