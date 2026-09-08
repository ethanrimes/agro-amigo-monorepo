import { defineConfig, devices } from "@playwright/test";
const remote = process.env.PLAYWRIGHT_BASE_URL;
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 20000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: remote || "http://127.0.0.1:3002",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: remote
    ? undefined
    : {
        command: "npm run dev -- -p 3002 -H 127.0.0.1",
        url: "http://127.0.0.1:3002",
        reuseExistingServer: true,
        timeout: 180000,
      },
  projects: [
    {
      name: "iphone-webkit",
      testMatch: ["layout.spec.ts", "explore.spec.ts", "farms.spec.ts", "weather-view.spec.ts", "farm-location.spec.ts"],
      use: { ...devices["iPhone 13"] },
    },
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
});
