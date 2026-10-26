// Dil ve tema tercihi kalıcı: kullanıcının son seçimi her şeyin önünde (yenileme, /app, detay,
// landing'e dönüş). Tarayıcı dili yalnızca hiç seçim yapılmamışsa kullanılır.
// Kök neden (canlı hata): seçim, hesaba yazma isteği (POST /users/me/language) dönene kadar
// kaydedilmiyordu; sunucu yavaşken yenileyen ya da sayfa değiştiren kullanıcı TR'ye dönüyordu.
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });
test.use({ locale: "tr-TR" });

const H1_EN = "What is the news saying about the companies you follow?";

async function register(page, apiURL) {
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  const username = `p${Date.now() % 1e9}`;
  const status = await page.evaluate(async ({ apiURL, username }) => {
    const tok = localStorage.getItem("newsradar_user_token");
    const r = await fetch(apiURL + "/users/upgrade", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
      body: JSON.stringify({ username, password: "parola12345", email: `${username}@example.com` }),
    });
    const d = await r.json();
    if (d.token) localStorage.setItem("newsradar_user_token", d.token);
    return r.status;
  }, { apiURL, username });
  expect(status).toBe(200);
}

async function expectEnEverywhere(page) {
  await page.reload();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.waitForTimeout(1500); // gecikmeli bir ezme olmasın
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/app/e/999999");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toHaveText(H1_EN);
  await page.waitForTimeout(1000);
  await expect(page.locator("h1")).toHaveText(H1_EN);
}

test("dil: sunucu yavaşken seçim anında geçerli; hemen yenilense de korunur", async ({ page }) => {
  await page.route(/\/users\/me\/language/, async (r) => { await new Promise((ok) => setTimeout(ok, 5000)); r.continue().catch(() => {}); });
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Pano" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).first().click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 1000 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toHaveText(H1_EN);
});

test("dil: landing'de seçim → /app ve yenileme sonrası da geçerli", async ({ page }) => {
  await page.goto("/?welcome");
  await page.getByRole("button", { name: "English" }).first().click();
  await expect(page.locator("h1")).toHaveText(H1_EN);
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});

for (const kind of ["anonim", "kayıtlı"]) {
  test(`dil: TR tarayıcıda EN seçimi kalıcı (${kind})`, async ({ page, apiURL }) => {
    if (kind === "kayıtlı") await register(page, apiURL);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Pano" })).toBeVisible();
    await page.getByRole("button", { name: "English" }).first().click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expectEnEverywhere(page);
  });

  test(`tema: seçim kalıcı (${kind})`, async ({ page, apiURL }) => {
    if (kind === "kayıtlı") await register(page, apiURL);
    await page.goto("/app");
    await page.getByRole("button", { name: /^Tema:/ }).first().click();
    await page.getByRole("menuitemradio", { name: "Koyu" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    for (const path of ["reload", "/app", "/app/e/999999", "/?welcome"]) {
      if (path === "reload") await page.reload(); else await page.goto(path);
      await page.waitForTimeout(800);
      await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    }
  });
}
