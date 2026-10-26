import { expect, test } from "@playwright/test";

test("a claim shows in full", async ({ page }) => {
  await page.goto("/#/claims/CLM-1001");
  await expect(page.getByText(/^My flight home from Rome/)).toBeVisible();
  const items = page.getByRole("region", { name: "Items claimed" });
  await expect(items.getByRole("row")).toHaveCount(4);
  const documents = page.getByRole("region", { name: "Documents" });
  await expect(documents.getByRole("heading", { level: 3 })).toHaveCount(4);
  await expect(documents).toContainText("Flight MA 611");
  await expect(page.getByRole("region", { name: "Policy" })).toContainText(
    "Premium",
  );
  await expect(page.getByRole("region", { name: "Customer" })).toContainText(
    "CLM-0412",
  );
});

test("the agent's steps appear as it works", async ({ page, request }) => {
  await page.goto("/#/claims/CLM-1004");
  await expect(page.getByText("No steps yet.")).toBeVisible();
  await request.post("/api/claims/CLM-1004/start", {
    data: { thread_id: "e2e-steps" },
  });
  for (const title of ["Read the claim", "Read the policy"]) {
    await request.post("/api/claims/CLM-1004/steps", {
      data: { kind: "tool", title, detail: "{}" },
    });
  }
  const steps = page
    .getByRole("region", { name: "The agent's steps" })
    .getByRole("listitem");
  await expect(steps).toHaveText([/Read the claim/, /Read the policy/]);
});

test("a handler signs off a payout over $1,000", async ({ page, request }) => {
  await request.post("/api/claims/CLM-1002/start", {
    data: { thread_id: "e2e-sign-off" },
  });
  await request.post("/api/claims/CLM-1002/decision", {
    data: {
      decision: "approve",
      payout: 1150,
      reasons: "A covered loss.",
      policy_section: "Section 5, Baggage and Personal Effects",
    },
  });
  const payment = await request.post("/api/claims/CLM-1002/payment", {
    data: { amount: 1150 },
  });
  expect(payment.status()).toBe(403);

  await page.goto("/#/claims/CLM-1002");
  const status = page.locator(".title .badge");
  await expect(status).toHaveText("Waiting for sign-off");
  await page.getByLabel("Handler").selectOption({ label: "Dana Whitfield" });
  await page
    .getByRole("button", { name: "Sign off and pay $1,150.00" })
    .click();
  await expect(status).toHaveText("Decided");
  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toContainText("Signed off by Dana Whitfield");
  await expect(decision).toContainText("Paid $1,150.00");
});
