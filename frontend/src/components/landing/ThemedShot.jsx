// Uygulamanın GERÇEK ekran görüntüsü — dile ve temaya göre. İki tema varyantı da DOM'da;
// aktif olmayan CSS ile gizli (index.css: .shot-light/.shot-dark). loading="lazy" ile gizli
// (display:none) görsel indirilmez → ziyaretçi yalnızca kendi temasının görselini indirir;
// tema değişince görsel anında değişir. width/height verili → düzen kayması (CLS) yok.
// Dosyalar: public/landing/step{n}-{lang}-{theme}.webp (scripts ile üretildi, 1200×750).
import React from "react";

export const SHOT_W = 1200;
export const SHOT_H = 750;

export default function ThemedShot({ step, lang, alt, eager = false, className = "" }) {
  const common = {
    width: SHOT_W,
    height: SHOT_H,
    alt,
    decoding: "async",
    loading: eager ? "eager" : "lazy",
    className: "h-auto w-full rounded-xl border border-ink-600 shadow-card",
  };
  return (
    <div className={className}>
      <img {...common} src={`/landing/step${step}-${lang}-light.webp`} className={`${common.className} shot-light`} />
      <img {...common} src={`/landing/step${step}-${lang}-dark.webp`} className={`${common.className} shot-dark`} />
    </div>
  );
}
