import { type APIRequestContext, expect, test } from "@playwright/test";

// The test stands in for the queue agent by calling the API through the
// dashboard's proxy, and watches the queue page follow the run.

async function send(
  request: APIRequestContext,
  method: "post" | "put",
  path: string,
  data: object,
) {
  const response = await request[method](path, { data });
  expect(response.ok()).toBe(true);
  return (await response.json()) as { run_id: string };
}

function todos(first: string, second: string) {
  return {
    todos: [
      { content: "CLM-1005, a delayed bag", status: first },
      { content: "CLM-1006, a stolen camera", status: second },
    ],
  };
}

test("the queue page follows a run", async ({ page, request }) => {
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Agent run" });
  const items = panel.getByRole("listitem");

  const { run_id } = await send(request, "post", "/api/runs", { cap: 2 });
  await send(
    request,
    "put",
    `/api/runs/${run_id}/todos`,
    todos("todo", "todo"),
  );
  await expect(panel.getByText(run_id)).toBeVisible();
  await expect(panel.getByText("Running")).toBeVisible();
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText("To do");

  await send(
    request,
    "put",
    `/api/runs/${run_id}/todos`,
    todos("in_progress", "todo"),
  );
  await expect(items.nth(0)).toContainText("In progress");

  for (const claimId of ["CLM-1005", "CLM-1006"]) {
    await send(request, "post", `/api/runs/${run_id}/claims`, {
      claim_id: claimId,
    });
    await send(request, "post", `/api/claims/${claimId}/start`, {
      thread_id: "e2e-run",
    });
    await send(request, "post", `/api/claims/${claimId}/decision`, {
      decision: "refer",
      payout: 0,
      section: "Manual section 5, Documents",
      reason: "A document is missing.",
    });
  }
  await send(
    request,
    "put",
    `/api/runs/${run_id}/todos`,
    todos("handler", "handler"),
  );
  await expect(items.nth(1)).toContainText("Left for a handler");

  await send(request, "post", `/api/runs/${run_id}/finish`, {
    summary: "Two claims referred for missing documents.",
  });
  await expect(panel.getByText("Finished")).toBeVisible();
  await expect(
    panel.getByText("Two claims referred for missing documents."),
  ).toBeVisible();
});
