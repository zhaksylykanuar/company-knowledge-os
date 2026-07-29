import { expect, test } from "@playwright/test";

const PRODUCT_PATHS = [
  "/dashboard",
  "/company-brain",
  "/ask",
  "/settings"
] as const;

function requiredCredential(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for authenticated browser smoke`);
  }
  return value;
}

test("founder session survives reload and four primary zones stay clean", async ({
  page
}) => {
  const consoleFailures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      consoleFailures.push(message.type());
    }
  });
  page.on("pageerror", () => {
    consoleFailures.push("pageerror");
  });

  await page.goto("/login");
  await page
    .locator('input[name="username"]')
    .fill(requiredCredential("FOUNDEROS_E2E_LOGIN_EMAIL"));
  await page
    .locator('input[name="password"]')
    .fill(requiredCredential("FOUNDEROS_E2E_LOGIN_PASSWORD"));
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/);

  for (const path of PRODUCT_PATHS) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`${path.replace("/", "\\/")}$`));
    const hasHorizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth
    );
    expect(hasHorizontalOverflow).toBe(false);
  }

  expect(consoleFailures).toEqual([]);
  await page.evaluate(async () => {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include"
    });
  });
});
