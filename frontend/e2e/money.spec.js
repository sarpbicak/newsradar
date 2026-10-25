// Para birimi biçimi (tarayıcı gerekmez): fiyat kendi para biriminde, dile uygun ondalıkla; dönüşüm yok.
import { test, expect } from "@playwright/test";
import { fmtMoney } from "../src/money.js";

const CASES = [
  // değer, para birimi, tr, en
  [311.21, "USD", "$311,21", "$311.21"],
  [1234.56, "EUR", "€1.234,56", "€1,234.56"],
  [1234.56, "TRY", "₺1.234,56", "₺1,234.56"],
  [3120, "JPY", "¥3.120", "¥3,120"], // yen ondalıksız
  [1234.5, "GBP", "£1.234,50", "£1,234.50"],
];

test("para birimi sembolü ve ondalık biçimi dile uygun", () => {
  for (const [v, cur, tr, en] of CASES) {
    expect(fmtMoney(v, cur, "tr")).toBe(tr);
    expect(fmtMoney(v, cur, "en")).toBe(en);
  }
});

test("hedef fiyat yuvarlama, eksik değer ve bilinmeyen kod", () => {
  expect(fmtMoney(419.6, "USD", "en", { digits: 0 })).toBe("$420");
  expect(fmtMoney(null, "EUR", "tr")).toBe("—");
  expect(fmtMoney(5, "XXX1", "tr")).toBe("5.00 XXX1");
});
