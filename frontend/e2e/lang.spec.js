// İlk ziyarette dil: tarayıcı dili de → DE, tr → TR, diğerleri → EN; kayıtlı seçim (nr_lang)
// her zaman önce gelir. Ayrı bir dil penceresi yok; dil bayraklardan değişir. DE sözlüğü ayrı
// paketten yüklenir; <html lang> ve bayrak seçici güncellenir.
// Almanca bayrağı: "local" projesi DE AÇIK derlenir (VITE_ENABLE_DE / NEWSRADAR_ENABLE_DE),
// "prod-subdomains" canlı gibi KAPALI: kapalıyken DE seçicide yok, de tarayıcı ve eski DE
// tercihi EN'e düşer.
import { test as base, expect } from "@playwright/test";
import { TARGETS } from "./stack.mjs";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const H1 = {
  de: "Was sagen die Nachrichten über die Unternehmen, denen du folgst?",
  tr: "Takip ettiğin şirketler hakkında haberler ne diyor?",
  en: "What is the news saying about the companies you follow?",
};
const DASH = { de: "Übersicht", en: "Dashboard", tr: "Pano" };
const deOn = (target) => TARGETS[target].de;

// Backend'deki kullanıcı dili (sohbet ve e-postalar bunu okur).
const backendLang = (page, apiURL) => page.evaluate(async (api) => {
  const tok = localStorage.getItem("newsradar_user_token");
  const r = await fetch(api + "/users/me", { credentials: "include", headers: { Authorization: `Bearer ${tok}` } });
  return (await r.json()).language;
}, apiURL);

for (const [locale, lang] of [["de-DE", "de"], ["tr-TR", "tr"], ["fr-FR", "en"]]) {
  test.describe(`tarayıcı ${locale}`, () => {
    test.use({ locale });
    test(`ilk ziyaret → ${lang} (DE kapalıyken de → en)`, async ({ page, target }) => {
      const want = lang === "de" && !deOn(target) ? "en" : lang;
      await page.goto("/?welcome");
      await expect(page.locator("h1")).toHaveText(H1[want]);
      await expect(page.locator("html")).toHaveAttribute("lang", want);
    });
  });
}

test.describe("uygulama, de tarayıcı, ilk ziyaret", () => {
  test.use({ locale: "de-DE" });
  test("dil penceresi yok: /app doğrudan tarayıcı dilinde, backend dili aynı", async ({ page, apiURL, target }) => {
    const want = deOn(target) ? "de" : "en";
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: DASH[want] })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("lang", want);
    await expect.poll(() => backendLang(page, apiURL)).toBe(want);
    expect(await page.evaluate(() => localStorage.getItem("nr_lang"))).toBeNull(); // seçim yapılmadı
  });

  test("seçim yokken tarayıcı dili backend'deki eski dile üstün gelir ve backend'e yazılır", async ({ page, apiURL, target }) => {
    const want = deOn(target) ? "de" : "en";
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: DASH[want] })).toBeVisible();
    await page.evaluate(async (api) => {
      const tok = localStorage.getItem("newsradar_user_token");
      await fetch(api + "/users/me/language", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` }, body: JSON.stringify({ language: "tr" }) });
    }, apiURL);
    await page.reload();
    await expect(page.getByRole("heading", { name: DASH[want] })).toBeVisible();
    await expect.poll(() => backendLang(page, apiURL)).toBe(want);
  });
});

test.describe("kayıtlı seçim önce gelir (DE açık)", () => {
  test.use({ locale: "de-DE" });
  test("de tarayıcı + nr_lang=tr → TR; bayraktan DE seçilince Almanca ve kalıcı", async ({ page, target }) => {
    test.skip(!deOn(target), "Almanca bu projede kapalı");
    await page.addInitScript(() => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("nr_lang", "tr"); sessionStorage.setItem("seeded", "1"); } });
    await page.goto("/?welcome");
    await expect(page.locator("h1")).toHaveText(H1.tr);
    await page.getByRole("button", { name: "Deutsch" }).first().click();
    await expect(page.locator("h1")).toHaveText(H1.de);
    await expect(page.getByRole("button", { name: "Deutsch" }).first()).toHaveAttribute("aria-pressed", "true");
    expect(await page.evaluate(() => localStorage.getItem("nr_lang"))).toBe("de");
    await page.reload();
    await expect(page.locator("h1")).toHaveText(H1.de);
  });
});

test.describe("Almanca kapalı", () => {
  test.use({ locale: "de-DE" });
  test("seçicide DE yok; daha önce DE seçmiş kullanıcı EN'e düşer (cihaz + hesap)", async ({ page, apiURL, target }) => {
    test.skip(deOn(target), "Almanca bu projede açık");
    await page.addInitScript(() => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("nr_lang", "de"); sessionStorage.setItem("seeded", "1"); } });
    await page.goto("/?welcome");
    await expect(page.locator("h1")).toHaveText(H1.en);
    await expect(page.getByRole("button", { name: "English" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Deutsch" })).toHaveCount(0);
    expect(await page.evaluate(() => localStorage.getItem("nr_lang"))).toBe("en");
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect.poll(() => backendLang(page, apiURL)).toBe("en");
  });
});
