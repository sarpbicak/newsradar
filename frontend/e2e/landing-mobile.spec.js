// Mobil landing okunabilirliği: kaydırınca hero metni solmaz (masaüstünde en az ~0,6), boş
// "Neden yaptım" bölümü DOM'da yok, footer Safari'nin yüzen adres çubuğu için alt boşluk bırakır.
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

// Görünen opaklık = öğe ve tüm atalarının opaklıklarının çarpımı.
const effOpacity = (n) => { let o = 1; for (let e = n; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity); return o; };

async function scrollHero(page, y) {
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForTimeout(1500); // kaydırma motoru ilk boyamadan sonra yüklenir
  await page.mouse.wheel(0, y);
  await page.waitForTimeout(1200);
  return page.locator("h1").evaluate(new Function(`return (${effOpacity})(arguments[0])`));
}

test.describe("mobil", () => {
  test.use({ viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true });

  test("hero kaydırınca solmaz; boş 'Neden yaptım' yok; footer alt boşluğu", async ({ page }) => {
    expect(await scrollHero(page, 500)).toBe(1);
    const cta = page.getByRole("link", { name: /Uygulamayı aç|Open the app/ }).first();
    expect(await cta.evaluate(new Function(`return (${effOpacity})(arguments[0])`))).toBe(1);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect(page.locator("footer")).toBeVisible();
    expect(await page.locator("#why-title").count()).toBe(0);
    const pb = await page.locator("footer > div").evaluate((n) => parseFloat(getComputedStyle(n).paddingBottom));
    expect(pb).toBeGreaterThanOrEqual(72);
  });
});

test("masaüstü: hero en fazla ~0,6 opaklığa iner", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const op = await scrollHero(page, 900);
  expect(op).toBeGreaterThanOrEqual(0.59);
  expect(op).toBeLessThan(1);
});
