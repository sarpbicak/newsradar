// Çıkış: kullanıcı adı ve baş harfi header'da / mobil menüde KALMAMALI; arayüz anında misafir
// olmalı ve cihaz çerezi kayıtlı hesabı sessizce geri getirmemeli (eskiden getiriyordu:
// hesaba geçişte cihaz çerezi aynı kullanıcı satırında kalıyor, çıkıştan sonraki açılış
// isteği o hesabı yeniden döndürüyordu).
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  apiURL: ["", { option: true }],
  target: ["local", { option: true }],
});

async function registeredUser(browser, apiURL, mobile) {
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    ...(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : {}),
  });
  await ctx.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  const page = await ctx.newPage();
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  const username = `u${Date.now() % 1e8}`;
  const res = await page.evaluate(
    async ({ apiURL, username }) => {
      const tok = localStorage.getItem("newsradar_user_token");
      const r = await fetch(apiURL + "/users/upgrade", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
        body: JSON.stringify({ username, password: "parola12345", email: `${username}@example.com` }),
      });
      const d = await r.json();
      if (d.token) localStorage.setItem("newsradar_user_token", d.token);
      return { status: r.status, id: d.user?.id };
    },
    { apiURL, username }
  );
  expect(res.status).toBe(200);
  // Kullanıcıya özel bir tercih (çıkışta temizlenmeli) + cihaz tercihi (kalmalı).
  await page.evaluate(() => {
    localStorage.setItem("nr_hint_account_dismissed", "1");
    localStorage.setItem("nr_theme", "dark");
  });
  await page.reload();
  return { ctx, page, username, id: res.id };
}

async function meId(page, apiURL) {
  return page.evaluate(async (apiURL) => {
    const tok = localStorage.getItem("newsradar_user_token");
    const r = await fetch(apiURL + "/users/me", { credentials: "include", headers: { Authorization: `Bearer ${tok}` } });
    return (await r.json()).id;
  }, apiURL);
}

test("masaüstü: çıkışta kullanıcı adı kaybolur, misafir olunur", async ({ browser, apiURL }) => {
  const { ctx, page, username, id } = await registeredUser(browser, apiURL, false);
  const header = page.locator("header[data-nav-bar]");
  await expect(header).toContainText(username);
  await header.getByRole("button", { name: new RegExp(username) }).click();
  await page.getByRole("menuitem", { name: "Çıkış yap" }).click();
  await expect(header).not.toContainText(username);
  await expect(header.getByRole("button", { name: "Giriş yap" })).toBeVisible();
  // Sayfa yenilense de kayıtlı hesap geri gelmez; yeni bir misafir.
  await page.reload();
  await expect(page.locator("header[data-nav-bar]")).not.toContainText(username);
  expect(await meId(page, apiURL)).not.toBe(id);
  const ls = await page.evaluate(() => ({ hint: localStorage.getItem("nr_hint_account_dismissed"), theme: localStorage.getItem("nr_theme") }));
  expect(ls).toEqual({ hint: null, theme: "dark" });
  await ctx.close();
});

test("mobil: çıkıştan sonra menüde kullanıcı adı ve rozet yok", async ({ browser, apiURL }) => {
  const { ctx, page, username, id } = await registeredUser(browser, apiURL, true);
  const open = () => page.locator("header button[aria-haspopup=dialog]").click();
  await open();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText(username);
  await drawer.getByRole("button", { name: "Çıkış yap" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await open();
  await expect(page.getByRole("dialog")).not.toContainText(username);
  await expect(page.getByRole("dialog")).toContainText("Misafir");
  await expect(page.getByRole("dialog").getByRole("button", { name: "Giriş yap" })).toBeVisible();
  expect(await meId(page, apiURL)).not.toBe(id);
  await ctx.close();
});

test("kayıt formu: e-posta zorunlu ve biçimi denetlenir; e-postayla giriş", async ({ browser, apiURL }) => {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  await ctx.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  const page = await ctx.newPage();
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  await page.locator("header[data-nav-bar]").getByRole("button", { name: "Hesap oluştur", exact: true }).click();
  const dlg = page.getByRole("dialog");
  const name = `f${Date.now() % 1e8}`;
  await dlg.getByLabel("Kullanıcı adı").fill(name);
  await dlg.getByLabel("Şifre").fill("parola12345");
  await dlg.getByLabel("E-posta").fill("bozuk-adres");
  await dlg.getByRole("button", { name: "Hesap oluştur", exact: true }).click();
  await expect(dlg.getByRole("alert")).toHaveText("Geçerli bir e-posta adresi gir.");
  await dlg.getByLabel("E-posta").fill(`${name}@Example.com`);
  await dlg.getByRole("button", { name: "Hesap oluştur", exact: true }).click();
  await expect(page.locator("header[data-nav-bar]")).toContainText(name);
  // Çıkış → e-postayla giriş.
  await page.locator("header[data-nav-bar]").getByRole("button", { name: new RegExp(name) }).click();
  await page.getByRole("menuitem", { name: "Çıkış yap" }).click();
  await page.locator("header[data-nav-bar]").getByRole("button", { name: "Giriş yap", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Kullanıcı adı ya da e-posta").fill(`${name}@example.com`);
  await page.getByRole("dialog").getByLabel("Şifre").fill("parola12345");
  await page.getByRole("dialog").getByRole("button", { name: "Giriş yap", exact: true }).click();
  await expect(page.locator("header[data-nav-bar]")).toContainText(name);
  await ctx.close();
});
