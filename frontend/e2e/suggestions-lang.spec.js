// Öneri açıklaması arayüz dilinde: istek ?lang= taşır, dil değişince yeniden gelir; o dilde
// açıklaması olmayan kartta açıklama satırı hiç yok. Sahte veri (route.fulfill), LLM yok.
import { test as base, expect } from "@playwright/test";

const test = base.extend({ apiURL: ["", { option: true }], target: ["local", { option: true }] });

const WHY = { tr: "Anthropic, kurumsal yapay zeka ürünleriyle hızla büyüyor.", en: "Anthropic is growing quickly with its enterprise AI products." };

const card = (id, name, why) => ({
  id, name, ticker: null, is_public: false, mention_count: 5, why_relevant: why,
  source_entity_names: ["Alphabet"], last_seen_at: "2026-11-01T00:00:00Z",
  add_as_type: "keyword", add_as_language: "en",
});

test("EN arayüzde açıklama EN, TR arayüzde TR; çevirisi olmayan kartta satır yok", async ({ page }) => {
  const asked = [];
  await page.route(/\/suggestions\?/, (route) => {
    const lang = new URL(route.request().url()).searchParams.get("lang");
    asked.push(lang);
    return route.fulfill({
      json: [card(1, "Anthropic", WHY[lang]), card(2, "Micron", null)],
      headers: {
        "access-control-allow-origin": route.request().headers().origin || "*",
        "access-control-allow-credentials": "true",
      },
    });
  });
  await page.addInitScript(() => {
    if (!localStorage.getItem("nr_lang")) localStorage.setItem("nr_lang", "en");
    localStorage.setItem("nr_section_suggestions", "1");
  });
  await page.goto("/app");

  await expect(page.getByText(WHY.en)).toBeVisible();
  await expect(page.getByText(WHY.tr)).toHaveCount(0);
  expect(asked.at(-1)).toBe("en");

  await page.getByRole("button", { name: "Türkçe" }).first().click();
  await expect(page.getByText(WHY.tr)).toBeVisible();
  await expect(page.getByText(WHY.en)).toHaveCount(0);
  expect(asked.at(-1)).toBe("tr");

  // İki kart var, açıklama satırı yalnızca Anthropic'te.
  await expect(page.getByText("Micron", { exact: true })).toBeVisible();
  const lines = page.locator("p.text-meta.leading-relaxed");
  await expect(lines).toHaveCount(1);
  await expect(lines).toHaveText(WHY.tr);
});
