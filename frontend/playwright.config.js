// Playwright e2e: `npm run e2e` (yerelde sistem Chrome'u için PW_CHANNEL=chrome).
// İki proje aynı testleri koşar: ayrı portlar (local) ve production gibi ayrı alt alan
// adları + HTTPS + Secure cookie (prod). Backend anahtarsız çalışır (e2e/stack.mjs).
import { defineConfig, devices } from "@playwright/test";
import { TARGETS, ensureCert } from "./e2e/stack.mjs";

ensureCert(); // iki HTTPS sunucusu aynı sertifikayı kullanır; yarışmasınlar diye önceden

const channel = process.env.PW_CHANNEL || undefined;
const server = (what, mode, url) => ({
  command: `node e2e/stack.mjs ${what} ${mode}`,
  url,
  ignoreHTTPSErrors: true,
  reuseExistingServer: false,
  timeout: 120_000,
  stdout: "ignore",
  stderr: "pipe",
});

export default defineConfig({
  testDir: "./e2e",
  // Sunucuda aynı anda tek tarama çalışır → testler sırayla.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 45_000,
  reporter: [["list"]],
  use: { locale: "tr-TR", trace: "retain-on-failure" },
  projects: [
    {
      name: "local",
      use: { channel, baseURL: TARGETS.local.web, apiURL: TARGETS.local.api, target: "local" },
    },
    {
      name: "prod-subdomains",
      use: {
        channel,
        baseURL: TARGETS.prod.web,
        apiURL: TARGETS.prod.api,
        target: "prod",
        ignoreHTTPSErrors: true,
        launchOptions: { args: ["--host-resolver-rules=MAP *.newsradar.test 127.0.0.1"] },
      },
    },
    {
      // iPhone Safari kaydırma (landing-scroll.spec.js): `npx playwright install webkit`
      name: "iphone-webkit",
      testMatch: /landing-scroll\.spec\.js/,
      use: { ...devices["iPhone 14"], baseURL: TARGETS.local.web, apiURL: TARGETS.local.api, target: "local" },
    },
    {
      name: "iphone-402-webkit", // iPhone 17 boyutu
      testMatch: /landing-scroll\.spec\.js/,
      use: { ...devices["iPhone 14"], viewport: { width: 402, height: 874 }, screen: { width: 402, height: 874 }, baseURL: TARGETS.local.web, apiURL: TARGETS.local.api, target: "local" },
    },
    {
      name: "pixel7-chromium",
      testMatch: /landing-scroll\.spec\.js/,
      use: { ...devices["Pixel 7"], channel, baseURL: TARGETS.local.web, apiURL: TARGETS.local.api, target: "local" },
    },
  ],
  webServer: [
    server("api", "local", "http://127.0.0.1:8899/health"),
    server("web", "local", "http://127.0.0.1:4174/app"),
    server("api", "prod", "https://127.0.0.1:8443/health"),
    server("web", "prod", "https://127.0.0.1:4443/app"),
  ],
});
