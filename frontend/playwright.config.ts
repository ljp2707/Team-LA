import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

/*
 * The CSP browser test (findings F28). Run it with: npm run test:e2e
 *
 * It starts three copies of the backend on the built app, each signed in as one person
 * through DEV_LOGIN_EMAIL, with CSP_MODE=enforce and the in-memory fake Airtable from the
 * backend tests (backend/tests/e2e_server.py). Nothing reaches the real Airtable base,
 * Google or Gmail.
 */

// The backend's virtual environment if there is one (Windows or Linux), else python on PATH (CI).
const python =
  process.env.E2E_PYTHON ??
  [".venv/Scripts/python.exe", ".venv/bin/python"].map((p) => `../backend/${p}`).find((p) => existsSync(p)) ??
  "python";

export const PEOPLE = {
  admin: { email: "admin@example.org", port: 8301 },
  staff: { email: "staff@example.org", port: 8302 },
  partner: { email: "partner@example.org", port: 8303 },
} as const;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  use: { browserName: "chromium", trace: "off" },
  webServer: Object.values(PEOPLE).map(({ email, port }) => ({
    command: `"${python}" ../backend/tests/e2e_server.py --email ${email} --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  })),
});
