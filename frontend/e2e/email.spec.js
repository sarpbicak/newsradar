// E-posta doğrulama ve şifre sıfırlama arayüzü (e2e yığını console arka uçla çalışır → özellik açık).
// Gerçek posta okunmaz; arayüz davranışı ve sunucu yanıtlarının doğru gösterimi denetlenir.
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  apiURL: ["", { option: true }],
  target: ["local", { option: true }],
});

async function registered(browser, apiURL) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  await ctx.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  const page = await ctx.newPage();
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  const username = `m${Date.now() % 1e8}`;
  const status = await page.evaluate(async ({ apiURL, username }) => {
    const tok = localStorage.getItem("newsradar_user_token");
    const r = await fetch(apiURL + "/users/upgrade", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
      body: JSON.stringify({ username, password: "parola12345", email: `${username}@example.com` }),
    });
    const d = await r.json();
    if (d.token) localStorage.setItem("newsradar_user_token", d.token);
    return r.status;
  }, { apiURL, username });
  expect(status).toBe(200);
  await page.reload();
  return { ctx, page, username };
}

test("doğrulanmamış e-posta: menüde uyarı, tekrar gönder bekleme süresi gösterir", async ({ browser, apiURL }) => {
  const { ctx, page, username } = await registered(browser, apiURL);
  const header = page.locator("header[data-nav-bar]");
  await header.getByRole("button", { name: new RegExp(username) }).click();
  await page.getByRole("menuitem", { name: "E-postanı doğrula" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(`${username}@example.com`);
  // Hesaba geçişte bağlantı zaten gitti → 1 dk dolmadan sunucu 429 + Retry-After döner.
  await dialog.getByRole("button", { name: "Tekrar gönder" }).click();
  await expect(dialog.getByRole("button", { name: /Tekrar gönder \(\d+ sn\)/ })).toBeDisabled();
  await ctx.close();
});

test("şifremi unuttum: adres ne olursa olsun aynı genel mesaj", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  await page.goto("/app");
  await page.locator("header[data-nav-bar]").getByRole("button", { name: "Giriş yap", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Şifremi unuttum" }).click();
  await dialog.getByLabel("E-posta").fill("kimse-yok@example.com");
  await dialog.getByRole("button", { name: "Bağlantı gönder" }).click();
  await expect(dialog).toContainText("Bu adres kayıtlıysa şifre sıfırlama bağlantısı gönderdik");
});

// EMAIL_BACKEND: /public/features → email. ses (ya da yerel) true; canlıda console false.
const emailFeature = (target, email) =>
  target.route("**/public/features", (route) => route.fulfill({
    json: { email },
    headers: {
      "access-control-allow-origin": route.request().headers().origin || "*",
      "access-control-allow-credentials": "true",
    },
  }));

for (const [name, email] of [["ses: açık", true], ["console (canlı): kapalı", false]]) {
  test(`e-posta özelliği ${name} → "Şifremi unuttum" ve doğrulama uyarısı ${email ? "görünür" : "gizli"}`, async ({ browser, apiURL }) => {
    const { ctx, page, username } = await registered(browser, apiURL);
    await emailFeature(ctx, email);
    await page.reload();
    const header = page.locator("header[data-nav-bar]");
    await header.getByRole("button", { name: new RegExp(username) }).click();
    await expect(page.getByRole("menuitem", { name: "Çıkış yap" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "E-postanı doğrula" })).toHaveCount(email ? 1 : 0);
    await page.keyboard.press("Escape");

    const guest = await browser.newContext({ ignoreHTTPSErrors: true });
    await guest.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
    await emailFeature(guest, email);
    const p2 = await guest.newPage();
    const features = p2.waitForResponse("**/public/features");
    await p2.goto("/app");
    await features;
    await p2.locator("header[data-nav-bar]").getByRole("button", { name: "Giriş yap", exact: true }).click();
    await expect(p2.getByRole("dialog").getByLabel("Şifre", { exact: true })).toBeVisible();
    await expect(p2.getByRole("dialog").getByRole("button", { name: "Şifremi unuttum" })).toHaveCount(email ? 1 : 0);
    await guest.close();
    await ctx.close();
  });
}

test("bağlantı sayfaları: geçersiz token açıkça söylenir, token adres çubuğundan silinir", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  await page.goto("/verify-email?token=uydurma-token");
  await expect(page.getByRole("status")).toContainText("Bağlantı çalışmadı");
  expect(page.url()).not.toContain("token=");
  await page.goto("/reset-password?token=uydurma-token");
  await page.getByLabel("Yeni şifre", { exact: true }).fill("yeniparola99");
  expect(page.url()).not.toContain("token="); // sayfa (ayrı paket) yüklenince silinir
  await page.getByLabel("Yeni şifre (tekrar)").fill("yeniparola99");
  await page.getByRole("button", { name: "Şifreyi değiştir" }).click();
  await expect(page.getByRole("alert")).toContainText("Bağlantı geçersiz");
});
