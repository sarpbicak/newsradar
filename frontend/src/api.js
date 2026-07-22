// NewsRadar API istemcisi — REST uçları + sohbet için SSE streaming.

// Deploy'da Render backend adresi VITE_API_URL ile verilir; yereldeyse localhost.
// (VITE_API_BASE eski isim — geriye uyumluluk için hâlâ kabul edilir.)
const API_BASE =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE ||
  "http://localhost:8000";

// --- Oturum token'ı: localStorage'da saklanır, her istekte Bearer olarak gider ---
const TOKEN_KEY = "newsradar_token";
let authToken = localStorage.getItem(TOKEN_KEY) || null;

export function getToken() {
  return authToken;
}

export function setToken(token) {
  authToken = token || null;
  if (authToken) localStorage.setItem(TOKEN_KEY, authToken);
  else localStorage.removeItem(TOKEN_KEY);
}

// 401 alındığında App'in giriş ekranına dönebilmesi için geri çağrı.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

function authHeaders(extra = {}) {
  const h = { "Content-Type": "application/json", ...extra };
  if (authToken) h.Authorization = `Bearer ${authToken}`;
  return h;
}

async function req(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders(options.headers),
  });
  if (res.status === 401) {
    setToken(null);
    onUnauthorized?.();
    throw new Error("Oturum geçersiz. Lütfen tekrar giriş yapın.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* yoksay */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Parola ile giriş: doğruysa token'ı saklar ve döner, yanlışsa hata fırlatır.
export async function login(password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    let detail = "Giriş başarısız.";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* yoksay */
    }
    throw new Error(detail);
  }
  const { token } = await res.json();
  setToken(token);
  return token;
}

export function logout() {
  setToken(null);
}

export const api = {
  status: () => req("/status"),
  listEntities: () => req("/entities"),
  createEntity: (payload) =>
    req("/entities", { method: "POST", body: JSON.stringify(payload) }),
  deleteEntity: (id) => req(`/entities/${id}`, { method: "DELETE" }),
  dashboard: (id) => req(`/entities/${id}/dashboard`),
  refresh: () => req("/refresh", { method: "POST" }),
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
    setToken(null);
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
