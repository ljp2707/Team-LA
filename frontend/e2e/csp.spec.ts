import { expect, test, type Page } from "@playwright/test";
import { PEOPLE } from "../playwright.config";

/*
 * Every page, as an admin, a staff member and a partner, with the Content-Security-Policy
 * enforced. Fails on any CSP violation, console error, uncaught error or failed request
 * (findings F28). Also opens the Nudge and Delete task dialogs and uses the My Tasks
 * filters, since dialogs and filters load code and styles that a page alone may not.
 */

type Problems = string[];

/** Record everything that should never happen on a page. */
async function watch(page: Page): Promise<Problems> {
  const problems: Problems = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      console.error(`CSP violation: ${e.effectiveDirective} blocked ${e.blockedURI}`);
    });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console error: ${msg.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`uncaught error: ${error.message}`));
  page.on("requestfailed", (request) => problems.push(`request failed: ${request.url()} ${request.failure()?.errorText}`));
  page.on("response", (response) => {
    if (response.status() >= 400) problems.push(`HTTP ${response.status()}: ${response.url()}`);
  });
  return problems;
}

async function signIn(page: Page, base: string) {
  const response = await page.goto(`${base}/auth/login`);
  expect(response?.ok()).toBeTruthy();
  await page.waitForLoadState("networkidle");
}

/** Open a page and wait until it has finished loading everything. */
async function visit(page: Page, base: string, path: string) {
  const response = await page.goto(`${base}${path}`);
  expect(response?.status(), `${path} status`).toBe(200);
  // The policy really is enforced on the page itself, not just report-only.
  expect(response?.headers()["content-security-policy"], `${path} CSP`).toContain("script-src 'self'");
  await page.waitForLoadState("networkidle");
  await expect(page.locator("#root")).not.toBeEmpty();
}

/** The self-hosted fonts load under the policy (Google Fonts is not allowed). */
async function expectFontsLoaded(page: Page) {
  const loaded = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family.replace(/"/g, ""));
  });
  expect(loaded).toContain("Figtree");
  expect(loaded).toContain("Bricolage Grotesque");
}

function select(page: Page, label: string) {
  return page.locator("label.inline-select", { hasText: label }).locator("select");
}

/**
 * Pick a My Tasks filter or sort and wait for the tasks it loads. Each choice fetches
 * /api/tasks/mine again; moving on before that finishes cancels it (net::ERR_ABORTED), which
 * the failed-request check rightly reports. waitForLoadState("networkidle") does not help
 * here: once the page has loaded it returns at once.
 */
async function choose(page: Page, label: string, value: string) {
  const loaded = page.waitForResponse((r) => r.url().includes("/api/tasks/mine"));
  await select(page, label).selectOption(value);
  await loaded;
}

test("admin: every page, the Nudge and Delete task dialogs, and the My Tasks filters", async ({ page }) => {
  const base = `http://127.0.0.1:${PEOPLE.admin.port}`;
  const problems = await watch(page);
  await signIn(page, base);

  for (const path of [
    "/",
    "/dashboard",
    "/projects",
    "/projects/new",
    "/projects/recProj",
    "/templates",
    "/users",
    "/assignments",
    "/assignments/recStaff",
    "/archive",
    "/audit",
    "/privacy",
    "/terms",
    "/not-authorized",
    "/no-such-page",
  ]) {
    await visit(page, base, path);
  }
  await expectFontsLoaded(page);

  // The Audit page shows the seeded admin action in plain words
  await visit(page, base, "/audit");
  await expect(page.getByRole("cell", { name: "Changed a person" })).toBeVisible();

  // Assignments, a person, then their task: where the Nudge button lives
  await visit(page, base, "/assignments/recStaff");
  await page.getByRole("link", { name: "Design flyer" }).first().click();
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/tasks\/recT2$/);

  await page.getByRole("button", { name: "Nudge" }).click();
  const nudge = page.getByRole("dialog");
  await expect(nudge).toContainText("Send a reminder to Sam about Design flyer?");
  await nudge.getByRole("textbox").fill("Can you finish this today?");
  await nudge.getByRole("button", { name: "Cancel" }).click();
  await expect(nudge).toBeHidden();

  await page.getByRole("button", { name: "Delete task" }).click();
  const remove = page.getByRole("dialog");
  await expect(remove).toContainText("Delete Design flyer?");
  await page.waitForLoadState("networkidle");
  await remove.getByRole("button", { name: "Cancel" }).click();
  await expect(remove).toBeHidden();

  // The status menu's Delete task on the program page
  await visit(page, base, "/projects/recProj");

  // My Tasks with every filter and sort; the choices go into the address
  await visit(page, base, "/my-tasks");
  await choose(page, "Sort by", "program");
  await choose(page, "Sort by", "location");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/sort=location/);
  await visit(page, base, "/my-tasks?show=overdue&sort=due");

  expect(problems, problems.join("\n")).toEqual([]);
});

test("staff: their pages and the My Tasks filters", async ({ page }) => {
  const base = `http://127.0.0.1:${PEOPLE.staff.port}`;
  const problems = await watch(page);
  await signIn(page, base);

  for (const path of ["/", "/my-tasks", "/projects", "/projects/recProj", "/tasks/recT2", "/privacy", "/terms"]) {
    await visit(page, base, path);
  }
  await expectFontsLoaded(page);

  await visit(page, base, "/my-tasks");
  await choose(page, "State", "WA");
  await choose(page, "City", "Seattle");
  await choose(page, "Program type", "Swim Safely");
  await choose(page, "Sort by", "location");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/state=WA/);
  await expect(page).toHaveURL(/city=Seattle/);
  await expect(page.getByText("Design flyer").first()).toBeVisible();
  // A refresh keeps the filters
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(select(page, "State")).toHaveValue("WA");

  // Staff never see the admin-only buttons
  await visit(page, base, "/tasks/recT2");
  await expect(page.getByRole("button", { name: "Nudge" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete task" })).toHaveCount(0);

  expect(problems, problems.join("\n")).toEqual([]);
});

test("partner: their program, task and My Tasks", async ({ page }) => {
  const base = `http://127.0.0.1:${PEOPLE.partner.port}`;
  const problems = await watch(page);
  await signIn(page, base);

  for (const path of ["/", "/projects", "/projects/recProj", "/tasks/recT6", "/my-tasks", "/privacy", "/terms"]) {
    await visit(page, base, path);
  }
  await expectFontsLoaded(page);

  expect(problems, problems.join("\n")).toEqual([]);
});
