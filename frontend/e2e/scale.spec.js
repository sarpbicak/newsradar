// Detay skalası: haberler ve analistler tek yatay skalada; iki işaret ayrı şekil (daire / eşkenar
// dörtgen), aynı kademedeyse çakışmaz; haber verisi yetersizse işaret yok, not var; hedef satırı
// "Analist hedefi $442 (+%19)", kaynak yalnızca ipucunda. Detay yanıtı sahte (gerçek LLM yok).
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const D = (text, direction) => ({ text, direction });
const analysis = (short, long) => ({
  headline_verdict: "Teslimatlar düştü.", ai_take: "Kısa yorum.", risk_score: 50, sentiment_trend: "stable",
  top_drivers: ["Teslimatlar düştü."], driver_directions: ["down"], summary: "Özet.", stance: "bearish",
  conviction: "medium", what_to_verify: [], invalidation: "", articles_considered: 12, created_at: "2026-10-25T10:00:00Z",
  short_term: short, long_term: long,
});
// 10 güçlü al + 30 al + 14 tut → skor 0,93 → "Olumlu" (54 analist).
const ANALYST = { strong_buy: 10, buy: 30, hold: 14, sell: 0, strong_sell: 0, total: 54, period: "2026-10-01",
  target: 442, target_kind: "median", target_mean: 430, target_median: 442, upside_percent: 19.0,
  current_price: 371.4, fetched_at: "2026-10-25T08:00:00Z" };
const dashboard = (a) => ({
  entity: { id: 999, name: "TESLA INC", display_name: "Tesla", type: "ticker", query: "TSLA", language: "en", active: true,
    article_count: 12, analyzed_count: 12, avg_sentiment: -0.2, top_flags: [], last_updated: "2026-10-25T10:00:00Z",
    analysis: a, analysis_language: "tr", evidence_strength: "medium", evidence_count: 12, price: 371.4, change_percent: 1.2,
    currency: "USD", us_market: true, analyst: ANALYST },
  articles: [], article_status: { total: 12, analyzed: 12, prefiltered: 0, pending: 0, expired: 0 },
  risk_history: [], price_history: [], analyst_history: [],
});
const NEG = { verdict: "negative", summary: "Olumsuz hafta.", drivers: [D("Teslimatlar düştü.", "down"), D("Fiyat indirimi.", "down")] };
const POS = { verdict: "positive", summary: "Olumlu.", drivers: [D("Sipariş arttı.", "up"), D("Maliyet düştü.", "up")] };
const NONE = { verdict: "insufficient_data", summary: "", drivers: [] };

async function open(page, a) {
  await page.addInitScript(() => { localStorage.setItem("nr_lang", "tr"); localStorage.setItem("nr_horizon", "short"); });
  await page.route(/\/entities\/999\/dashboard/, (r) => r.fulfill({ json: dashboard(a) }));
  await page.goto("/app/e/999");
  return page.getByRole("region", { name: "Haber yönü ve analist görüşü" });
}

test("haberler olumsuz, analistler olumlu: tek skala, iki etiketli işaret, hedef satırı", async ({ page }) => {
  const scale = await open(page, analysis(NEG, NEG));
  await expect(scale.getByRole("img", { name: "Haberler olumsuz, analistler olumlu" })).toBeVisible();
  await expect(scale.getByText("Haberler (kısa vade)")).toBeVisible();
  await expect(scale.getByText("Analistler (54)")).toBeVisible();
  const target = scale.getByText(/Analist hedefi/);
  await expect(target).toHaveText(/Analist hedefi \$442 \(\+%19\)/);
  await expect(target).toHaveAttribute("title", "Medyan hedef, FMP"); // kaynak yalnızca ipucunda
  await expect(scale.getByText("FMP")).toHaveCount(0);
  const box = await scale.boundingBox();
  expect(box.height).toBeLessThanOrEqual(128); // ~120px
});

test("aynı kademedeki iki işaret çakışmaz (yan yana)", async ({ page }) => {
  const scale = await open(page, analysis(POS, POS));
  await expect(scale.getByRole("img", { name: "Haberler olumlu, analistler olumlu" })).toBeVisible();
  const shapes = scale.locator(".relative.mt-1 > span.absolute");
  await expect(shapes).toHaveCount(2);
  const [b1, b2] = [await shapes.nth(0).boundingBox(), await shapes.nth(1).boundingBox()];
  expect(b1.x + b1.width <= b2.x || b2.x + b2.width <= b1.x).toBe(true);
});

test("haber verisi yetersizse haber işareti yok, kısa not var", async ({ page }) => {
  const scale = await open(page, analysis(NONE, NONE));
  await expect(scale.getByRole("img", { name: "Haberler için yeterli veri yok, analistler olumlu" })).toBeVisible();
  await expect(scale.getByText("Haberler (kısa vade): yeterli veri yok.")).toBeVisible();
  await expect(scale.locator(".relative.mt-1 > span.absolute")).toHaveCount(1);
});

// Pano kartı: kompakt skala (tek çizgi, iki işaret, analist sayısı); eski analist çubuğu yok.
const card = () => ({ ...dashboard(analysis(NEG, NEG)).entity, priority_score: 3, priority_reason: "divergence", tier: 1 });
test("pano kartı: kompakt skala, analist sayısı, 'buy-leaning' çubuğu yok", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("nr_lang", "tr"); localStorage.setItem("nr_horizon", "short"); });
  await page.route(/\/entities\?lang=/, (r) => r.fulfill({ json: [card()] }));
  await page.goto("/app");
  await expect(page.getByRole("img", { name: "Haberler olumsuz, analistler olumlu" }).first()).toBeVisible();
  await expect(page.getByText("54 analist").first()).toBeVisible();
  await expect(page.getByText(/buy-leaning|alım yönlü/)).toHaveCount(0);
});
