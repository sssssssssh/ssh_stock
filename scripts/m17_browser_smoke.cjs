const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'frontend', 'coverage', 'browser', 'm17');
const hash = 'a'.repeat(64);
const risk = { max_positions: 10, max_single_position_weight: '0.1', min_cash_ratio: '0.02',
  max_new_positions_per_day: 2, max_sector_weight: '0.3', max_theme_weight: '0.3', max_daily_turnover: '0.5' };
const account = { id: 'account', mode: 'PAPER', name: '前向模拟组合', state: 'ACTIVE', initial_cash: '1000000', benchmark_code: '999999.SH',
  first_trade_date: '2026-10-12', latest_trade_date: '2026-10-14', next_trade_date: '2026-10-15', config_snapshot_json: { paper: { risk } }, record_hash: hash };
const candidate = { ts_code: '000001.SZ', name: '合成验收证券', opportunity_stage: 'RIGHT_SIDE_NEW', opportunity_score: '82',
  industry_sector_id: 1, primary_theme_code: 'synthetic-theme', risk_codes: [], reason_codes: ['FROZEN_TEST_FACT'], close: '10' };
const observation = { id: 'observation', signal_date: '2026-10-14', record_hash: hash, data: { candidates: [candidate,
  { ...candidate, ts_code: '600000.SH', name: '<img src=x onerror="window.__paper_xss=true">', risk_codes: ['SUSPENDED'] }] } };
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port; await new Promise(resolve => probe.close(resolve));
  const vite = spawn(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
    { cwd: path.join(root, 'frontend'), windowsHide: true, stdio: 'pipe' });
  let logs = ''; vite.stdout.on('data', data => { logs += data; }); vite.stderr.on('data', data => { logs += data; });
  let browser;
  try {
    const url = `http://127.0.0.1:${port}/tests/browser/m17.html`;
    let ready = false;
    for (let i = 0; i < 100; i++) { try { if ((await fetch(url)).ok) { ready = true; break; } } catch {} await wait(200); }
    assert(ready, logs);
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
    await fs.mkdir(output, { recursive: true });
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      let approved = false, approvalPosts = 0, failStatus = false;
      const requests = [];
      await page.route('**/api/v1/**', async route => {
        const req = route.request(), url = new URL(req.url());
        let data, meta = { total: 1, limit: 20, offset: 0 };
        if (req.method() === 'POST') {
          requests.push({ path: url.pathname, body: req.postDataJSON() });
          assert(!url.pathname.includes('/broker') && !JSON.stringify(req.postDataJSON()).includes('LIVE'));
          if (url.pathname.endsWith('/approve')) {
            approvalPosts++;
            const body = req.postDataJSON(); assert.equal(body.confirmed, true); assert.equal(typeof body.target_weight, 'string');
            if (!approved) { approved = true; await wait(80); return route.abort('failed'); }
            data = { id: 'approval', state: 'APPROVED', mode: 'PAPER' };
          } else data = { id: 'queued', mode: 'PAPER', status: 'QUEUED' };
        } else if (url.pathname.endsWith('/paper/status')) {
          if (failStatus) { failStatus = false; return route.fulfill({ status: 503, json: { detail: { code: 'SOURCE_NOT_READY' } } }); }
          data = { enabled: true, schema_ready: true, auto_advance: false, auto_approve: false, default_risk: risk,
            business_date: '2026-10-14', latest_raw_date: '2026-10-14' };
        } else if (url.pathname.endsWith('/paper/accounts')) data = [account];
        else if (url.pathname.endsWith('/paper/accounts/account')) data = account;
        else if (url.pathname.endsWith('/performance')) data = { continuous: true, cumulative_return: '0.025', maximum_drawdown: '-0.05',
          realized_pnl: '1000', unrealized_pnl: '24000', cumulative_cost: '105', cumulative_turnover: '0.18', benchmark_status: 'BENCHMARK_UNAVAILABLE',
          financial_source_hash: hash, latest: { cash: '905000', market_value: '120000', total_assets: '1025000', nav: '1.025' },
          execution: { reached_orders: 2, filled_orders: 1, hypothetical_fill_rate: '0.5', blocked_reasons: { SUSPENDED: 1 }, stages: { RIGHT_SIDE_NEW: { orders: 2, filled: 1 } } },
          series: ['2026-10-12', '2026-10-13', '2026-10-14'].map((trade_date, i) => ({ trade_date,
            nav: ['1', '1.05', '1.025'][i], benchmark_nav: i === 1 ? null : '1', cash: '905000', market_value: '120000',
            cumulative_cost: String(i * 50), drawdown: ['0', '0', '-0.02380952'][i], daily_return: '0.025', valid: true })) };
        else if (url.pathname.endsWith('/jobs')) { data = []; meta.total = 0; }
        else if (url.pathname.endsWith('/observations')) data = [observation];
        else if (url.pathname.endsWith('/proposals')) {
          const offset = Number(url.searchParams.get('offset') || 0); meta.total = 24;
          data = Array.from({ length: offset ? 4 : 20 }, (_, i) => ({ id: `proposal-${offset + i}`, ts_code: '000001.SZ',
            action: 'PROPOSE_BUY', target_weight: '0.08', state: approved && !offset && !i ? 'APPROVED' : 'PENDING_REVIEW',
            stage: 'RIGHT_SIDE_NEW', expires_at: '2026-10-15T01:30:00Z', data: { candidate } }));
        } else if (url.pathname.endsWith('/reports')) { data = []; meta.total = 0; }
        else if (url.pathname.endsWith('/orders')) data = [{ id: 'order', ts_code: '600000.SH', side: 'BUY', quantity: 100,
          scheduled_date: '2026-10-15', status: 'SKIPPED', reason_code: `SUSPENDED_${'long-reason-'.repeat(20)}`, data: {} }];
        else if (url.pathname.endsWith('/reviews')) data = [{ id: 'review', asof_date: '2026-10-14', window_days: 1,
          status: 'READY', data: { stage: 'RIGHT_SIDE_NEW', action: 'WATCH', counterfactual: true, forward_mark_return: '0.03', included_in_nav: false } }];
        else if (url.pathname.includes('/paper/accounts/account/')) { data = []; meta.total = 0; }
        else throw new Error('Unexpected M17 API path: ' + url.pathname);
        await route.fulfill({ json: { code: 0, message: 'ok', data, meta } });
      });
      await page.goto(url);
      await page.getByRole('button', { name: '人工审批', exact: true }).first().waitFor();
      assert.equal(requests.length, 0);
      assert.equal(await page.locator('img').count(), 0);
      assert.equal(await page.evaluate(() => window.__paper_xss), undefined);
      await page.getByRole('button', { name: '人工审批', exact: true }).first().click();
      await page.getByRole('dialog').waitFor(); assert.equal(requests.length, 0);
      assert(await page.getByRole('button', { name: '确认模拟委托', exact: true }).isDisabled());
      await page.getByRole('checkbox').check();
      await page.getByRole('button', { name: '确认模拟委托', exact: true }).dblclick();
      await page.getByRole('alert').first().waitFor();
      assert.equal(approvalPosts, 1);
      await page.screenshot({ path: path.join(output, `approval-${width}.png`), fullPage: true });
      await page.getByRole('button', { name: '取消', exact: true }).click();
      await page.reload();
      await page.getByRole('button', { name: '人工审批', exact: true }).first().waitFor();
      assert(await page.getByRole('button', { name: '人工审批', exact: true }).first().isDisabled());
      assert.equal(approvalPosts, 1);
      await page.getByRole('button', { name: '下一页', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.paper-pagination')?.textContent.includes('21–24'));
      assert.equal(await page.locator('.paper-proposal').count(), 4);
      await page.getByRole('button', { name: '模拟组合', exact: true }).click();
      await page.locator('.paper-chart svg').waitFor();
      assert(await page.locator('.paper-chart svg path').count() > 5);
      assert(await page.locator('.paper-chart').evaluate(element => element.getBoundingClientRect().height >= 250));
      await page.screenshot({ path: path.join(output, `portfolio-${width}.png`), fullPage: true });
      await page.getByRole('tab', { name: '现金与持仓', exact: true }).click();
      await page.locator('.paper-chart svg').waitFor();
      await page.getByRole('button', { name: '执行与账本', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.paper-facts-table')?.textContent.includes('SKIPPED'));
      assert((await page.locator('.paper-facts-table').textContent()).includes('SKIPPED'));
      await page.getByRole('button', { name: '后验复盘', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.paper-facts-table')?.textContent.includes('标记收益'));
      assert((await page.locator('.paper-warning-text').first().textContent()).includes('不计入 NAV'));
      failStatus = true; await page.getByRole('button', { name: '刷新', exact: true }).click();
      await page.getByRole('alert').first().waitFor();
      assert((await page.getByRole('alert').first().textContent()).includes('SOURCE_NOT_READY'));
      await page.getByRole('button', { name: '刷新', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[role=alert]'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'M17 overflow at ' + width);
      await page.screenshot({ path: path.join(output, `review-${width}.png`), fullPage: true });
      assert.equal(approvalPosts, 1); assert.deepEqual(errors, []);
      console.log(`M17 browser ${width}px: explicit approval, lost response, reload, pagination, SVG charts, XSS, outage recovery passed`);
      await page.close();
    }
  } finally {
    if (browser) await browser.close(); vite.kill();
    await new Promise(resolve => { if (vite.exitCode !== null) resolve(); else vite.once('exit', resolve); });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
