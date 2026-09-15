// NewsRadar API istemcisi — REST uçları + sohbet için SSE streaming.

// Deploy'da Render backend adresi VITE_API_URL ile verilir; yereldeyse localhost.
// (VITE_API_BASE eski isim — geriye uyumluluk için hâlâ kabul edilir.)
const API_BASE =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE ||
  "http://localhost:8000";

// --- İKİ KATMANLI oturum ---
// Katman 1 (genel şifre) token'ı: register/login uçlarını açar.
// Katman 2 (kişisel hesap) token'ı: tüm veri + admin uçlarına gider (user_id taşır).
const GENERAL_KEY = "newsradar_token";        // (eski adı korundu — geriye uyum)
const USER_KEY = "newsradar_user_token";
let generalToken = localStorage.getItem(GENERAL_KEY) || null;
let userToken = localStorage.getItem(USER_KEY) || null;

export function getGeneralToken() {
  return generalToken;
}
export function getUserToken() {
  return userToken;
}
export function setGeneralToken(t) {
  generalToken = t || null;
  if (generalToken) localStorage.setItem(GENERAL_KEY, generalToken);
  else localStorage.removeItem(GENERAL_KEY);
}
export function setUserToken(t) {
  userToken = t || null;
  if (userToken) localStorage.setItem(USER_KEY, userToken);
  else localStorage.removeItem(USER_KEY);
}

// Kişisel oturum 401 olunca App'in kişisel giriş ekranına dönmesi için geri çağrı.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

// Veri/admin istekleri KİŞİSEL token ile gider.
function authHeaders(extra = {}) {
  const h = { "Content-Type": "application/json", ...extra };
  if (userToken) h.Authorization = `Bearer ${userToken}`;
  return h;
}

async function parseError(res, fallback) {
  let detail = fallback || res.statusText;
  try {
    detail = (await res.json()).detail || detail;
  } catch {
    /* yoksay */
  }
  return detail;
}

async function req(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders(options.headers),
    credentials: "include", // anon cihaz cookie'si gönderilsin (cross-origin)
  });
  if (res.status === 401) {
    setUserToken(null); // kişisel oturum düştü → App yeni anon oturum başlatır
    onUnauthorized?.();
    throw new Error("Oturum geçersiz. Lütfen tekrar deneyin.");
  }
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return null;
  return res.json();
}

// ANONİM cihaz oturumu: şifresiz. Cookie ile aynı cihazda kalıcı; token'ı saklar.
export async function bootstrapSession() {
  const res = await fetch(`${API_BASE}/session/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // HttpOnly device cookie yaz/oku
  });
  if (!res.ok) throw new Error(await parseError(res, "Oturum başlatılamadı."));
  const data = await res.json();
  setUserToken(data.token);
  return data.user;
}

// Anonim oturumu KALICI hesaba çevir (liste korunur).
export async function upgradeAccount(username, password) {
  const data = await req("/users/upgrade", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setUserToken(data.token);
  return data.user;
}

// Katman 2: kayıt/giriş — GENEL token ile korunur; kişisel token + user döner.
async function userAuth(path, body) {
  // Herkese açık: genel şifre kapısı YOK. Kayıt/giriş doğrudan.
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res, "İşlem başarısız."));
  const data = await res.json();
  setUserToken(data.token);
  return data.user;
}

export function register(username, password) {
  return userAuth("/users/register", { username, password });
}
export function userLogin(username, password) {
  return userAuth("/users/login", { username, password });
}

export function logout() {
  setUserToken(null); // kişisel çıkış (genel katman korunur — istenirse ayrıca temizlenebilir)
}
export function logoutAll() {
  setUserToken(null);
  setGeneralToken(null);
}

export const api = {
  me: () => req("/users/me"),
  dismissGuide: () => req("/users/me/guide-dismiss", { method: "POST" }),
  finishTutorial: () => req("/users/me/tutorial-done", { method: "POST" }),
  // Admin (yalnızca is_admin kullanıcı; değilse backend 403 döner)
  adminUsers: () => req("/admin/users"),
  adminUserDetail: (id) => req(`/admin/users/${id}`),
  adminDeleteUser: (id) => req(`/admin/users/${id}`, { method: "DELETE" }),
  adminResetPassword: (id) => req(`/admin/users/${id}/reset-password`, { method: "POST" }),
  adminStats: () => req("/admin/stats"),
  status: () => req("/status"),
  listEntities: () => req("/entities"),
  createEntity: (payload) =>
    req("/entities", { method: "POST", body: JSON.stringify(payload) }),
  deleteEntity: (id) => req(`/entities/${id}`, { method: "DELETE" }),
  dashboard: (id) => req(`/entities/${id}/dashboard`),
  refresh: () => req("/refresh", { method: "POST" }),
  searchSymbols: (q) => req(`/symbol-search?q=${encodeURIComponent(q)}`),
  // Öneriler (co-mentioned şirketler)
  listSuggestions: () => req("/suggestions"),
  dismissSuggestion: (id) => req(`/suggestions/${id}/dismiss`, { method: "POST" }),
  addSuggestion: (id) => req(`/suggestions/${id}/add`, { method: "POST" }),
};

// Sohbet: POST /chat text/event-stream döner. EventSource yalnızca GET
// desteklediği için SSE'yi fetch + ReadableStream ile elle parse ediyoruz.
// onDelta(text), onError(msg), onDone() geri çağrıları çağrılır.
export async function streamChat({ entityId, messages, onDelta, onError, onDone }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ entity_id: entityId, messages }),
  });
  if (res.status === 401) {
    setUserToken(null);
    onUnauthorized?.();
    onError?.("Oturum geçersiz. Lütfen tekrar giriş yapın.");
    return;
  }
  if (!res.ok || !res.body) {
    onError?.(`Sohbet başlatılamadı (${res.status}).`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE olayları çift newline ile ayrılır.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "";
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload = {};
      try {
        payload = JSON.parse(data);
      } catch {
        /* yoksay */
      }
      if (event === "delta") onDelta?.(payload.text || "");
      else if (event === "error") onError?.(payload.message || "Bilinmeyen hata");
      else if (event === "done") onDone?.();
    }
  }
  onDone?.();
}
