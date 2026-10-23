// Landing sahneleri için küçük oynatma motoru (bağımlılık yok).
// - Sahne ilk kez görünür olunca (IntersectionObserver) BİR KEZ oynar ve son karede kalır.
// - replay() başa sarar ve yeniden oynatır.
// - prefers-reduced-motion: animasyon yok — doğrudan son kare.
// schedule: her adımın başlangıç zamanı (ms, artan). step 0 = başlangıç karesi, schedule.length = son kare.
import { useCallback, useEffect, useRef, useState } from "react";

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function usePlayback(ref, schedule, { threshold = 0.35 } = {}) {
  const last = schedule.length;
  const reduced = prefersReducedMotion();
  const [step, setStep] = useState(reduced ? last : 0);
  const [run, setRun] = useState(0);       // 0 = henüz oynamadı; her oynatmada artar
  const timers = useRef([]);
  const key = schedule.join(",");

  // İlk görünürlükte bir kez başlat.
  useEffect(() => {
    if (reduced || run) return undefined;
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) { setRun(1); return undefined; }
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setRun(1); io.disconnect(); }
    }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, reduced, run, threshold]);

  // Oynatma: her adım kendi zamanında.
  useEffect(() => {
    if (!run || reduced) return undefined;
    setStep(0);
    timers.current = schedule.map((at, i) => setTimeout(() => setStep(i + 1), at));
    return () => timers.current.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, reduced, key]);

  const replay = useCallback(() => setRun((r) => r + 1), []);
  return { step, last, run, done: step >= last, replay, reduced, started: run > 0 || reduced };
}

// Artan zamanlar: steps(adet, aralık, başlangıç) → [başlangıç, başlangıç+aralık, ...]
export const steps = (count, every, from = 0) => Array.from({ length: count }, (_, i) => from + i * every);
