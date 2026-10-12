import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

// All API data is synthetic; this check never submits a real research request.
const require = createRequire(resolve("frontend/package.json"));
const modulePath = process.env.PLAYWRIGHT_MODULE_PATH || require.resolve("playwright");
const { chromium } = await import(pathToFileURL(modulePath).href);
const baseUrl = process.env.WORKBENCH_URL || "http://127.0.0.1:5173";
const outputDir = resolve("docs/assets/m16-3-1");
await mkdir(outputDir, { recursive: true });

const created = "2026-10-12T01:00:00Z";
const chat = { chat_id: "chat-a", title: "201-message acceptance", status: "ACTIVE", created_at: created, updated_at: created };
const citation = {
  marker: "E1", evidence_id: "synthetic-window-evidence", evidence_version: "v2",
  tool_name: "walk_forward.window_lineage", entity_id: "study-a:window:301", as_of_date: "2026-01-02",
  navigation: { view: "walk_forward", study_id: "study-a", validation_id: "validation-a", window_no: 301, source_tool: "walk_forward.window_lineage" }
};
const stockCitation = {
  marker: "E2", evidence_id: "synthetic-stock-evidence", evidence_version: "v2",
  tool_name: "opportunity.list", entity_id: "000001.SZ", as_of_date: "2026-01-02",
  navigation: { view: "long", ts_code: "000001.SZ", trade_date: "2026-01-02", source_tool: "opportunity.list" }
};
const staleStockCitation = { ...stockCitation, marker: "E3", evidence_id: "synthetic-older-stock-evidence", as_of_date: "2026-01-01", navigation: { ...stockCitation.navigation, trade_date: "2026-01-01" } };
const row = (sequence, content = `Synthetic history ${sequence}`) => ({
  message_id: `message-${sequence}`, role: sequence % 2 ? "ASSISTANT" : "USER",
  content, status: "COMPLETED", sequence_no: sequence, created_at: created,
  metadata: sequence % 2 ? {
    answer_status: sequence === 201 ? "PARTIAL_VERIFIED" : "COMPLETED",
    verified_claims: [], rejected_claims: sequence === 201 ? [{ claim_id: "rejected", reason_codes: ["VALUE_MISMATCH"] }] : [],
    citations: [citation], warnings: [], tool_calls: []
  } : {}
});
const rows = Array.from({ length: 201 }, (_, index) => row(index + 1));
let mode = "lost-before-commit";
let lost = false;
let savedTurn = null;
const posts = [];
const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL || undefined });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const ok = (data, meta = {}) => route.fulfill({ json: { code: 0, message: "ok", data, meta } });
    if (path === "/auth/me") return ok({ username: "synthetic-owner", must_change_password: false });
    if (path === "/agent/status") return ok({ llm_enabled: true, tool_count: 9, registry_version: "m16.3-v1", read_only: true });
    if (path === "/agent/chats") return ok([chat], { total: 1 });
    if (path === "/agent/chats/chat-a/messages") {
      const body = request.postDataJSON();
      posts.push(body);
      if (!lost && mode === "lost-before-commit") {
        lost = true;
        return route.abort("failed");
      }
      const user = { ...row(rows.length + 1, body.content), role: "USER", metadata: {} };
      const answer = { ...row(rows.length + 2, "Recovered synthetic answer"), role: "ASSISTANT", metadata: { answer_status: "COMPLETED", citations: [citation, stockCitation, staleStockCitation] } };
      rows.push(user, answer);
      savedTurn = { chat_id: "chat-a", request_id: body.request_id, content: body.content, user_message_id: user.message_id, assistant_message_id: answer.message_id, status: "COMPLETED", started_at: created };
      if (mode === "lost-after-commit") return route.abort("failed");
      return ok({ answer_status: "COMPLETED" });
    }
    if (path.startsWith("/agent/chats/chat-a/turns/")) {
      if (savedTurn) return ok(savedTurn);
      return route.fulfill({ status: 404, json: { detail: { code: "TURN_NOT_FOUND", message: "missing synthetic turn" } } });
    }
    if (path === "/agent/chats/chat-a") {
      const limit = Number(url.searchParams.get("limit") || 100);
      const before = Number(url.searchParams.get("before_sequence") || rows.length + 1);
      const selected = rows.filter((item) => item.sequence_no < before).slice(-limit);
      return ok({ ...chat, messages: selected, active_turn: null }, {
        total: rows.length, limit, offset: 0, has_more: selected[0]?.sequence_no > 1,
        next_cursor: selected[0]?.sequence_no > 1 ? selected[0].sequence_no : null
      });
    }
    if (path.includes("/walk-forwards/study-a/validations/validation-a/windows")) {
      assert.equal(url.searchParams.get("window_no"), "301");
      return ok([{ window_no: 301, selected_train_run_id: "train-a", oos_run_id: "oos-a" }], { total: 1 });
    }
    if (path.includes("/walk-forwards/")) return ok({ status: "SUCCESS", window_count: 1001 });
    if (path === "/dashboard/summary") return ok({ trade_date: "2026-01-02", sector_heat_top: [], signal_counts: [] });
    if (path.startsWith("/system/status") || path.startsWith("/system/runtime")) return ok({});
    if (path === "/stocks/right-side") return ok([{ ts_code: "000001.SZ", trade_date: "2026-01-02", state: "S3", name: "Synthetic stock", reason_codes: [] }]);
    return ok([]);
  });

  await page.goto(baseUrl);
  await page.locator(".nav-button").filter({ hasText: "智能研究" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".agent-message").length === 50);
  assert.match(await page.locator(".agent-message").last().innerText(), /201/);
  await page.locator(".agent-stream").evaluate((element) => { element.scrollTop = element.scrollHeight; });
  const desktopLayout = await page.locator(".agent-layout").evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const composer = element.querySelector(".agent-composer").getBoundingClientRect();
    const stream = element.querySelector(".agent-stream");
    return { composerWithinPanel: composer.bottom <= bounds.bottom + 1, scrollable: stream.scrollHeight > stream.clientHeight };
  });
  assert.equal(desktopLayout.composerWithinPanel, true, "composer clipped by the message list");
  assert.equal(desktopLayout.scrollable, true, "message list must scroll within its panel");
  await page.screenshot({ path: resolve(outputDir, "desktop.png"), fullPage: true });

  for (let attempt = 0; attempt < 4; attempt += 1) {
    await page.getByRole("button", { name: "加载更早消息", exact: true }).click();
    await page.waitForFunction((count) => document.querySelectorAll(".agent-message").length === count, Math.min(100 + attempt * 50, 201));
  }
  const history = await page.locator(".agent-answer").allTextContents();
  assert.equal(history.length, 201);
  assert.equal(new Set(history).size, 201);
  await page.getByRole("textbox", { name: "研究问题" }).fill("Synthetic lost reply");
  await page.locator(".agent-composer button").click();
  await page.getByRole("button", { name: "沿用原请求重试", exact: true }).click();
  await page.waitForFunction(() => !document.querySelector(".agent-pending"));
  assert.equal(posts.length, 2);
  assert.deepEqual(posts[0], posts[1]);

  mode = "lost-after-commit";
  await page.getByRole("textbox", { name: "研究问题" }).fill("Synthetic committed reply");
  await page.locator(".agent-composer button").click();
  await page.waitForFunction(() => !document.querySelector(".agent-pending"));
  assert.equal(posts.length, 3);
  assert.equal(rows.length, 205);

  await page.getByRole("textbox", { name: "研究问题" }).fill("Draft preserved on return");
  await page.locator(".agent-citations button").filter({ hasText: "walk_forward.window_lineage" }).last().click();
  const savedScroll = await page.locator(".agent-stream").evaluate((element) => element.scrollTop);
  await page.getByRole("button", { name: "打开业务详情", exact: true }).click();
  await page.getByRole("heading", { name: "Walk-forward 窗口明细", exact: true }).waitFor();
  assert.match(await page.locator(".wf-detail").innerText(), /oos-a/);
  await page.getByRole("button", { name: "返回智能研究", exact: true }).click();
  assert.equal(await page.getByRole("textbox", { name: "研究问题" }).inputValue(), "Draft preserved on return");
  assert.equal(await page.locator(".agent-stream").evaluate((element) => element.scrollTop), savedScroll);

  await page.locator(".agent-citations button").filter({ hasText: "E2" }).last().click();
  await page.getByRole("button", { name: "打开业务详情", exact: true }).click();
  await page.locator(".research-highlight").waitFor();
  assert.match(await page.locator(".research-highlight").innerText(), /000001.SZ/);
  await page.locator(".nav-button").filter({ hasText: "智能研究" }).click();
  await page.locator(".agent-citations button").filter({ hasText: "E3" }).last().click();
  await page.getByRole("button", { name: "打开业务详情", exact: true }).click();
  assert.match(await page.locator(".navigation-strip").innerText(), /2026-01-01/);
  assert.equal(await page.locator(".research-highlight").count(), 0);
  await page.locator(".nav-button").filter({ hasText: "智能研究" }).click();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".agent-citations button").filter({ hasText: "walk_forward.window_lineage" }).last().click();
  await page.locator(".agent-evidence-pane.open").waitFor();
  await page.waitForFunction(() => {
    const pane = document.querySelector(".agent-evidence-pane.open");
    return pane && Math.abs(pane.getBoundingClientRect().right - window.innerWidth) < 1;
  });
  const actionsFit = await page.locator(".agent-evidence-detail").evaluate((detail) =>
    [...detail.querySelectorAll("button")].every((button) =>
      button.getBoundingClientRect().right <= window.innerWidth + 1
    )
  );
  assert.equal(actionsFit, true, "mobile evidence actions clipped");
  await page.screenshot({ path: resolve(outputDir, "mobile.png") });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, "mobile horizontal overflow");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ history_messages: 201, repeated_request_ids_equal: true, committed_lost_reply_posts: 1, precise_window: 301, mobile_overflow: false, browser_errors: errors, screenshots: ["desktop.png", "mobile.png"] }, null, 2));
  await context.close();
} finally {
  await browser.close();
}
