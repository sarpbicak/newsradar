// İlk giriş tutorial'ı — yeni kullanıcıya kısa, adım adım tanıtım (kapatılabilir).
// Tamamlanınca/kapatılınca bir daha gösterilmez (backend User.tutorial_done).
import React, { useState } from "react";
import { X, Radar, TrendingUp, Sparkles, ShieldCheck } from "lucide-react";

const STEPS = [
  {
    icon: Radar,
    title: "NewsRadar'a hoş geldin!",
    body: "Takip etmek istediğin şirketleri ekle; gerisini biz hallederiz. Haberleri toplar, yapay zekâ ile analiz eder ve sana özetleriz.",
  },
  {
    icon: TrendingUp,
    title: "Şirketleri nasıl eklersin?",
    body: "Halka açık şirketler için ticker seç (Tesla → TSLA). Özel şirketler ya da konular için keyword kullan (SpaceX, OpenAI). Arama kutusu sembolü senin için bulur.",
  },
  {
    icon: Sparkles,
    title: "Yapay zekâ ne yapar?",
    body: "Her şirket için haberleri okur ve tek bir değerlendirme üretir: haberlerin genel havası (olumlu/olumsuz), ne kadar güvenilir olduğu ve — borsadakiler için — analist hedef fiyatı.",
  },
  {
    icon: ShieldCheck,
    title: "Önemli not",
    body: "Bu bir yatırım tavsiyesi değil, haber akışının özetidir. Hedef fiyatlar gerçek analistlerden gelir, bizim tahminimiz değildir. Kararlar sana aittir.",
  },
];

export default function Tutorial({ onClose }) {
  const [step, setStep] = useState(0);
  const s = STEPS[step];
  const Icon = s.icon;
  const last = step === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-2xl border border-ink-600 bg-ink-800 p-6 shadow-card-hover">
        <button
          onClick={onClose}
          aria-label="Kapat"
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
          <Icon className="h-6 w-6" />
        </div>

        <h2 className="mb-2 font-display text-xl font-bold text-slate-100">{s.title}</h2>
        <p className="text-[15px] leading-relaxed text-slate-300">{s.body}</p>

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
            Geç
          </button>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep((v) => v - 1)}
                className="rounded-lg px-3 py-2 text-sm text-slate-400 transition hover:bg-ink-700 hover:text-slate-200"
              >
                Geri
              </button>
            )}
            <button
              onClick={() => (last ? onClose() : setStep((v) => v + 1))}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:brightness-105"
            >
              {last ? "Başla" : "İleri"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
