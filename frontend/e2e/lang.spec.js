// İlk ziyarette dil: tarayıcı dili de → DE, tr → TR, diğerleri → EN; kayıtlı seçim (nr_lang)
// her zaman önce gelir. Ayrı bir dil penceresi yok; dil bayraklardan değişir. DE sözlüğü ayrı
// paketten yüklenir; <html lang> ve bayrak seçici güncellenir.
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const H1 = {
  de: "Was sagen die Nachrichten über die Unternehmen, denen du folgst?",
  tr: "Takip ettiğin şirketler hakkında haberler ne diyor?",
  en: "What is the news saying about the companies you follow?",
};

for (const [locale, lang] of [["de-DE", "de"], ["tr-TR", "tr"], ["fr-FR", "en"]]) {
  test.describe(`tarayıcı ${locale}`, () => {
    test.use({ locale });
    test(`ilk ziyaret → ${lang}`, async ({ page }) => {
      await page.goto("/?welcome");
      await expect(page.locator("h1")).toHaveText(H1[lang]);
      await expect(page.locator("html")).toHaveAttribute("lang", lang);
    });
  });
}

// Backend'deki kullanıcı dili (sohbet ve e-postalar bunu okur).
const backendLang = (page, apiURL) => page.evaluate(async (api) => {
  const tok = localStorage.getItem("newsradar_user_token");
  const r = await fetch(api + "/users/me", { credentials: "include", headers: { Authorization: `Bearer ${tok}` } });
  return (await r.json()).language;
}, apiURL);

test.describe("uygulama, de tarayıcı, ilk ziyaret", () => {
  test.use({ locale: "de-DE" });
  test("dil penceresi yok: /app doğrudan Almanca, backend dili de", async ({ page, apiURL }) => {
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Übersicht" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("lang", "de");
    await expect.poll(() => backendLang(page, apiURL)).toBe("de");
    expect(await page.evaluate(() => localStorage.getItem("nr_lang"))).toBeNull(); // seçim yapılmadı
  });

  test("seçim yokken tarayıcı dili backend'deki eski dile üstün gelir ve backend'e yazılır", async ({ page, apiURL }) => {
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Übersicht" })).toBeVisible();
    await page.evaluate(async (api) => {
      const tok = localStorage.getItem("newsradar_user_token");
      await fetch(api + "/users/me/language", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` }, body: JSON.stringify({ language: "en" }) });
    }, apiURL);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Übersicht" })).toBeVisible();
    await expect.poll(() => backendLang(page, apiURL)).toBe("de");
  });
});

test.describe("kayıtlı seçim önce gelir", () => {
  test.use({ locale: "de-DE" });
  test("de tarayıcı + nr_lang=tr → TR; bayraktan DE seçilince Almanca ve kalıcı", async ({ page }) => {
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
