// İlk ziyarette dil: tarayıcı dili de → DE, tr → TR, diğerleri → EN; kayıtlı seçim (nr_lang)
// her zaman önce gelir. DE sözlüğü ayrı paketten yüklenir; <html lang> ve bayrak seçici güncellenir.
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

test.describe("uygulama, de tarayıcı, ilk ziyaret", () => {
  test.use({ locale: "de-DE" });
  test("/app Almanca açılır (anonim oturum da de), dil penceresi Almanca", async ({ page }) => {
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Sprache / Language" })).toBeVisible();
    await expect(page.getByText("Oberfläche und Einschätzungen werden in dieser Sprache angezeigt.")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Deutsch" }).click();
    await expect(page.getByRole("heading", { name: "Übersicht" })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "de");
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
