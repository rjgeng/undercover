import { expect, test } from "@playwright/test";

test("the agent's instructions are read only", async ({ page }) => {
  await page.goto("/#/instructions");
  await expect(
    page.getByText(/You decide travel insurance claims/),
  ).toBeVisible();
  await expect(page.getByText("Policy wording, version 2026.1")).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});
