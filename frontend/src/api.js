// NewsRadar API istemcisi — REST uçları + sohbet için SSE streaming.
import { getLang, tt } from "./i18n.jsx";

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

// Makinece okunur hata kodları → kullanıcının dilinde mesaj (ör. mükerrer şirket: 409).
const CODE_MESSAGES = { duplicate_entity: "wl.duplicate", already_in_watchlist: "wl.alreadyIn" };
async function apiError(res) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* gövde yok */
  }
  const key = body && CODE_MESSAGES[body.code];
  const dup = body?.duplicate_of;
  const msg = key ? tt(key, { name: dup?.display_name || dup?.name || "" }) : body?.detail || res.statusText;
  const err = new Error(typeof msg === "string" ? msg : res.statusText);
  err.code = body?.code;
  err.status = res.status;
  err.data = body;
  return err;
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
  if (!res.ok) throw await apiError(res);
  if (res.status === 204) return null;
  return res.json();
}

async function publicGet(path) {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "omit" });
  if (!res.ok) throw new Error(await parseError(res));
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
export async function upgradeAccount(username, password, email) {
  const data = await req("/users/upgrade", {
    method: "POST",
    body: JSON.stringify({ username, password, email }),
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

export function register(username, password, email) {
  return userAuth("/users/register", { username, password, email });
}
// Hesaba e-posta ekle/değiştir (eski hesaplarda boş olabilir).
export function setEmail(email) {
  return req("/users/me/email", { method: "POST", body: JSON.stringify({ email }) });
}
export function userLogin(username, password) {
  return userAuth("/users/login", { username, password });
}

// --- E-posta doğrulama / şifre sıfırlama (bağlantı sayfaları oturumsuz da çalışır) ---
async function publicPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiError(res);
  return res.json();
}
export function forgotPassword(email) {
  return publicPost("/users/forgot-password", { email });
}
export function verifyEmail(token) {
  return publicPost("/users/verify-email", { token });
}
// Yeni şifre: başarılıysa bu cihazda oturum açılır (diğer oturumlar sunucuda kapanır).
export async function resetPassword(token, password) {
  const data = await publicPost("/users/reset-password", { token, password });
  setUserToken(data.token);
  return data.user;
}
// "Tekrar gönder" — 429'da err.retryAfter (sn) dolu döner.
export async function resendVerification() {
  const res = await fetch(`${API_BASE}/users/me/email/resend`, { method: "POST", headers: authHeaders(), credentials: "include" });
  if (!res.ok) {
    const err = await apiError(res);
    err.retryAfter = Number(res.headers.get("Retry-After")) || 60;
    throw err;
  }
  return res.json();
}

// Kullanıcıya özel yerel anahtarlar (çıkışta silinir). Dil/tema CİHAZ tercihidir, kalır.
const USER_SCOPED_KEYS = [USER_KEY, "nr_hint_account_dismissed", "nr_more_starters_dismissed", "nr_chat_panel_open"];
const USER_SCOPED_PREFIXES = ["nr_section_"];

export async function logout() {
  setUserToken(null); // kişisel çıkış (genel katman korunur — istenirse ayrıca temizlenebilir)
  try {
    USER_SCOPED_KEYS.forEach((k) => localStorage.removeItem(k));
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && USER_SCOPED_PREFIXES.some((p) => k.startsWith(p))) localStorage.removeItem(k);
    }
  } catch {
    /* depolama kapalı — yalnızca bellekteki durum sıfırlanır */
  }
  // Cihaz cookie'sini sunucuda sil: aksi halde bir sonraki bootstrap kayıtlı hesabı geri getirir.
  try {
    await fetch(`${API_BASE}/session/logout`, { method: "POST", credentials: "include" });
  } catch {
    /* ağ hatası: token zaten silindi; bootstrap yine denenecek */
  }
}
// Çerezsiz ziyaretçi sayacı: sayfa türü + (yalnızca ilk görüntülemede) yönlendiren adres.
// Kişisel token varsa gönderilir ki admin ziyaretleri sayılmasın. Hata sessizce yutulur.
let referrerSent = false;
export function trackView(page) {
  const referrer = referrerSent ? null : document.referrer || null;
  referrerSent = true;
  const headers = { "Content-Type": "application/json" };
  if (userToken) headers.Authorization = `Bearer ${userToken}`;
  fetch(`${API_BASE}/public/pv`, { method: "POST", headers, body: JSON.stringify({ page, referrer }), keepalive: true, credentials: "omit" })
    .catch(() => {});
}

export function logoutAll() {
  setUserToken(null);
  setGeneralToken(null);
}

export const api = {
  me: () => req("/users/me"),
  setLanguage: (language) => req("/users/me/language", { method: "POST", body: JSON.stringify({ language }) }),
  // Gizlilik metni için gerçek değerler (herkese açık): LLM/barındırma sağlayıcısı,
  // iletişim adresi, IP saklama süresi — hepsi backend config'inden.
  privacyInfo: () => req("/privacy-info"),
  // "Nasıl çalışır?" anlatımının GERÇEK örnek verisi (seed şirket, son başlıklar, kart).
  howItWorks: () => req("/how-it-works"),
  // Landing (oturumsuz): yalnızca toplamlar + seed örneği. Çerez/token GÖNDERİLMEZ —
  // ziyaretçi için oturum açılmaz (kullanıcı kotası tüketilmez).
  publicStats: () => publicGet("/public/stats"),
  publicHowItWorks: (lang) => publicGet(`/public/how-it-works?lang=${encodeURIComponent(lang)}`),
  publicFeatures: () => publicGet("/public/features"),
  // Geri bildirim (herkese açık — anon da gönderebilir)
  sendFeedback: (message, contact) =>
    req("/feedback", { method: "POST", body: JSON.stringify({ message, contact }) }),
  // Admin (yalnızca is_admin kullanıcı; değilse backend 403 döner)
  adminUsers: () => req("/admin/users"),
  adminFeedback: () => req("/admin/feedback"),
  adminMarkFeedbackRead: (id) => req(`/admin/feedback/${id}/read`, { method: "POST" }),
  adminDeleteFeedback: (id) => req(`/admin/feedback/${id}`, { method: "DELETE" }),
  adminUserDetail: (id) => req(`/admin/users/${id}`),
  adminDeleteUser: (id) => req(`/admin/users/${id}`, { method: "DELETE" }),
  adminResetPassword: (id) => req(`/admin/users/${id}/reset-password`, { method: "POST" }),
  adminStats: () => req("/admin/stats"),
  adminVisits: () => req("/admin/visits"),
  status: () => req("/status"),
  // ?lang: AI içeriği arayüzün GÜNCEL dilinde (backend user.language'e güvenmeden).
  listEntities: () => req(`/entities?lang=${getLang()}`),
  createEntity: (payload) =>
    req("/entities", { method: "POST", body: JSON.stringify(payload) }),
  deleteEntity: (id) => req(`/entities/${id}`, { method: "DELETE" }),
  // limit: haber sayısı (varsayılan 50). Grafikler 90 günlük günlük duygu için 200 ister —
  // yalnızca o sekme açılınca (ilk yükleme hafif kalsın).
  dashboard: (id, limit = 50) => req(`/entities/${id}/dashboard?lang=${getLang()}&limit=${limit}`),
  refresh: () => req("/refresh", { method: "POST" }),
  cancelRefresh: () => req("/refresh", { method: "DELETE" }), // sıradaki yenilemeden vazgeç
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
