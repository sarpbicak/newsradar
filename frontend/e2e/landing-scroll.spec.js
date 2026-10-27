// Landing kaydırma, mobil: belirmeler masaüstündeki gibi kaydırmaya bağlı ve çift yönlü,
// yalnızca KONUMA göre (her geçişte ekrana girerken artar, geri kaydırırken azalır; ekranın
// ortasında tam; aynı konumda hep aynı değer). Görünür alan = viewport + yüzen yarı saydam
// Safari çubuğunun arkası (BEHIND_BAR). Adres çubuğu taklidi: aşağı inerken viewport +86px.
// Mobil testler MOBILE projelerinde (WebKit iPhone 14, WebKit 402×874, Chromium Pixel 7);
// masaüstü testi "local"de (masaüstü scrub'ı çift yönlü kalır).
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const BEHIND_BAR = 150; // px: viewport'un altında, çubuğun arkasından görünen şerit
const MOBILE = /^(iphone|pixel)/;

// Başlığın görünürlüğü: opaklık zinciri × maskeli satırların görünen payı × kelime opaklığı.
function sample(behind = 0) {
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
    return { k: `${i}:${(el.id || el.textContent).trim().slice(0, 30)}`, inView: r.bottom > 0 && r.top < window.innerHeight + behind, v: vis(el) };
  });
}

// Bölüm başlıkları (h2, adım h3): konum + görünürlük; sayfa yatay taşıyor mu.
function headings() {
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
    return o;
  };
  const vh = window.innerHeight;
  return {
    vh,
    y: Math.round(window.scrollY),
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    hs: [...document.querySelectorAll("main h2, main h3")].map((el, i) => {
      const r = el.getBoundingClientRect();
      return { k: `${i}:${(el.id || el.textContent).trim().slice(0, 28)}`, top: r.top, mid: r.top + r.height / 2, v: vis(el) };
    }),
  };
}

test("mobil: başlıklar her geçişte konuma göre gelir ve geri gider; ortada tam; titreme yok", async ({ page }, info) => {
  test.skip(!MOBILE.test(info.project.name), "yalnızca mobil projelerde");
  test.setTimeout(240_000);
  const { width, height: bar } = page.viewportSize();
  const full = bar + 86; // adres çubuğu küçülmüş
  await page.goto("/?welcome");
  await expect(page.locator("h1")).toBeVisible();
  await page.waitForTimeout(3500); // motor açılıştan sonra yüklenir
  const maxY = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  const ys = [];
  for (let y = 0; y <= maxY; y += 40) ys.push(y);
  const passes = [];
  for (const dir of ["down", "up", "down", "up"]) {
    const h = dir === "down" ? full : bar;
    await page.setViewportSize({ width, height: h });
    const rows = [];
    for (const y of dir === "down" ? ys : [...ys].reverse()) {
      await page.evaluate((v) => window.scrollTo(0, v), y);
      await page.waitForTimeout(25);
      rows.push(await page.evaluate(headings));
    }
    passes.push({ dir, rows });
  }

  const bad = { "1 girişte artar / geri giderken azalır": [], "2 ortada tam": [], "3 aynı konumda aynı değer": [], "4 yatay taşma yok": [] };
  let checked = 0;
  for (const [pi, { dir, rows }] of passes.entries()) {
    const keys = rows[0].hs.map((x) => x.k);
    for (const [hi, k] of keys.entries()) {
      // Giriş şeridi (iki yönde aynı fiziksel aralık): başlığın üstü, küçük viewport'un %60'ı ile
      // büyük viewport'un alt kenarı + çubuk arkası arasında.
      const zone = rows.map((r) => r.hs[hi]).filter((x) => x.top > 0.6 * bar && x.top < full + BEHIND_BAR);
      if (zone.length < 4) continue;
      checked++;
      let worst = 0;
      for (let i = 1; i < zone.length; i++) {
        const d = zone[i].v - zone[i - 1].v;
        worst = Math.max(worst, dir === "down" ? -d : d);
      }
      const span = Math.max(...zone.map((x) => x.v)) - Math.min(...zone.map((x) => x.v));
      if (worst > 0.02 || span < 0.5) bad["1 girişte artar / geri giderken azalır"].push(`${pi + 1}.${dir} ${k}: ters ${worst.toFixed(2)}, aralık ${span.toFixed(2)}`);
    }
    for (const r of rows) {
      if (r.overflow > 0) bad["4 yatay taşma yok"].push(`${pi + 1}.${dir} y=${r.y}: +${r.overflow}px`);
      for (const x of r.hs) if (x.mid > 0.4 * r.vh && x.mid < 0.6 * r.vh && x.v < 0.99) bad["2 ortada tam"].push(`${pi + 1}.${dir} y=${r.y} ${x.k}: ${x.v.toFixed(2)}`);
    }
  }
  // Aynı kaydırma konumunda, ekranın orta bölgesindeki başlığın değeri geçişten geçişe aynı.
  const at = passes.map((p) => new Map(p.rows.map((r) => [r.y, r])));
  for (const y of ys) {
    const rs = at.map((m) => m.get(y)).filter(Boolean);
    for (const [hi, x0] of rs[0].hs.entries()) {
      const vals = rs.filter((r) => r.hs[hi].mid > 0.25 * r.vh && r.hs[hi].mid < 0.75 * r.vh).map((r) => r.hs[hi].v);
      if (vals.length > 1 && Math.max(...vals) - Math.min(...vals) > 0.02) bad["3 aynı konumda aynı değer"].push(`y=${y} ${x0.k}: ${vals.map((v) => v.toFixed(2)).join("/")}`);
    }
  }
  for (const v of Object.values(bad)) v.splice(3); // ilk 3 örnek yeter
  expect(checked, "giriş şeridinden geçen başlık").toBeGreaterThanOrEqual(12);
  expect(bad).toEqual({ "1 girişte artar / geri giderken azalır": [], "2 ortada tam": [], "3 aynı konumda aynı değer": [], "4 yatay taşma yok": [] });
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

test("mobil, reduced-motion: kaydırma boyunca her başlık sabit ve tam görünür", async ({ page }, info) => {
  test.skip(!MOBILE.test(info.project.name), "yalnızca mobil projelerde");
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
