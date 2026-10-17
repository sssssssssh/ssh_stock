// UI-only gate: the frozen Git tree, not an editable inventory, is the authority.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync, spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const baseline = '0136ee9e03727314102cc041d52dd488cca50def';
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const allowed = file => file === 'frontend/src/style.css'
  || file.startsWith('docs/ui-upgrade/')
  || ['README.md', 'PROJECT_RULES.md', 'docs/股票机会发现系统_PRD_V1.0.md',
    'docs/股票机会发现系统_系统设计_V1.0.md',
    '.github/workflows/ci.yml', 'scripts/ui_visual_integrity.cjs', 'scripts/ui_visual_browser.cjs'].includes(file);

function check({ workspace = root } = {}) {
  const git = args => execFileSync('git', args, { cwd: workspace, maxBuffer: 16 * 1024 * 1024 });
  git(['cat-file', '-e', `${baseline}^{commit}`]);
  const inventory = JSON.parse(fs.readFileSync(path.join(workspace, 'docs/ui-upgrade/UI-0_source_inventory.json')));
  assert.equal(inventory.baseline_commit, baseline);
  const files = git(['ls-tree', '-r', '-z', '--name-only', baseline, 'frontend']).toString().split('\0').filter(Boolean);
  assert.deepEqual(inventory.sources.map(row => row.file), files, 'Frozen inventory must cover the exact Git tree');
  let protectedFiles = 0;
  for (const row of inventory.sources) {
    const original = git(['show', `${baseline}:${row.file}`]);
    assert.equal(sha(original), row.sha256, `Inventory drift: ${row.file}`);
    assert.equal(original.length, row.bytes);
    if (row.file !== 'frontend/src/style.css') {
      assert.equal(sha(fs.readFileSync(path.join(workspace, row.file))), sha(original), `Non-visual modification: ${row.file}`);
      protectedFiles++;
    }
  }
  const changed = git(['diff', '-z', '--name-only', baseline]).toString().split('\0').filter(Boolean);
  const untracked = git(['ls-files', '-z', '--others', '--exclude-standard']).toString().split('\0').filter(Boolean);
  for (const file of [...changed, ...untracked]) assert(allowed(file), `Outside UI-only delivery scope: ${file}`);
  const additions = git(['diff', '--unified=0', baseline, '--', 'frontend/src/style.css']).toString()
    .split('\n').filter(line => line.startsWith('+') && !line.startsWith('+++')).join('\n');
  assert(!/\b(?:display\s*:\s*none|visibility\s*:\s*hidden|pointer-events\s*:\s*none|order\s*:)/i.test(additions),
    'New styles must not hide or disable existing controls/information or reorder keyboard targets');
  assert(!/\bcontent\s*:\s*["'][^"']+/i.test(additions), 'Do not introduce product text through CSS');
  assert(!/@import|https?:\/\//i.test(additions), 'Do not add remote style/font dependencies');
  const oldCI = git(['show', `${baseline}:.github/workflows/ci.yml`]).toString().trimEnd();
  assert(fs.readFileSync(path.join(workspace, '.github/workflows/ci.yml'), 'utf8').startsWith(oldCI),
    'Existing test job must remain byte-for-byte intact; append the isolated UI job only');
  return { baseline, protectedFiles, vueFiles: inventory.counts.vue_files,
    controls: inventory.counts.controls, apiCallSites: inventory.counts.api_call_sites, changed };
}

function selfTest() {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'ssh-stock-ui-negative-'));
  try {
    execFileSync('git', ['clone', '--quiet', '--shared', '--no-hardlinks', root, sandbox]);
    check({workspace: sandbox});
    const cases = [
      ['vue-byte-change', 'frontend/src/App.vue', '\n<!-- negative fixture only -->\n', 'Non-visual modification'],
      ['new-production-file', 'frontend/src/ui_forbidden_fixture.ts', 'export const forbidden = true;\n', 'Outside UI-only'],
      ['new-backend-file', 'backend/ui_forbidden_fixture.py', '# forbidden fixture\n', 'Outside UI-only'],
      ['hidden-css', 'frontend/src/style.css', '\n.fixture { display:none; }\n', 'New styles must not hide'],
      ['old-ci-weakened', '.github/workflows/ci.yml', '\n', 'Existing test job']
    ];
    const results=[];
    for(const [name,file,addition,expected] of cases) {
      const target=path.join(sandbox,file), original=fs.existsSync(target)?fs.readFileSync(target):null;
      const bytes=name==='old-ci-weakened' ? fs.readFileSync(target,'utf8').replace('python -m ruff check','echo bypass-ruff')
        : Buffer.concat([original||Buffer.alloc(0),Buffer.from(addition)]);
      fs.writeFileSync(target,bytes);
      const result=spawnSync(process.execPath,['-e',`require(${JSON.stringify(__filename)}).check({workspace:${JSON.stringify(sandbox)}})`],{encoding:'utf8'});
      assert.notEqual(result.status,0,`${name} incorrectly passed`);
      assert(result.stderr.includes(expected),`${name} failed for an unrelated reason: ${result.stderr}`);
      results.push({name,exit_code:result.status,rejected:true});
      console.log(`Negative ${name}: correctly rejected with exit ${result.status}`);
      if(original)fs.writeFileSync(target,original);else fs.unlinkSync(target);
      check({workspace:sandbox});
    }
    return {passed:true,cases:results};
  } finally { fs.rmSync(sandbox,{recursive:true,force:true}); }
}
if (require.main === module) {
  // The negative checks must keep rejecting business/code additions.
  for (const file of ['backend/app/api/routes.py', 'frontend/src/App.vue', 'frontend/package-lock.json',
    'frontend/src/services/api.ts', '.env', 'migrations/new.py']) assert.equal(allowed(file), false);
  console.log(JSON.stringify(process.argv.includes('--self-test')?selfTest():check(), null, 2));
}
module.exports = { check, baseline, selfTest };
