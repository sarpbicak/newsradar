// Minimal istemci yönlendirmesi ("/" landing, "/app" pano, "/app/e/<id>" detay) — ek bağımlılık yok.
// CloudFront'ta bilinmeyen yol → index.html (SPA hata yanıtları), yerelde Vite aynısını yapar.
import { useEffect, useState } from "react";

const EVENT = "nr:navigate";

export function navigate(to, { replace = false } = {}) {
  if (to === window.location.pathname + window.location.search + window.location.hash) return;
  window.history[replace ? "replaceState" : "pushState"](null, "", to);
  window.dispatchEvent(new Event(EVENT));
  if (!to.includes("#")) window.scrollTo(0, 0);
}

export function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener("popstate", update);
    window.addEventListener(EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(EVENT, update);
    };
  }, []);
  return path;
}

export const isAppPath = (path) => path === "/app" || path.startsWith("/app/");

// Daha önce gelmiş (cihaz oturumu / kayıtlı hesap) ziyaretçi "/"'ı açınca doğrudan panoya.
// Cihaz çerezi HttpOnly (JS okuyamaz); aynı bootstrap'te yazılan oturum token'ı localStorage'da.
// "/#bolum" ya da "/?welcome" ile landing yine görülebilir (uygulamadaki "Hakkında" bağlantısı).
export function shouldSkipLanding() {
  const { pathname, search, hash } = window.location;
  if (pathname !== "/" || hash || new URLSearchParams(search).has("welcome")) return false;
  try {
    return !!localStorage.getItem("newsradar_user_token");
  } catch {
    return false;
  }
}
