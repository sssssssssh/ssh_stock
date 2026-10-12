import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Synthetic HTTP fixtures only; no model, Agent tools, or user database are accessed.
const require = createRequire(resolve("frontend/package.json"));
const modulePath = process.env.PLAYWRIGHT_MODULE_PATH || require.resolve("playwright");
const { chromium } = await import(pathToFileURL(modulePath).href);
const outputDir = resolve("docs/assets/m16-4-1");
await mkdir(outputDir, { recursive: true });
const created = "2026-10-12T00:00:00Z";
const summary = (id) => ({ report_id: id, report_type: "market_review", title: `Synthetic ${id}`,
  report_version: "m16.4-v1", source_chat_id: "synthetic-chat", source_message_id: "synthetic-message",
  as_of_date: "2026-10-10", source_answer_status: "COMPLETED", snapshot_hash: "a".repeat(64),
  created_at: created, archived_at: null });
const claims = ["000002.SZ", "000001.SZ"].map((entity, index) => ({
  claim_id: `claim-${index}`, claim_type: "FACT", text: `Synthetic score ${entity}`,
  evidence_ids: [`synthetic-evidence-${entity}-${"a".repeat(80)}`], quality_status: "PASS",
  structured_facts: [{ path: `records.${index}.score`, entity, value: String(10 + index),
    unit: "score", trade_date: "2026-10-10", sample_role: "LIVE" }]
}));
const bar = { chart_id: "bar", chart_type: "bar", title: "冻结同日分数", unit: "score",
  metric_id: "opportunity.list:score", trade_date: "2026-10-10", sample_role: "LIVE",
  entity_kind: "stock", columns: ["entity", "value"],
  rows: claims.map((claim) => [claim.structured_facts[0].entity, claim.structured_facts[0].value]) };
const detail = (id) => ({ ...summary(id), source_contract: { snapshot_level: "CLAIM_SNAPSHOT_ONLY",
  limitations: ["SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"] }, snapshot: {
  claims, citations: claims.map((claim) => ({ marker: "E", evidence_id: claim.evidence_ids[0],
    evidence_version: "v2", tool_name: "opportunity.list", entity_id: claim.structured_facts[0].entity,
    as_of_date: "2026-10-10" })),
  sections: [{ section_id: "facts", title: "已验证事实", claim_ids: claims.map((claim) => claim.claim_id), items: [] }],
  charts: id === "report-1" ? [bar, { ...bar, chart_id: "line", chart_type: "line", title: "无完整日序列" }]
    : [{ ...bar, unit: "mixed" }],
  rejected_claims: [], warnings: ["SERIES_NOT_AVAILABLE", "REPLAY_UNAVAILABLE"]
} });
let mode = "legacy";
const browser = await chromium.launch({ headless: true,
  channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL || undefined });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const ok = (data, meta = {}) => route.fulfill({ json: { code: 0, message: "ok", data, meta } });
    if (path === "/auth/me") return ok({ username: "synthetic-owner", must_change_password: false });
    if (path === "/agent/reports") return ok([summary("report-1"), summary("report-2")], { total: 2 });
    if (path === "/agent/reports/report-1" || path === "/agent/reports/report-2") return ok(detail(path.split("/").at(-1)));
    if (path === "/agent/report-comparisons") return ok({ policy_version: mode === "legacy"
      ? "m16.2.2-comparison-v1" : "m16.4.1-report-comparison-v2",
      state: mode === "legacy" ? "COMPARABLE" : "INCOMPATIBLE", reason_codes: ["EXACT_M14_BUNDLE_REQUIRED"],
      display_safety: { legacy_policy: mode === "legacy", delta_allowed: false, warnings: [] },
      result: { facts: [{ metric_key: "synthetic-metric", left: "10", right: "11", delta: "999", pair_status: "INCOMPATIBLE" }] } });
    if (path === "/dashboard/summary") return ok({ trade_date: "2026-10-10", sector_heat_top: [], signal_counts: [] });
    if (path.startsWith("/system/status") || path.startsWith("/system/runtime")) return ok({});
    return ok([]);
  });
  await page.goto(process.env.WORKBENCH_URL || "http://127.0.0.1:5173");
  await page.locator(".nav-button").filter({ hasText: "研究报告" }).click();
  const open = (id) => page.locator(".report-list button").filter({ hasText: `Synthetic ${id}` });
  await open("report-1").focus();
  await page.keyboard.press("Enter");
  try {
    await page.locator(".bar-chart svg").waitFor();
  } catch (error) {
    console.log(JSON.stringify({ text: await page.locator(".report-workbench").innerText(), errors }));
    throw error;
  }
  assert.match(await page.locator(".report-detail").innerText(), /SERIES_NOT_AVAILABLE/);
  assert.equal(await page.locator(".bar-chart svg").count(), 1, "line must not render");
  await page.screenshot({ path: resolve(outputDir, "desktop.png"), fullPage: true });
  await page.locator(".report-compare select").nth(0).selectOption("report-1");
  await page.locator(".report-compare select").nth(1).selectOption("report-2");
  await page.getByRole("button", { name: "比较", exact: true }).click();
  await page.locator(".comparison-result").waitFor();
  assert.match(await page.locator(".comparison-result").innerText(), /旧版比较策略/);
  assert.doesNotMatch(await page.locator(".comparison-result").innerText(), /999/);
  mode = "incompatible";
  await page.getByRole("button", { name: "比较", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".comparison-result")?.textContent.includes("INCOMPATIBLE"));
  assert.doesNotMatch(await page.locator(".comparison-result").innerText(), /999/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  await page.screenshot({ path: resolve(outputDir, "mobile.png"), fullPage: true });
  await open("report-2").click();
  await page.getByRole("status").filter({ hasText: "CHART_UNIT_OR_DATA_INVALID" }).waitFor();
  assert.equal(await page.locator(".bar-chart svg").count(), 0, "old chart must be disposed");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ frozen_bar: true, line_disabled: true, legacy_delta_hidden: true,
    incompatible_delta_hidden: true, mobile_overflow: false, keyboard_open: true,
    invalid_bar_fallback: true, browser_errors: errors }));
} finally {
  await browser.close();
}
