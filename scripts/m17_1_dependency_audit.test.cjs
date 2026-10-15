const assert = require('node:assert/strict');
const { test } = require('node:test');
const { validateAudit } = require('./m17_1_dependency_audit.cjs');

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
