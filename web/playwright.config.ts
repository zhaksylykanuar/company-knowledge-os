import { defineConfig, devices } from "@playwright/test";

const baseURL =
  process.env.FOUNDEROS_E2E_BASE_URL?.trim() || "http://127.0.0.1:3000";
const parsedBaseURL = new URL(baseURL);
if (
  parsedBaseURL.protocol !== "http:" ||
  parsedBaseURL.hostname !== "127.0.0.1" ||
  parsedBaseURL.username ||
  parsedBaseURL.password ||
  parsedBaseURL.pathname !== "/" ||
  parsedBaseURL.search ||
  parsedBaseURL.hash
) {
  throw new Error(
    "FOUNDEROS_E2E_BASE_URL must be a plain 127.0.0.1 HTTP origin"
  );
}

export default defineConfig({
  testDir: "./e2e",
  outputDir: ".playwright-artifacts",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["line"]],
  use: {
    baseURL,
    screenshot: "off",
    trace: "off",
    video: "off"
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] }
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"] }
    }
  ]
});
