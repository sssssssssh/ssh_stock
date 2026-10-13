// Synthetic API projections, actual Vue components and browser fetch/rendering.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = process.env.BROWSER_ARTIFACT_DIR || path.join(root, 'frontend', 'coverage', 'browser');
const hash = 'a'.repeat(64);
const contractReference = { manifest_id: 'child', manifest_hash: hash, policy_version: 'm16.6-contract-manifest-v1',
  contract_ids_hash: hash, contract_refs_hash: hash, contract_count: 21, contract_scope: ['M14_EXACT_BUNDLE'], gap_codes: [], reproduction_level: 'FROZEN_CONTRACT_RECHECK' };
const check = { archive_integrity: { status: 'VERIFIED' }, frozen_fact_recheck: { status: 'VERIFIED' },
  contract_integrity: { status: 'VERIFIED' }, contract_semantics: { status: 'VERIFIED', reason_codes: [] },
  comparison_permission: { allowed: false }, calculation_reproduced: false, results: [] };
const summaries = ['report-1', 'report-2', 'legacy'].map(report_id => ({ report_id, report_type: 'strategy_review',
  report_version: report_id === 'legacy' ? 'm16.5-report-v1' : 'm16.6-report-v1', title: report_id === 'legacy' ? '历史报告' : `冻结研究 ${report_id}`,
  source_chat_id: 'synthetic-chat', source_message_id: 'synthetic-message', as_of_date: '2026-10-10', source_answer_status: 'COMPLETED',
  snapshot_hash: hash, archived_at: null, created_at: '2026-10-13T00:00:00Z' }));
const rows = Array.from({ length: 21 }, (_, i) => ({ contract_id: `contract-${i}`, contract_kind: i % 3 ? 'M14_EXACT_BUNDLE' : 'M15_WINDOW_LINEAGE',
  subject_id: `synthetic-long-identity-${'x'.repeat(70)}-${i}`, role: i % 3 ? 'TRAIN' : 'STUDY', schema_version: 'm16.6-m14-bundle-v1',
  contract_hash: hash, tool_result_archive_id: `tool-${i}`, status: 'VERIFIED', reason_codes: [] }));
function report(id) {
  const summary = summaries.find(row => row.report_id === id);
  return { ...summary, source_turn_id: 'turn', parent_report_id: null,
    source_contract: { snapshot_level: 'FROZEN_TOOL_EVIDENCE' },
    snapshot: { claims: [{ claim_id: 'claim', claim_type: 'FACT', text: '冻结事实', evidence_ids: ['synthetic-evidence'] }],
      contract_reference: id === 'legacy' ? null : contractReference,
      sections: [{ section_id: 'facts', title: '已验证事实', claim_ids: ['claim'] }], charts: [], citations: [], warnings: [], rejected_claims: [] } };
}
function comparison(mode, denied) {
  return { comparison_id: 'synthetic-comparison', policy_version: 'm16.6-report-comparison-v4', state: denied ? 'CONTEXT_REQUIRED' : 'COMPARABLE',
    reason_codes: denied ? ['ASSUMPTIONS_REQUIRE_CONTEXT'] : [], display_safety: { legacy_policy: false, delta_allowed: !denied },
    result: { facts: [{ delta: 'AUDIT_DELTA_MUST_NOT_RENDER' }] },
    display_result: { comparison_mode: mode, comparison_permissions: { allowed: !denied },
      sample_context: { window_no: 1, train_start_date: '2026-01-02', train_end_date: '2026-01-12', oos_start_date: '2026-01-13', oos_end_date: '2026-01-23' },
      facts: [{ metric_key: 'annualized_return', left: '0.20', right: '0.08', delta: '0.123456', pair_status: 'COMPARABLE',
        comparison_permission: { allowed: !denied }, formula: 'TRAIN_MINUS_OOS' }], contract_check: { left: check, right: check } } };
}
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const vite = spawn(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
    { cwd: path.join(root, 'frontend'), windowsHide: true, stdio: 'pipe' });
  let serverOutput = '';
  vite.stdout.on('data', data => { serverOutput += data; }); vite.stderr.on('data', data => { serverOutput += data; });
  let browser;
  try {
    const url = `http://127.0.0.1:${port}/tests/browser/m16_6.html`;
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch { /* Startup polling. */ }
      await wait(200);
    }
    assert(ready, serverOutput);
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
    await fs.mkdir(output, { recursive: true });
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      let failVerify = true;
      await page.route('**/api/v1/**', async route => {
        const req = route.request(), url = new URL(req.url());
        let data, meta = {};
        if (url.pathname.endsWith('/verify-contracts')) {
          if (failVerify) { failVerify = false; return route.fulfill({ status: 409, json: { detail: { code: 'CONTRACT_HASH_MISMATCH' } } }); }
          data = check;
        } else if (url.pathname.endsWith('/report-comparisons')) {
          const body = req.postDataJSON(); data = comparison(body.comparison_mode, body.comparison_mode === 'DIFFERENT_ASSUMPTIONS');
        } else if (url.pathname.endsWith('/contracts')) {
          const offset = Number(url.searchParams.get('offset') || 0); data = rows.slice(offset, offset + 20); meta = { total: rows.length, check };
        } else if (url.pathname.includes('/contracts/')) {
          const id = url.pathname.split('/').pop(); data = { ...rows.find(row => row.contract_id === id), projection: { selected: { run_id: 'synthetic-run' },
            note: '<img src=x onerror="window.__xss=true">', source_hash: hash } };
        } else if (url.pathname.endsWith('/evidence')) {
          data = []; meta = { archive_status: 'COMPLETE', integrity: { status: 'VERIFIED' }, reproduction_level: 'FROZEN_FACT_RECHECK',
            archived_evidence_count: 1, required_evidence_count: 1, total: 0, warnings: [] };
        } else if (url.pathname.endsWith('/reports')) { data = summaries; meta = { total: summaries.length }; }
        else if (url.pathname.includes('/reports/')) { data = report(url.pathname.split('/').pop()); }
        else throw new Error('Unexpected API path: ' + url.pathname);
        await route.fulfill({ json: { code: 0, message: 'ok', data, meta } });
      });
      await page.goto(url);
      await page.getByRole('button', { name: /冻结研究 report-1/ }).click();
      await page.locator('.contract-panel tbody tr').first().waitFor();
      assert.equal(await page.locator('.contract-panel tbody tr').count(), 20);
      await page.getByRole('button', { name: '下一页', exact: true }).focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.querySelector('.contract-pagination')?.textContent.includes('21 / 21'));
      assert.equal(await page.locator('.contract-panel tbody tr').count(), 1);
      await page.locator('.contract-panel tbody button').click();
      await page.locator('.contract-detail pre').waitFor();
      assert.equal(await page.locator('.contract-detail img').count(), 0);
      assert.equal(await page.evaluate(() => window.__xss), undefined);
      await page.getByRole('button', { name: '复核合同', exact: true }).click();
      await page.locator('.contract-error').waitFor();
      assert((await page.locator('.contract-statuses').textContent()).includes('待核验'));
      await page.getByRole('button', { name: '重新加载' }).click();
      await page.waitForFunction(() => !document.querySelector('.contract-error'));
      await page.locator('.report-compare select').nth(0).selectOption('report-1');
      await page.locator('.report-compare select').nth(1).selectOption('report-2');
      await page.getByLabel('比较模式').selectOption('WINDOW_DEGRADATION');
      await page.getByRole('button', { name: '比较', exact: true }).click();
      await page.locator('.comparison-result').waitFor();
      assert((await page.locator('.comparison-result').textContent()).includes('TRAIN − OOS'));
      assert((await page.locator('.comparison-result').textContent()).includes('0.123456'));
      assert(!(await page.locator('.comparison-result').textContent()).includes('AUDIT_DELTA'));
      await page.locator('.comparison-result').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `comparison-${width}.png`), fullPage: true });
      await page.getByLabel('比较模式').selectOption('DIFFERENT_ASSUMPTIONS');
      await page.getByRole('button', { name: '比较', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.comparison-result')?.textContent.includes('CONTEXT_REQUIRED'));
      assert(!(await page.locator('.comparison-result').textContent()).includes('0.123456'));
      assert(!(await page.locator('.comparison-result').textContent()).includes('AUDIT_DELTA'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'page overflow at ' + width);
      await page.locator('.contract-panel').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `contract-${width}.png`), fullPage: true });
      await page.getByRole('button', { name: /历史报告/ }).click();
      await page.locator('.contract-empty').waitFor();
      assert.equal(await page.locator('.contract-panel button').count(), 0);
      assert.deepEqual(errors, []);
      console.log(`M16.6 browser ${width}px: pagination, keyboard, XSS, recovery, dual-permission, legacy passed`);
      await page.close();
    }
  } finally {
    if (browser) await browser.close();
    vite.kill();
    await new Promise(resolve => { if (vite.exitCode !== null) resolve(); else vite.once('exit', resolve); });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
