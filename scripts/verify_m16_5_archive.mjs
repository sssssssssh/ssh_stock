import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Synthetic browser fixtures: no real LLM, market data or user database.
const require = createRequire(resolve("frontend/package.json"));
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH || require.resolve("playwright")).href);
const out = resolve("docs/assets/m16-5");
await mkdir(out, { recursive: true });
const created = "2026-10-13T00:00:00Z";
const summary = id => ({ report_id: id, report_type: "market_review", title: `Synthetic ${id}`,
  report_version: id === "legacy" ? "m16.4-v1" : "m16.5-v1", source_chat_id: "chat",
  source_message_id: "message", source_answer_status: "COMPLETED", snapshot_hash: "a".repeat(64),
  as_of_date: "2026-01-02", archived_at: null, created_at: created });
const evidence = Array.from({ length: 22 }, (_, index) => ({ evidence_id: `synthetic-${index}-${"a".repeat(64)}`,
  tool_call_id: "actual-call", tool_name: "opportunity.list", tool_version: "1.0", entity_id: `stock-${index}`,
  as_of_date: "2026-01-02", record_path: `records.${index}`, created_at: created, content_hash: "a".repeat(64) }));
const meta = { archive_status: "COMPLETE", manifest_id: "synthetic-manifest", manifest_hash: "a".repeat(64),
  manifest_version: "m16.5-archive-v1", source_turn_id: "synthetic-turn", reproduction_level: "FROZEN_FACT_RECHECK",
  required_evidence_count: 22, archived_evidence_count: 22, integrity: { status: "VERIFIED", policy_version: "m16.5-integrity-v1" },
  calculation_reproduced: false, warnings: ["CALCULATION_NOT_REEXECUTED"], limitations: ["HISTORICAL_TOOL_RESULT_ONLY"], total: 22 };
const unavailable = { ...meta, archive_status: "UNAVAILABLE", manifest_id: null, manifest_hash: null,
  reproduction_level: "SNAPSHOT_ONLY", required_evidence_count: 0, archived_evidence_count: 0,
  integrity: { status: "UNVERIFIABLE" }, warnings: ["ARCHIVE_UNAVAILABLE", "REPLAY_UNAVAILABLE"], total: 0 };
const fact = { path: "records.0.score", value: "60.000000000000000001", unit: "score", entity: "stock-0",
  trade_date: "2026-01-02", sample_role: "LIVE" };
const claim = { claim_id: "c1", claim_type: "FACT", text: "Synthetic frozen score", quality_status: "PASS",
  evidence_ids: [evidence[0].evidence_id], structured_facts: [fact], reason_codes: [] };
const report = id => ({ ...summary(id), source_contract: { snapshot_level: id === "legacy" ? "CLAIM_SNAPSHOT_ONLY" : "FROZEN_TOOL_EVIDENCE" },
  snapshot: { claims: [claim], citations: [{ marker: "E1", evidence_id: evidence[0].evidence_id,
    evidence_version: "v2", tool_name: "opportunity.list", entity_id: "stock-0", as_of_date: "2026-01-02" }],
    sections: [{ section_id: "facts", title: "冻结事实", claim_ids: ["c1"], items: [] }], charts: [],
    rejected_claims: [], warnings: ["SERIES_NOT_AVAILABLE"] } });
let mode = "verified";
const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL || undefined });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url()), path = url.pathname.replace("/api/v1", "");
    const ok = (data, metadata = {}) => route.fulfill({ json: { code: 0, message: "ok", data, meta: metadata } });
    if (path === "/auth/me") return ok({ id: "synthetic-owner", username: "synthetic-owner", must_change_password: false });
    if (path === "/agent/reports") return ok([summary("new"), summary("legacy")], { total: 2 });
    if (path.match(/^\/agent\/reports\/[^/]+$/)) return ok(report(path.split("/").at(-1)));
    if (path.endsWith("/evidence")) {
      if (path.includes("/legacy/")) return ok([], unavailable);
      await new Promise(done => setTimeout(done, 80));
      const offset = Number(url.searchParams.get("offset"));
      return ok(evidence.slice(offset, offset + 20), meta);
    }
    if (path.includes("/evidence/")) return ok({ ...meta, ...evidence[0], arguments_summary: { trade_date: "2026-01-02" },
      arguments_hash: "b".repeat(64), registry_schema_hash: "c".repeat(64), config_hash: "d".repeat(64),
      source_hash: "e".repeat(64), projection_version: "m16.5-content-projector-v1", frozen_facts: [{ claim_id: "c1", ...fact }] });
    if (path.endsWith("/verify")) {
      if (mode === "network") return route.abort("failed");
      if (mode === "integrity") return route.fulfill({ status: 409, json: { detail: { code: "ARCHIVE_INTEGRITY_MISMATCH" } } });
      const state = mode === "mismatch" ? "MISMATCH" : "VERIFIED";
      return ok({ ...meta, verification_level: state === "VERIFIED" ? "FACT_REVERIFIED" : state,
        fact_recheck: { status: state, checked_claim_count: 1, results: [{ claim_id: "c1", status: state,
          reason_codes: state === "MISMATCH" ? ["VALUE_MISMATCH"] : [],
          failed_fields: state === "MISMATCH" ? [{ path: "records.0.score", code: "VALUE_MISMATCH" }] : [] }] } });
    }
    if (path === "/agent/report-comparisons") return ok({ policy_version: "m16.5-report-comparison-v3",
      state: "CONTEXT_REQUIRED", reason_codes: ["PAIR_MAPPING_NOT_PROVIDED"],
      display_safety: { legacy_policy: false, delta_allowed: false, warnings: [] }, result: { facts: [{ delta: "999999" }] },
      display_result: { facts: [], unmatched_facts: { left: [{ value: "60", trade_date: "2026-01-02",
        metric_identity: { entity_id: "A", metric_id: "opportunity.list:score", unit: "score", sample_role: "LIVE" } }],
        right: [{ value: "70", trade_date: "2026-01-02", metric_identity: { entity_id: "B", metric_id: "opportunity.list:score", unit: "score", sample_role: "LIVE" } }] } } });
    if (path === "/agent/status") return ok({ llm_enabled: false, registry_version: "m16.5", tool_count: 9 });
    if (path === "/agent/chats") return ok([{ chat_id: "chat", title: "Synthetic archived chat", status: "ARCHIVED", created_at: created, updated_at: created }], { total: 1 });
    if (path === "/agent/chats/chat") return ok({ chat_id: "chat", title: "Synthetic archived chat", status: "ARCHIVED",
      messages: [{ message_id: "message", role: "ASSISTANT", content: "Synthetic verified", status: "COMPLETED", sequence_no: 2,
        source_request_id: "synthetic-request", created_at: created, metadata: { answer_status: "COMPLETED", verified_claims: [claim], citations: [] } }] }, { total: 1, has_more: false });
    if (path.endsWith("/archive")) return ok({ ...meta, evidence: evidence.slice(0, 2) });
    if (path === "/dashboard/summary") return ok({ sector_heat_top: [], signal_counts: [] });
    if (path === "/system/status" || path === "/system/runtime") return ok({});
    return ok([]);
  });
  await page.goto(process.env.WORKBENCH_URL || "http://127.0.0.1:5173");
  await page.locator(".nav-button").filter({ hasText: "研究报告" }).click();
  const open = id => page.locator(".report-list button").filter({ hasText: `Synthetic ${id}` });
  await open("new").focus(); await page.keyboard.press("Enter");
  try { await page.getByText("归档：COMPLETE", { exact: true }).waitFor(); }
  catch (error) { console.log(JSON.stringify({ text: await page.locator(".report-workbench").innerText(), errors })); throw error; }
  await page.getByRole("button", { name: "从冻结证据复核", exact: true }).click();
  await page.getByText("FACT_REVERIFIED · 1 项", { exact: true }).waitFor();
  await page.getByRole("button", { name: "更多证据", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll(".archive-evidence article").length === 22);
  await page.getByRole("button", { name: "查看冻结事实", exact: true }).first().click();
  await page.getByRole("region", { name: "冻结事实详情" }).waitFor();
  assert.match(await page.locator(".archive-detail").innerText(), /60.000000000000000001/);
  await page.screenshot({ path: resolve(out, "desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  await page.locator(".archive-panel").evaluate(el => el.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: resolve(out, "mobile.png") });
  await page.locator(".archive-detail").evaluate(el => el.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: resolve(out, "mobile-detail.png") });
  await page.getByRole("button", { name: "关闭详情", exact: true }).click();
  for (const next of ["mismatch", "integrity", "network"]) {
    mode = next;
    await page.getByRole("button", { name: "从冻结证据复核", exact: true }).click();
    if (next === "mismatch") await page.getByText("事实复核：MISMATCH", { exact: true }).waitFor();
    else await page.locator(".archive-panel [role='alert']").waitFor();
    assert.doesNotMatch(await page.locator(".archive-panel").innerText(), /FACT_REVERIFIED/);
  }
  mode = "verified";
  await open("legacy").click();
  await page.getByText("历史报告仅含 Claim 快照，无法恢复当次工具原始响应", { exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "从冻结证据复核", exact: true }).isDisabled(), true);
  await page.locator(".report-compare select").nth(0).selectOption("new");
  await page.locator(".report-compare select").nth(1).selectOption("legacy");
  await page.getByRole("button", { name: "比较", exact: true }).click();
  await page.getByText("PAIR_MAPPING_NOT_PROVIDED", { exact: true }).waitFor();
  assert.doesNotMatch(await page.locator(".comparison-result").innerText(), /999999/);
  await page.locator(".archive-panel").evaluate(el => el.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: resolve(out, "legacy-mobile.png") });
  await page.locator(".nav-button").filter({ hasText: "智能研究" }).click();
  await page.locator(".agent-chat-item").click();
  await page.getByRole("button", { name: "查看证据归档", exact: true }).click();
  await page.getByText("归档：COMPLETE", { exact: true }).waitFor();
  await page.getByRole("button", { name: "关闭归档面板", exact: true }).click();
  await page.locator(".agent-workbench .archive-panel").waitFor({ state: "detached" });
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ new_report_verified: true, legacy_unavailable: true, owner_fixture_only: true,
    mismatch_and_network_fail_closed: true, precise_decimal: true, paged_22_evidence: true,
    keyboard_open: true, archived_chat_read: true, panel_cleanup: true, desktop_1440: true,
    mobile_390_overflow: false, audit_delta_hidden: true, errors }));
} finally { await browser.close(); }
