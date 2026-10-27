// Landing kaydırma (iPhone Safari hatası: başlık ekranın altında görünürken bir an kaybolup
// animasyonla yeniden beliriyordu). Mobil/dokunmatikte belirme yok: ekrandaki hiçbir başlık
// hiçbir an 1'in altına inmez. Adres çubuğu taklidi: yön değişince viewport yüksekliği +86px.
// Masaüstü scrub'ı çift yönlü kalır. Mobil testler iPhone projelerinde (WebKit: iPhone 14 ve
// 402×874), masaüstü testi "local"de.
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

// Başlığın görünürlüğü: opaklık zinciri × maskeli satırların görünen payı × kelime opaklığı.
function sample() {
  const op = (el) => { let o = 1; for (let e = el; e; e = e.parentElement) o *= +getComputedStyle(e).opacity; return o; };
  const vis = (el) => {
    let o = op(el);
    const masks = el.querySelectorAll('[data-fx="mask"]');
    if (masks.length) {
      let s = 0;
      masks.forEach((m) => {
        const r = m.getBoundingClientRect(), c = m.parentElement.getBoundingClientRect();
        s += r.height ? Math.max(0, Math.min(r.bottom, c.bottom) - Math.max(r.top, c.top)) / r.height : 1;
      });
      o *= s / masks.length;
    }
    const words = el.querySelectorAll("[data-w]");
    if (words.length) o *= Math.min(...[...words].map((w) => +getComputedStyle(w).opacity));
    return o;
  };
  const els = [...document.querySelectorAll("main h2, main h3, main [data-w]")]
    .map((el) => (el.matches("[data-w]") ? el.closest("p") : el))
    .filter((el, i, a) => a.indexOf(el) === i);
  return els.map((el, i) => {
    const r = el.getBoundingClientRect();
    return { k: `${i}:${(el.id || el.textContent).trim().slice(0, 30)}`, inView: r.bottom > 0 && r.top < window.innerHeight, v: vis(el) };
  });
}

const IPHONE = /^iphone/;

test("iPhone: ekrandaki başlıklar kaydırma boyunca hep tam görünür", async ({ page }, info) => {
  test.skip(!IPHONE.test(info.project.name), "yalnızca WebKit iPhone projelerinde");
  test.setTimeout(120_000);
  const { width, height: bar } = page.viewportSize();
  const full = bar + 86; // adres çubuğu küçülmüş
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForTimeout(3500); // motor açılıştan sonra yüklenir
  const hist = {};
  let h = bar;
  const step = async (dy) => {
    const want = dy > 0 ? full : bar;
    if (want !== h) await page.setViewportSize({ width, height: (h = want) });
    await page.evaluate((d) => window.scrollBy(0, d), dy);
    await page.waitForTimeout(30);
    for (const e of await page.evaluate(sample)) if (e.inView) (hist[e.k] ||= []).push(e.v);
  };
  const scrollY = () => page.evaluate(() => window.scrollY);
  const maxY = () => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  const turn = Math.round((await maxY()) / 2);
  let turned = false;
  for (let y = 0; y < (await maxY()) - 1; y = await scrollY()) {
    await step(40);
    if (!turned && y >= turn) {
      turned = true;
      for (let k = 0; k < 15; k++) await step(-40); // yarıda geri dön
    }
  }
  while ((await scrollY()) > 0) await step(-40);

  const keys = Object.keys(hist);
  expect(keys.length).toBeGreaterThanOrEqual(8);
  for (const k of keys) expect(Math.min(...hist[k]), `${k} ekrandayken 1'in altına indi`).toBeGreaterThanOrEqual(0.99);
});

test("masaüstü: manifesto scrub'ı çift yönlü kalır", async ({ page }, info) => {
  test.skip(info.project.name !== "local", "masaüstü Chrome, tek proje yeter");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForTimeout(2500);
  const top = await page.locator("[data-w]").first().evaluate((n) => n.closest("section").getBoundingClientRect().top + window.scrollY);
  const lit = () => page.evaluate(() => [...document.querySelectorAll("[data-w]")].filter((w) => +getComputedStyle(w).opacity > 0.99).length);
  await page.evaluate((y) => window.scrollTo(0, y), top + 900);
  await page.waitForTimeout(1500);
  const deep = await lit();
  await page.evaluate((y) => window.scrollTo(0, y), top + 200);
  await page.waitForTimeout(1500);
  const back = await lit();
  expect(deep).toBeGreaterThan(0);
  expect(back).toBeLessThan(deep); // geri kaydırınca kelimeler yeniden söner
});

test("iPhone, reduced-motion: kaydırma boyunca her başlık sabit ve tam görünür", async ({ page }, info) => {
  test.skip(!IPHONE.test(info.project.name), "yalnızca WebKit iPhone projelerinde");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForTimeout(3500);
  const maxY = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  for (let y = 0; y <= maxY; y += 400) {
    await page.evaluate((v) => window.scrollTo(0, v), y);
    await page.waitForTimeout(40);
    for (const e of await page.evaluate(sample)) if (e.inView) expect(e.v, e.k).toBe(1);
  }
});
