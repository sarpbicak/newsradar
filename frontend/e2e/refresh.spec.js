// "Yenile" tek tıkla başlamalı; başlayamazsa kullanıcı HER ZAMAN açık bir not görmeli.
//
// Gerileme: polling, POST /refresh onaylanmadan başlıyordu. Tıklama anında giden /status
// ("çalışmıyor") yavaş /entities ile aynı Promise.all'da bekliyor, sonra taze durumun üstüne
// yazılıyordu → gösterge sönüyor, tarama arka planda sessizce sürüyor, hak düşüyordu.
// Testler /entities'i production'daki gibi yavaşlatarak bu sırayı zorlar.
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  apiURL: ["", { option: true }],
  target: ["local", { option: true }],
  page: async ({ page }, use) => {
    await page.addInitScript(() => {
      if (!localStorage.getItem("nr_lang")) localStorage.setItem("nr_lang", "tr");
    });
    await use(page);
  },
});

const SLOW_ENTITIES_MS = 400;
// Header'da masaüstü ve mobil (kompakt) iki düğme var; görünür olan.
const refreshBtn = (page) => page.getByTestId("refresh").filter({ visible: true });

async function slowEntities(page) {
  await page.route(/\/entities(\?|$)/, async (route) => {
    if (route.request().method() === "GET") await new Promise((r) => setTimeout(r, SLOW_ENTITIES_MS));
    await route.continue();
  });
}

// Sayfanın kendi oturumuyla API çağrısı (cookie + token, tarayıcıdaki gibi).
function apiCall(page, apiURL, path, { method = "GET", body, token } = {}) {
  return page.evaluate(
    async ({ apiURL, path, method, body, token }) => {
      const tok = token ?? localStorage.getItem("newsradar_user_token");
      const res = await fetch(apiURL + path, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: res.status, body: await res.json().catch(() => null) };
    },
    { apiURL, path, method, body, token }
  );
}

async function openAsGuest(page) {
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  await expect(refreshBtn(page)).toBeVisible();
}

async function addCompany(page, apiURL) {
  const r = await apiCall(page, apiURL, "/entities", {
    method: "POST",
    body: { name: "Tesla", type: "ticker", query: "TSLA", language: "en" },
  });
  expect([200, 201]).toContain(r.status);
}

async function loginAsNewUser(page, apiURL) {
  const tok = await page.evaluate(async (apiURL) => {
    const post = (path, body, token) =>
      fetch(apiURL + path, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
      }).then((r) => r.json());
    const g = await post("/auth/login", { password: "e2e-genel-sifre" });
    await post("/users/register", { username: "e2eadmin", password: "parola12345" }, g.token); // ilk kayıt (admin) — varsa 409
    const u = await post("/users/register", { username: `u${Date.now()}`, password: "parola12345" }, g.token);
    return u.token;
  }, apiURL);
  expect(tok).toBeTruthy();
  await page.evaluate((t) => localStorage.setItem("newsradar_user_token", t), tok);
}

// Tek tıklama → POST /refresh başladı → arayüz taramayı gösterir (çalışıyor ya da bitti),
// hata notu yok, hak sayacı sunucudakiyle aynı (bayat sayı kalmaz).
async function clickOnceAndExpectStarted(page, { leftAfter }) {
  const btn = refreshBtn(page);
  const ack = page.waitForResponse((r) => /\/refresh(\?|$)/.test(r.url()) && r.request().method() === "POST");
  await btn.click();
  const res = await ack;
  expect(res.status()).toBe(200);
  expect(await res.json()).toMatchObject({ started: true });
  // Anahtarsız tarama çok hızlı biter: "Yenileniyor…" ya da bitiş satırı "Tamamlandı" görünmeli.
  await expect(page.getByText(/Yenileniyor|Başlatılıyor|Tamamlandı/).first()).toBeVisible();
  await page.waitForTimeout(SLOW_ENTITIES_MS * 3);
  await expect(page.getByText(/Yenileme başlatılamadı/)).toHaveCount(0);
  await expect(btn).toHaveText(leftAfter, { timeout: 10_000 });
}

test("misafir: tek tıklama yenilemeyi başlatır", async ({ page, apiURL }) => {
  await openAsGuest(page);
  await addCompany(page, apiURL);
  await slowEntities(page);
  await page.reload();
  await expect(refreshBtn(page)).toHaveText(/1 hak/);
  // Misafir hakkı 1 → tarama başlayınca hak biter.
  await clickOnceAndExpectStarted(page, { leftAfter: /yenilenir/ });
});

test("giriş yapmış kullanıcı: ilk tıklama yenilemeyi başlatır", async ({ page, apiURL }) => {
  await openAsGuest(page);
  await loginAsNewUser(page, apiURL);
  await page.reload();
  await addCompany(page, apiURL);
  await slowEntities(page);
  await page.reload();
  await expect(refreshBtn(page)).toHaveText(/3 hak/);
  await clickOnceAndExpectStarted(page, { leftAfter: /2 hak/ });
});

test("misafir, boş liste: başlamazsa açık not gösterilir", async ({ page }) => {
  await openAsGuest(page);
  await refreshBtn(page).click();
  await expect(page.getByRole("alert")).toContainText("Yenileme başlatılamadı: izleme listen boş");
});

test("sunucu hatası: not + Tekrar dene ile yenileme başlar", async ({ page, apiURL }) => {
  await openAsGuest(page);
  await addCompany(page, apiURL);
  await page.reload();
  let fail = true;
  await page.route(/\/refresh(\?|$)/, (route) =>
    fail && route.request().method() === "POST"
      ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Sunucu hatası" }) })
      : route.continue()
  );
  await refreshBtn(page).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Yenileme başlatılamadı: Sunucu hatası");
  fail = false;
  const ack = page.waitForResponse((r) => /\/refresh(\?|$)/.test(r.url()) && r.request().method() === "POST");
  await alert.getByRole("button", { name: "Tekrar dene" }).click();
  expect(await (await ack).json()).toMatchObject({ started: true });
  await expect(page.getByText(/Yenileme başlatılamadı/)).toHaveCount(0);
});

test("misafir cihaz çerezi ilk istekte oluşur ve aynı misafire döner", async ({ page, apiURL, target, context }) => {
  await openAsGuest(page);
  const cookies = await context.cookies(apiURL);
  const device = cookies.find((c) => c.name === "nr_device");
  expect(device, "nr_device cookie'si yazılmalı").toBeTruthy();
  expect(device.httpOnly).toBe(true);
  expect(device.sameSite).toBe("Lax");
  if (target === "prod") {
    expect(device.secure).toBe(true);
    expect(device.domain).toBe(".newsradar.test");
  }
  const me = (await apiCall(page, apiURL, "/users/me")).body;
  // Token kaybolsa bile (ör. localStorage temizlendi) cookie aynı misafiri geri getirir.
  await page.evaluate(() => localStorage.removeItem("newsradar_user_token"));
  await page.reload();
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  const again = (await apiCall(page, apiURL, "/users/me")).body;
  expect(again.id).toBe(me.id);
});
