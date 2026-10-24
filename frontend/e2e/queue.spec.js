// Yenileme kuyruğu: iki ayrı kullanıcı aynı anda "Yenile"ye basar. İlki hemen başlar, ikincisi
// "Sıradasın" görür; ilkinin taraması bitince ikincinin kendi yenilemesi başlar ve tamamlanır.
// Backend sahte tarama ile çalışır (NEWSRADAR_FAKE_REFRESH_SECONDS, anahtarsız). Şirketler farklı:
// aynı şirket olsaydı ikinci iş "birleşir" (zaten güncellendi) ve hiç başlamazdı.
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  apiURL: ["", { option: true }],
  target: ["local", { option: true }],
});

const refreshBtn = (page) => page.getByTestId("refresh").filter({ visible: true });

async function guestWithCompany(browser, apiURL, company) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  await ctx.addInitScript(() => localStorage.setItem("nr_lang", "tr"));
  const page = await ctx.newPage();
  await page.goto("/app");
  await page.waitForFunction(() => localStorage.getItem("newsradar_user_token"));
  const status = await page.evaluate(
    async ({ apiURL, company }) => {
      const tok = localStorage.getItem("newsradar_user_token");
      const r = await fetch(apiURL + "/entities", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
        body: JSON.stringify(company),
      });
      return r.status;
    },
    { apiURL, company }
  );
  expect([200, 201]).toContain(status);
  await page.reload();
  await expect(refreshBtn(page)).toHaveText(/1 hak/);
  return { ctx, page };
}

test("iki kullanıcı aynı anda: ikincisi sırada bekler, sonra kendi yenilemesi tamamlanır", async ({ browser, apiURL }) => {
  test.setTimeout(60_000);
  const a = await guestWithCompany(browser, apiURL, { name: "Tesla", type: "ticker", query: "TSLA", language: "en" });
  const b = await guestWithCompany(browser, apiURL, { name: "NVIDIA", type: "ticker", query: "NVDA", language: "en" });

  const ackA = a.page.waitForResponse((r) => /\/refresh(\?|$)/.test(r.url()) && r.request().method() === "POST");
  await refreshBtn(a.page).click();
  expect(await (await ackA).json()).toMatchObject({ accepted: true, started: true });

  const ackB = b.page.waitForResponse((r) => /\/refresh(\?|$)/.test(r.url()) && r.request().method() === "POST");
  await refreshBtn(b.page).click();
  const bodyB = await (await ackB).json();
  expect(bodyB).toMatchObject({ accepted: true, queued: true, queue_position: 1 });

  // B 1. sırada: buton ve şerit "Sıradaki sensin" (2+ sırada "Sıradasın: N. sıra"); hak henüz
  // düşmedi (başlayınca düşer).
  await expect(refreshBtn(b.page)).toHaveText(/Sıradaki sensin/);
  await expect(b.page.getByRole("status").getByText("Sıradaki sensin")).toBeVisible();

  // A biter, sonra B'nin sırası gelir: "Yenileniyor" → "Tamamlandı"; B'nin hakkı başlayınca düşer.
  await expect(a.page.getByText(/Tamamlandı/).first()).toBeVisible({ timeout: 20_000 });
  await expect(refreshBtn(b.page)).toHaveText(/Yenileniyor/, { timeout: 20_000 });
  await expect(b.page.getByText(/Tamamlandı/).first()).toBeVisible({ timeout: 20_000 });
  await expect(refreshBtn(b.page)).toHaveText(/yenilenir/);
  await expect(b.page.getByText(/Yenileme başlatılamadı/)).toHaveCount(0);

  await a.ctx.close();
  await b.ctx.close();
});

test("sıradan vazgeç: hak düşmez", async ({ browser, apiURL }) => {
  test.setTimeout(60_000);
  const a = await guestWithCompany(browser, apiURL, { name: "Apple", type: "ticker", query: "AAPL", language: "en" });
  const b = await guestWithCompany(browser, apiURL, { name: "Microsoft", type: "ticker", query: "MSFT", language: "en" });
  await refreshBtn(a.page).click();
  await expect(refreshBtn(a.page)).toHaveText(/Yenileniyor|Başlatılıyor/);
  await refreshBtn(b.page).click();
  await expect(b.page.getByText(/Sıradaki sensin|Sıradasın: \d+\. sıra/).last()).toBeVisible();
  const del = b.page.waitForResponse((r) => /\/refresh(\?|$)/.test(r.url()) && r.request().method() === "DELETE");
  await b.page.getByRole("button", { name: "Vazgeç" }).click();
  expect((await del).status()).toBe(204);
  await expect(refreshBtn(b.page)).toHaveText(/1 hak/, { timeout: 10_000 });
  await expect(a.page.getByText(/Tamamlandı/).first()).toBeVisible({ timeout: 20_000 });
  await a.ctx.close();
  await b.ctx.close();
});
