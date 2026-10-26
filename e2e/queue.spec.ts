import { expect, test } from "@playwright/test";

const STATES = ["Waiting", "In progress", "Waiting for sign-off", "Decided"];

test("the queue shows every claim and where it stands", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("row")).toHaveCount(26);
  const tiles = page.getByRole("region", { name: "Claims by state" });
  for (const state of STATES) {
    await expect(tiles.getByText(state, { exact: true })).toBeVisible();
  }
  const counts = await tiles.locator(".count").allTextContents();
  expect(counts.map(Number).reduce((sum, count) => sum + count, 0)).toBe(25);
  const row = page.getByRole("row", { name: /CLM-1001/ });
  await expect(row).toContainText("$420.00");
  await expect(row).toContainText("Waiting");
});

test("the queue refreshes without a reload", async ({ page, request }) => {
  await page.goto("/");
  const row = page.getByRole("row", { name: /CLM-1005/ });
  await expect(row).toContainText("Waiting");
  const started = await request.post("/api/claims/CLM-1005/start", {
    data: { thread_id: "e2e-queue" },
  });
  expect(started.ok()).toBe(true);
  await expect(row).toContainText("In progress", { timeout: 3000 });
});
