const assert = require('node:assert/strict');
const { test } = require('node:test');
const { validateAudit, validateLock, diagnostic, collect, main } = require('./m17_1_dependency_audit.cjs');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function result(total = 1) {
  return { status: total ? 1 : 0, stdout: JSON.stringify({ auditReportVersion: 2,
    vulnerabilities: total ? { synthetic: { severity: 'high' } } : {},
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: total,
      critical: 0, total } } }) };
}

test('known vulnerabilities remain explicit inventory, not a false clean audit', () => {
  const audit = validateAudit(result());
  assert.equal(audit.exit_status, 1);
  assert.equal(audit.report.metadata.vulnerabilities.total, 1);
});
test('an actual empty audit is accepted as zero', () => {
  assert.equal(validateAudit(result(0)).report.metadata.vulnerabilities.total, 0);
});
test('process/network failure cannot become an accepted risk inventory', () => {
  assert.throws(() => validateAudit({ ...result(), status: 2 }), /command failed/);
  assert.throws(() => validateAudit({ ...result(), error: new Error('private') }), /command failed/);
});
test('invalid JSON or registry error fails without exporting error payload', () => {
  assert.throws(() => validateAudit({ status: 1, stdout: 'private response' }), /invalid JSON/);
  assert.throws(() => validateAudit({ status: 1, stdout: '{"error":{"secret":"private"}}' }),
    /schema or counts/);
});
for (const value of [-1, 0.5, '1', null]) {
  test(`invalid count ${JSON.stringify(value)} is rejected`, () => {
    const input = result();
    const body = JSON.parse(input.stdout);
    body.metadata.vulnerabilities.high = value;
    input.stdout = JSON.stringify(body);
    assert.throws(() => validateAudit(input), /schema or counts/);
  });
}
test('mismatched inventory and total is rejected', () => {
  const input = result();
  const body = JSON.parse(input.stdout);
  body.vulnerabilities = {};
  input.stdout = JSON.stringify(body);
  assert.throws(() => validateAudit(input), /schema or counts/);
});

test('severity totals must match individual entries, not just grand total', () => {
  const input = result();
  const body = JSON.parse(input.stdout);
  body.vulnerabilities.synthetic.severity = 'low';
  assert.throws(() => validateAudit({ ...input, stdout: JSON.stringify(body) }), /schema or counts/);
});

test('transient timeout retries are bounded and retain real exit-one inventory', async () => {
  let calls = 0;
  const attempts = [];
  const audit = await collect(() => ++calls === 1 ? {
    error: { code: 'ETIMEDOUT', message: 'TOKEN_DO_NOT_EXPORT' }, status: null,
    stderr: 'https://private:secret@registry.example', stdout: '' } : result(), [], attempts,
  'all', async () => {});
  assert.equal(calls, 2);
  assert.equal(audit.exit_status, 1);
  assert.equal(attempts[0].code, 'ETIMEDOUT');
  assert.ok(!JSON.stringify(attempts).includes('secret'));
  assert.ok(!JSON.stringify(attempts).includes('TOKEN'));
  assert.equal(attempts[1].state, 'COMPLETE');
});

for (const code of ['ECONNRESET', 'EAI_AGAIN', 'ETIMEDOUT']) {
  test(`persistent ${code} fails after three attempts`, async () => {
    const attempts = [];
    await assert.rejects(collect(() => ({ status: null, error: { code } }), [], attempts,
      'all', async () => {}));
    assert.equal(attempts.length, 3);
    assert.ok(attempts.every(a => a.state === 'INCOMPLETE'));
  });
}

for (const failure of [
  { status: 1, error: { code: 'CERT_HAS_EXPIRED' } },
  { status: 1, stdout: 'INVALID_PRIVATE_RESPONSE' },
  { status: 0, stdout: '{"metadata":{}}' },
  { status: 2, stdout: '{}' },
]) {
  test('certificate/schema/JSON/command failure is not retried or exported raw', async () => {
    const attempts = [];
    await assert.rejects(collect(() => failure, [], attempts, 'all', async () => {}));
    assert.equal(attempts.length, 1);
    assert.ok(!JSON.stringify(attempts).includes('PRIVATE_RESPONSE'));
  });
}

test('HTTP transient classification is numeric and summaries are bounded', () => {
  const detail = diagnostic({ status: 1, stdout: JSON.stringify({
    error: { code: 'UNTRUSTED_' + 'X'.repeat(5000), statusCode: 503 } }) });
  assert.equal(detail.code, 'UNKNOWN');
  assert.equal(detail.retryable, true);
  assert.ok(JSON.stringify(detail).length < 500);
});

function lockedAudit(dev = false) {
  const value = result();
  const body = JSON.parse(value.stdout);
  body.vulnerabilities.synthetic = { name: 'synthetic', severity: 'high',
    nodes: ['node_modules/synthetic'] };
  return { all: validateAudit({ ...value, stdout: JSON.stringify(body) }),
    production: validateAudit(result(0)), lock: { lockfileVersion: 3, packages: {
      'node_modules/synthetic': { version: '1.2.3', dev } } } };
}

test('lockfile membership, node versions and production subset are required', () => {
  const { all, production, lock } = lockedAudit();
  assert.equal(validateLock(all, production, lock).synthetic.version, '1.2.3');
  assert.throws(() => validateLock(all, production, { ...lock, packages: {} }), /absent/);
  assert.throws(() => validateLock(all, production, { ...lock, lockfileVersion: 2 }), /lockfile/);
  assert.throws(() => validateLock(production, all, lock), /subset/);
  assert.throws(() => validateLock(all, all, lockedAudit(true).lock), /subset/);
});

function temporary(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'a422-audit-unit-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'frontend'));
  fs.writeFileSync(path.join(root, 'frontend/package-lock.json'), JSON.stringify(lockedAudit().lock));
  return root;
}

test('main writes a valid complete artifact only after both real-shaped reports', async t => {
  const root = temporary(t);
  const { all, production } = lockedAudit();
  const responses = [{ status: 0, stdout: '10.9.4\n' },
    { status: 1, stdout: JSON.stringify(all.report) },
    { status: 0, stdout: JSON.stringify(production.report) }];
  const artifact = await main({ root, nodeVersion: 'v22.0.0', invoke: () => responses.shift() });
  assert.equal(artifact.status, 'COMPLETE');
  assert.equal(artifact.all.report.metadata.vulnerabilities.total, 1);
  assert.equal(artifact.production.report.metadata.vulnerabilities.total, 0);
  assert.ok(fs.existsSync(path.join(root, '.codex_tmp/m17_1-dependency-audit.json')));
  assert.ok(!fs.existsSync(path.join(root, '.codex_tmp/m17_1-dependency-audit-incomplete.json')));
});

for (const phase of ['npm-version', 'audit-network', 'lock']) {
  test(`${phase} failure writes INCOMPLETE only, never a zero/partial inventory`, async t => {
    const root = temporary(t);
    const { all } = lockedAudit();
    const responses = [{ status: 0, stdout: '10.9.4\n' },
      { status: 1, stdout: JSON.stringify(all.report) }, result(0)];
    if (phase === 'npm-version') responses[0] = { status: 2, stderr: 'PRIVATE' };
    if (phase === 'audit-network') responses[1] = { status: null, error: { code: 'ETIMEDOUT' } };
    if (phase === 'lock') fs.writeFileSync(path.join(root, 'frontend/package-lock.json'),
      JSON.stringify({ lockfileVersion: 3, packages: {} }));
    await assert.rejects(main({ root, nodeVersion: 'v22.0.0', pause: async () => {},
      invoke: () => responses.shift() || { status: null, error: { code: 'ETIMEDOUT' } } }));
    const incomplete = fs.readFileSync(path.join(root, '.codex_tmp/m17_1-dependency-audit-incomplete.json'), 'utf8');
    assert.equal(JSON.parse(incomplete).status, 'INCOMPLETE');
    assert.ok(!incomplete.includes('PRIVATE') && !incomplete.includes('vulnerabilities'));
    assert.ok(!fs.existsSync(path.join(root, '.codex_tmp/m17_1-dependency-audit.json')));
  });
}
