const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function validateAudit(result) {
  if (result.error || ![0, 1].includes(result.status)) throw new Error('Audit command failed');
  let report;
  try { report = JSON.parse(result.stdout); }
  catch { throw new Error('Audit returned invalid JSON'); }
  const counts = report.metadata?.vulnerabilities;
  const levels = ['info', 'low', 'moderate', 'high', 'critical'];
  if (report.error || report.auditReportVersion !== 2 || !counts ||
      typeof report.vulnerabilities !== 'object' || !report.vulnerabilities ||
      [...levels, 'total'].some(key => !Number.isSafeInteger(counts[key]) || counts[key] < 0) ||
      levels.reduce((total, key) => total + counts[key], 0) !== counts.total ||
      Object.keys(report.vulnerabilities).length !== counts.total) {
    throw new Error('Audit report schema or counts are invalid');
  }
  return { exit_status: result.status, report };
}

function main() {
  if (!process.version.startsWith('v22.')) throw new Error('Dependency audit requires Node 22');
  const root = path.resolve(__dirname, '..');
  const frontend = path.join(root, 'frontend');
  const lockBytes = fs.readFileSync(path.join(frontend, 'package-lock.json'));
  const lock = JSON.parse(lockBytes.toString('utf8'));
  const command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const invoke = args => spawnSync(command, args, {
    cwd: frontend, encoding: 'utf8', timeout: 90000, maxBuffer: 8 * 1024 * 1024,
    shell: process.platform === 'win32', windowsHide: true,
  });
  const npmVersion = invoke(['--version']);
  if (npmVersion.status !== 0) throw new Error('Cannot read npm version');
  const args = ['audit', '--json', '--registry=https://registry.npmjs.org'];
  const all = validateAudit(invoke(args));
  const production = validateAudit(invoke([...args, '--omit=dev']));
  const packages = Object.fromEntries(Object.keys(all.report.vulnerabilities).sort().map(name => {
    const entry = lock.packages[`node_modules/${name}`];
    if (!entry?.version) throw new Error('Audit package absent from lockfile');
    return [name, { version: entry.version, dev: Boolean(entry.dev) }];
  }));
  const artifact = {
    schema_version: 'm17.1-dependency-audit-v1', measured_at: new Date().toISOString(),
    node_version: process.version, npm_version: npmVersion.stdout.trim(),
    lock_sha256: createHash('sha256').update(lockBytes).digest('hex'),
    registry: 'https://registry.npmjs.org', packages, all, production,
    interpretation: 'RISK_INVENTORY_NOT_A_DEPENDENCY_UPGRADE_OR_ZERO_VULNERABILITY_GATE',
  };
  const destination = path.join(root, '.codex_tmp', 'm17_1-dependency-audit.json');
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, JSON.stringify(artifact, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({ node: artifact.node_version, lock_sha256: artifact.lock_sha256,
    all: all.report.metadata.vulnerabilities, production: production.report.metadata.vulnerabilities }));
}

module.exports = { validateAudit };
if (require.main === module) main();
