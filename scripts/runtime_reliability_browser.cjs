// Read-only browser acceptance: every API request is synthetic and intercepted.
const assert = require('node:assert/strict');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const net = require('node:net');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'frontend/coverage/runtime-reliability-browser');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  const vite = spawn(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'),
    '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
  { cwd: path.join(root, 'frontend'), stdio: 'pipe' });
  let browser;
  try {
    const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
    assert(!process.env.GITHUB_SHA || process.env.GITHUB_SHA === head, 'CI_HEAD_MISMATCH');
    await fs.mkdir(output, { recursive: true });
    const url = `http://127.0.0.1:${port}`;
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch {}
      await wait(100);
    }
    assert(ready, 'Isolated frontend did not start');
    browser = await chromium.launch({ headless: true,
      ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
    const results = [];
    for (const width of [1440, 390]) {
      for (const mode of ['loading', 'empty', 'stale', 'failed', 'statistics-error', 'queue', 'cancel', 'cancelled', 'unconfirmed', 'candidate', 'published', 'schedule-alert']) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        const errors = [];
        let cancelRequested = false, cancelPosts = 0;
        let pending = Array.from({ length: 35 }, (_, index) => ({
          id: `queued-${index}`, job_type: 'backfill', status: 'QUEUED', can_cancel: true,
          started_at: new Date(Date.UTC(2026, 9, 18, 1, 0, index)).toISOString(),
          finished_at: null, step: 'queued from api', row_count: 0, error_message: null,
          metadata: { start: '2026-01-01', end: '2026-03-31' }
        }));
        const running = () => ({
          id: 'synthetic-running', job_type: 'recalculate', status: mode === 'cancelled' ? 'CANCELLED' : mode === 'published' ? 'SUCCESS' : 'RUNNING',
          started_at: '2026-10-18T00:00:00Z', execution_started_at: '2026-10-18T00:30:00Z',
          heartbeat_at: '2026-10-18T00:31:00Z', last_progress_at: '2026-10-18T00:30:30Z',
          finished_at: mode === 'cancelled' ? '2026-10-18T00:32:00Z' : null,
          cancel_requested: cancelRequested || mode === 'cancelled', can_cancel: !cancelRequested && !['cancelled', 'unconfirmed'].includes(mode),
          execution_unconfirmed: mode === 'unconfirmed',
          publication: ['candidate', 'published'].includes(mode) ? {
            state: mode === 'published' ? 'PUBLISHED' : 'PREPARING',
            identity: 'synthetic-publication-identity', published_at: '2026-10-18T01:00:00Z'
          } : undefined,
          metadata: { stage: 'factors', progress_pct: 20 }, row_count: 12, step: '90 factors', error_message: null
        });
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/api/v1/**', async route => {
          const p = new URL(route.request().url()).pathname.replace('/api/v1', '');
          let data = [];
          let status = 200;
          if (p === '/auth/me') data = { username: 'synthetic-admin', must_change_password: false };
          else if (p === '/dashboard/summary') data = { sector_heat_top: [] };
          else if (p === '/system/status') data = {};
          else if (p === '/system/runtime') data = { services: {}, queued_count: 0, running_count: mode === 'stale' ? 1 : 0,
            scheduler_compensation: mode === 'schedule-alert' ? { pending_count: 1, items: [{
              kind: 'catchup', target_date: '2026-10-17', state: 'DEFERRED', error_code: 'QUEUE_CAPACITY_EXCEEDED'
            }] } : undefined };
          else if (p === '/jobs/queue') data = {
            running: ['queue', 'cancel', 'unconfirmed', 'candidate'].includes(mode) ? [running()] : [],
            queued: mode === 'queue' ? pending.map((job, index) => ({ ...job, queue_position: index + 1 })) : []
          };
          else if (p.endsWith('/cancel')) {
            assert.equal(route.request().method(), 'POST');
            cancelPosts++;
            if (p.includes('/queued-')) {
              const id = p.split('/').at(-2);
              const job = pending.find(row => row.id === id);
              pending = pending.filter(row => row.id !== id);
              data = { ...job, status: 'CANCELLED', cancel_requested: true };
            } else { cancelRequested = true; data = running(); }
          }
          else if (p === '/system/data-coverage' && mode === 'statistics-error') status = 503;
          else if (p === '/jobs') {
            if (['cancelled', 'published'].includes(mode)) data = [running()];
            if (mode === 'loading') await wait(1800);
            if (['stale', 'failed'].includes(mode)) data = [{
              id: 'synthetic-job', job_type: 'recalculate', status: mode === 'stale' ? 'RUNNING' : 'FAILED',
              heartbeat_stale: mode === 'stale', started_at: '2026-10-18T00:00:00Z',
              finished_at: mode === 'failed' ? '2026-10-18T00:01:00Z' : null,
              step: '80 calculate trade status', row_count: 0,
              error_message: mode === 'failed' ? 'SYNTHETIC_DATABASE_FAILURE · '.repeat(15) : null,
              metadata: { start: '2025-02-01', end: '2025-02-28', stage: 'trade_status', progress_pct: 4 }
            }];
          }
          await route.fulfill({ status, contentType: 'application/json',
            body: JSON.stringify(status === 200 ? { code: 0, data, meta: {} } : { detail: 'SYNTHETIC_STATISTICS_UNAVAILABLE' }) });
        });
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        await page.locator('.nav-button').filter({ hasText: '覆盖、拉取和任务进度' }).click();
        if (mode === 'loading') {
          await page.getByRole('button', { name: '刷新中', exact: true }).waitFor();
        } else {
          await page.getByRole('button', { name: '刷新', exact: true }).waitFor();
          if (mode === 'stale') await page.locator('.job-current [role="status"]').waitFor();
          if (mode === 'failed') await page.locator('.job-error-line').waitFor();
          if (mode === 'empty') assert((await page.locator('.job-list').innerText()).includes('暂无任务记录'));
          if (mode === 'statistics-error') await page.getByText('SYNTHETIC_STATISTICS_UNAVAILABLE', { exact: true }).waitFor();
          if (mode === 'candidate') await page.getByText('候选计算中，尚未发布', { exact: true }).waitFor();
          if (mode === 'published') await page.getByText(/已发布 · .*synthetic-publication-identity/).waitFor();
          if (mode === 'schedule-alert') await page.getByText(/调度待处理 1 项/).waitFor();
          if (mode === 'queue') {
            await page.waitForFunction(() => document.querySelectorAll('.queue-entry').length === 35);
            page.once('dialog', dialog => dialog.accept());
            await page.locator('.queue-entry button').first().click();
            await page.waitForFunction(() => document.querySelectorAll('.queue-entry').length === 34);
            assert.equal(cancelPosts, 1);
            assert((await page.locator('.queue-entry').first().innerText()).includes('#1'));
          }
          if (mode === 'cancel') {
            page.once('dialog', dialog => dialog.accept());
            await page.getByRole('button', { name: '请求取消', exact: true }).click();
            await page.getByRole('button', { name: '取消中', exact: true }).waitFor();
            assert(await page.getByRole('button', { name: '取消中', exact: true }).isDisabled());
            assert.equal(cancelPosts, 1);
            assert((await page.locator('.job-current').innerText()).includes('已请求取消，等待当前安全点'));
          }
          if (mode === 'unconfirmed') {
            await page.getByText('执行结果待确认', { exact: true }).waitFor();
            assert.equal(await page.locator('.job-current button').count(), 0);
            assert((await page.locator('.job-current').innerText()).includes('无法证明旧 SQL 已停止'));
          }
        }
        assert.equal(await page.getByRole('button', { name: '同步基础信息', exact: true }).count(), 1);
        assert.equal(await page.getByRole('button', { name: '拉取原始数据', exact: true }).count(), 1);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        assert(overflow <= 1, `${width}/${mode}: page overflow ${overflow}`);
        assert.deepEqual(errors, []);
        const file = `${width}-${mode}.png`;
        await page.screenshot({ path: path.join(output, file), fullPage: true });
        results.push({ width, mode, file, passed: true });
        await page.close();
      }
    }
    await fs.writeFile(path.join(output, 'result.json'), JSON.stringify({
      synthetic: true, head_sha: head,
      working_tree_dirty: Boolean(execFileSync('git', ['status', '--short'], { cwd: root, encoding: 'utf8' }).trim()),
      results
    }, null, 2));
    console.log(JSON.stringify({ passed: results.length, synthetic: true, output }));
  } finally {
    if (browser) await browser.close();
    vite.kill('SIGTERM');
    await new Promise(resolve => { if (vite.exitCode !== null) resolve(); else vite.once('exit', resolve); });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
