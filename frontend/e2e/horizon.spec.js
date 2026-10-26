// Detayda ufuk geri dönüşü: seçili ufukta "yetersiz veri" var, ötekinde veri var → bu şirketin
// detayı veri olan ufku gösterir + not; genel seçim (kaydedilen tercih, seçici) DEĞİŞMEZ.
// Detay API yanıtı sahte bir analizle değiştirilir (gerçek LLM yok).
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const D = (text, direction) => ({ text, direction });
const ANALYSIS = {
  headline_verdict: "Ocugen'in faz 3 ara verisi olumlu.", ai_take: "Tek bir çalışma güncellemesi var.", risk_score: 45,
  sentiment_trend: "stable", top_drivers: ["Faz 3 ara verisi birincil hedefi karşıladı."], driver_directions: ["up"],
  summary: "Tek güncelleme.", stance: "bullish", conviction: "low", what_to_verify: ["Tam sonuçları doğrula."],
  invalidation: "Tam sonuçlar başarısız olursa.", articles_considered: 3, created_at: "2026-10-25T10:00:00Z",
  short_term: { verdict: "positive", summary: "Faz 3 ara verisi bu haftanın haberi.", drivers: [D("Birincil hedef karşılandı.", "up"), D("Hisse yükseldi.", "up")] },
  long_term: { verdict: "insufficient_data", drivers: [], summary: "" },
};
const DASHBOARD = {
  entity: { id: 999, name: "OCUGEN INC", display_name: "Ocugen", type: "ticker", query: "OCGN", language: "en", active: true,
    article_count: 3, analyzed_count: 3, avg_sentiment: 0.3, top_flags: [], last_updated: "2026-10-25T10:00:00Z",
    analysis: ANALYSIS, analysis_language: "tr", evidence_strength: "weak", evidence_count: 3, exchange: "NYSE / Nasdaq",
    country: "ABD", currency: "USD", us_market: true },
  articles: [], article_status: { total: 3, analyzed: 3, prefiltered: 0, pending: 0, expired: 0 },
  risk_history: [], price_history: [], analyst_history: [],
};

test("seçili ufuk boşsa detay veri olan ufku gösterir, genel seçim değişmez", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("nr_lang", "tr"); localStorage.setItem("nr_horizon", "long"); });
  await page.route(/\/entities\/999\/dashboard/, (r) => r.fulfill({ json: DASHBOARD }));
  await page.goto("/app/e/999");
  await expect(page.getByText("Uzun vade için henüz yeterli veri yok, kısa vade gösteriliyor.")).toBeVisible();
  await expect(page.getByText("Haberler · kısa vade: Olumlu").first()).toBeVisible();
  await expect(page.getByText("Haberler · kısa vade").first()).toBeVisible(); // gösterge başlığı
  await expect(page.getByRole("button", { name: "Uzun vade" })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => localStorage.getItem("nr_horizon"))).toBe("long");
});

test("seçili ufukta veri varsa not çıkmaz", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("nr_lang", "tr"); localStorage.setItem("nr_horizon", "short"); });
  await page.route(/\/entities\/999\/dashboard/, (r) => r.fulfill({ json: DASHBOARD }));
  await page.goto("/app/e/999");
  await expect(page.getByText("Haberler · kısa vade: Olumlu").first()).toBeVisible();
  await expect(page.getByText("henüz yeterli veri yok")).toHaveCount(0);
});

// GDELT devre kesici açıkken: haber kaynağı geçici olarak kullanılamıyor → tek, sakin not.
test("haber kaynağı duraklatıldıysa detayda sakin not", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("nr_lang", "tr"); });
  const paused = { ...DASHBOARD, entity: { ...DASHBOARD.entity, news_paused: true } };
  await page.route(/\/entities\/999\/dashboard/, (r) => r.fulfill({ json: paused }));
  await page.goto("/app/e/999");
  await expect(page.getByText("Bu şirketin haber kaynağı geçici olarak kullanılamıyor, mevcut haberler gösteriliyor.")).toBeVisible();
});
