const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const levels = ['info', 'low', 'moderate', 'high', 'critical'];
const transient = new Set(['ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN', 'ENOTFOUND', 'ENETUNREACH',
  'EHOSTUNREACH', 'ECONNREFUSED', 'EPIPE']);
const knownCodes = new Set([...transient, 'CERT_HAS_EXPIRED', 'DEPTH_ZERO_SELF_SIGNED_CERT',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'ERR_TLS_CERT_ALTNAME_INVALID', 'ENOENT', 'EACCES']);

class AuditError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function diagnostic(result, elapsed = 0) {
  let parsed;
  try { parsed = JSON.parse(result.stdout); } catch { /* No raw output is exported. */ }
  const rawCode = result.error?.code || parsed?.error?.code;
  const code = knownCodes.has(rawCode) ? rawCode : 'UNKNOWN';
  const http = parsed?.error?.statusCode;
  const httpStatus = Number.isInteger(http) && http >= 100 && http <= 599 ? http : null;
  return { code, status: Number.isInteger(result.status) ? result.status : null,
    registry_host: 'registry.npmjs.org',
    signal: ['SIGTERM', 'SIGKILL', 'SIGINT'].includes(result.signal) ? result.signal : null,
    elapsed_ms: elapsed, stdout_bytes: Buffer.byteLength(result.stdout || ''),
    stderr_bytes: Buffer.byteLength(result.stderr || ''), http_status: httpStatus,
    // Deliberately bounded structural summary, never registry text/URL/credentials.
    output_summary: parsed ? (parsed.error ? 'JSON_ERROR_OBJECT' : 'JSON_REPORT') : 'NON_JSON',
    stderr_summary: result.stderr ? 'CONTENT_REDACTED' : 'EMPTY',
    retryable: transient.has(code) || [429, 502, 503, 504].includes(httpStatus) };
}

function validateAudit(result) {
  if (result.error || result.signal || ![0, 1].includes(result.status)) {
    throw new AuditError('AUDIT_PROCESS_FAILURE', 'Audit command failed');
  }
  let report;
  try { report = JSON.parse(result.stdout); }
  catch { throw new AuditError('AUDIT_INVALID_JSON', 'Audit returned invalid JSON'); }
  const counts = report.metadata?.vulnerabilities;
  if (report.error || report.auditReportVersion !== 2 || !counts ||
      typeof report.vulnerabilities !== 'object' || !report.vulnerabilities || Array.isArray(report.vulnerabilities) ||
      [...levels, 'total'].some(key => !Number.isSafeInteger(counts[key]) || counts[key] < 0) ||
      levels.reduce((total, key) => total + counts[key], 0) !== counts.total ||
      Object.keys(report.vulnerabilities).length !== counts.total) {
    throw new AuditError('AUDIT_INVALID_SCHEMA', 'Audit report schema or counts are invalid');
  }
  for (const level of levels) {
    if (Object.values(report.vulnerabilities).filter(v => v?.severity === level).length !== counts[level]) {
      throw new AuditError('AUDIT_SEVERITY_MISMATCH', 'Audit report schema or counts are invalid');
    }
  }
  return { exit_status: result.status, report };
}

function validateLock(all, production, lock) {
  if (!lock.packages || lock.lockfileVersion !== 3) {
    throw new AuditError('AUDIT_LOCK_SCHEMA', 'Unsupported lockfile');
  }
  const packages = {};
  for (const [scope, audit] of [['all', all], ['production', production]]) {
    for (const [name, entry] of Object.entries(audit.report.vulnerabilities)) {
      if (!Array.isArray(entry.nodes) || !entry.nodes.length || entry.name !== name ||
          entry.nodes.some(node => typeof node !== 'string' || !lock.packages[node]?.version ||
            !node.endsWith(`node_modules/${name}`))) {
        throw new AuditError('AUDIT_PACKAGE_ABSENT_FROM_LOCK', 'Audit package absent from lockfile');
      }
      if (scope === 'production' && (!all.report.vulnerabilities[name] ||
          entry.nodes.some(node => lock.packages[node].dev ||
            !all.report.vulnerabilities[name].nodes.includes(node)))) {
        throw new AuditError('AUDIT_PRODUCTION_NOT_SUBSET', 'Production inventory is not a subset');
      }
      if (scope === 'all') {
        const node = entry.nodes.includes(`node_modules/${name}`) ? `node_modules/${name}` : entry.nodes[0];
        const installed = lock.packages[node];
        packages[name] = { version: installed.version, dev: Boolean(installed.dev),
          nodes: Object.fromEntries(entry.nodes.map(p => [p, {
            version: lock.packages[p].version, dev: Boolean(lock.packages[p].dev) }])) };
      }
    }
  }
  return packages;
}

async function collect(invoke, args, attempts, scope, pause) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const started = performance.now();
    const result = invoke(args);
    const detail = { scope, attempt, ...diagnostic(result, Math.round(performance.now() - started)) };
    try {
      const audit = validateAudit(result);
      attempts.push({ ...detail, state: 'COMPLETE' });
      return audit;
    } catch (error) {
      attempts.push({ ...detail, state: 'INCOMPLETE', failure_code: error.code });
      console.error(JSON.stringify({ audit_failure: attempts.at(-1) }));
      if (!detail.retryable || attempt === 3) throw error;
      await pause(attempt * 1000);
    }
  }
}

function atomic(destination, value) {
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination + '.tmp', JSON.stringify(value, null, 2) + '\n', 'utf8');
  fs.renameSync(destination + '.tmp', destination);
}

async function main(options = {}) {
  const root = options.root || path.resolve(__dirname, '..');
  const frontend = path.join(root, 'frontend');
  const destination = path.join(root, '.codex_tmp', 'm17_1-dependency-audit.json');
  const incomplete = path.join(root, '.codex_tmp', 'm17_1-dependency-audit-incomplete.json');
  const attempts = [];
  const identity = { head_sha: process.env.GITHUB_SHA || 'LOCAL_NOT_RELEASE_EVIDENCE',
    run_id: process.env.GITHUB_RUN_ID || 'local', attempt: process.env.GITHUB_RUN_ATTEMPT || 'local' };
  const command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const invoke = options.invoke || (args => spawnSync(command, args, {
    cwd: frontend, encoding: 'utf8', timeout: 90000, maxBuffer: 8 * 1024 * 1024,
    shell: process.platform === 'win32', windowsHide: true,
  }));
  const pause = options.pause || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  try {
    if (fs.existsSync(destination) || fs.existsSync(incomplete)) {
      throw new AuditError('AUDIT_OUTPUT_ALREADY_EXISTS', 'Refusing stale audit output');
    }
    if (!(options.nodeVersion || process.version).startsWith('v22.')) {
      throw new AuditError('AUDIT_NODE_VERSION', 'Dependency audit requires Node 22');
    }
    const lockBytes = fs.readFileSync(path.join(frontend, 'package-lock.json'));
    const lock = JSON.parse(lockBytes.toString('utf8'));
    const npmVersion = invoke(['--version']);
    const version = (npmVersion.stdout || '').trim();
    if (npmVersion.error || npmVersion.signal || npmVersion.status !== 0 || !/^\d+\.\d+\.\d+$/.test(version)) {
      attempts.push({ scope: 'npm-version', ...diagnostic(npmVersion) });
      throw new AuditError('AUDIT_NPM_VERSION_FAILURE', 'Cannot read npm version');
    }
    const args = ['audit', '--json', '--registry=https://registry.npmjs.org'];
    const all = await collect(invoke, args, attempts, 'all', pause);
    const production = await collect(invoke, [...args, '--omit=dev'], attempts, 'production', pause);
    const packages = validateLock(all, production, lock);
    const artifact = {
      schema_version: 'm17.1-dependency-audit-v1', measured_at: new Date().toISOString(),
      status: 'COMPLETE', ...identity, attempts,
      node_version: options.nodeVersion || process.version, npm_version: version,
      lock_sha256: createHash('sha256').update(lockBytes).digest('hex'),
      registry: 'https://registry.npmjs.org', packages, all, production,
      interpretation: 'RISK_INVENTORY_NOT_A_DEPENDENCY_UPGRADE_OR_ZERO_VULNERABILITY_GATE',
    };
    atomic(destination, artifact);
    console.log(JSON.stringify({ node: artifact.node_version, lock_sha256: artifact.lock_sha256,
      all: all.report.metadata.vulnerabilities, production: production.report.metadata.vulnerabilities }));
    return artifact;
  } catch (error) {
    atomic(incomplete, { schema_version: 'dependency-audit-incomplete-v1', status: 'INCOMPLETE',
      ...identity, measured_at: new Date().toISOString(), attempts,
      failure_code: error instanceof AuditError ? error.code : 'AUDIT_LOCAL_INPUT_FAILURE' });
    throw new AuditError(error instanceof AuditError ? error.code : 'AUDIT_LOCAL_INPUT_FAILURE',
      'Dependency audit INCOMPLETE; see sanitized diagnostic artifact');
  }
}

module.exports = { validateAudit, validateLock, diagnostic, collect, main };
if (require.main === module) main().catch(error => { console.error(error.code); process.exitCode = 1; });
