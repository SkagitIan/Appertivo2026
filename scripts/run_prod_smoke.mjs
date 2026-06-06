import { spawnSync } from "node:child_process";

const baseUrl = process.env.E2E_PROD_BASE_URL || "https://appertivo2026-production.up.railway.app";
const result = spawnSync(
  "npx",
  ["playwright", "test", "tests/e2e/prod-smoke.spec.js", "--config=playwright.config.js"],
  {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      E2E_BASE_URL: baseUrl,
      E2E_SKIP_WEBSERVER: "1",
    },
  }
);

process.exit(result.status ?? 1);

