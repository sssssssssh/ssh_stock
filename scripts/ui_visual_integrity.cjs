// UI-only gate: the frozen Git tree, not an editable inventory, is the authority.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const baseline = '0136ee9e03727314102cc041d52dd488cca50def';
const git = args => execFileSync('git', args, { cwd: root, maxBuffer: 16 * 1024 * 1024 });
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const allowed = file => file === 'frontend/src/style.css'
  || file.startsWith('docs/ui-upgrade/')
  || ['README.md', 'PROJECT_RULES.md', 'docs/股票机会发现系统_PRD_V1.0.md',
    'docs/股票机会发现系统_系统设计_V1.0.md',
    'scripts/ui_visual_integrity.cjs', 'scripts/ui_visual_browser.cjs'].includes(file);

function check() {
  const inventory = JSON.parse(fs.readFileSync(path.join(root, 'docs/ui-upgrade/UI-0_source_inventory.json')));
  assert.equal(inventory.baseline_commit, baseline);
  const files = git(['ls-tree', '-r', '--name-only', baseline, 'frontend']).toString().trim().split('\n');
  assert.deepEqual(inventory.sources.map(row => row.file), files, 'Frozen inventory must cover the exact Git tree');
  let protectedFiles = 0;
  for (const row of inventory.sources) {
    const original = git(['show', `${baseline}:${row.file}`]);
    assert.equal(sha(original), row.sha256, `Inventory drift: ${row.file}`);
    assert.equal(original.length, row.bytes);
    if (row.file !== 'frontend/src/style.css') {
      assert.equal(sha(fs.readFileSync(path.join(root, row.file))), sha(original), `Non-visual modification: ${row.file}`);
      protectedFiles++;
    }
  }
  const changed = git(['diff', '--name-only', baseline]).toString().trim().split('\n').filter(Boolean);
  const untracked = git(['ls-files', '--others', '--exclude-standard']).toString().trim().split('\n').filter(Boolean);
  for (const file of [...changed, ...untracked]) assert(allowed(file), `Outside UI-only delivery scope: ${file}`);
  const additions = git(['diff', '--unified=0', baseline, '--', 'frontend/src/style.css']).toString()
    .split('\n').filter(line => line.startsWith('+') && !line.startsWith('+++')).join('\n');
  assert(!/\b(?:display\s*:\s*none|visibility\s*:\s*hidden|pointer-events\s*:\s*none|order\s*:)/i.test(additions),
    'New styles must not hide or disable existing controls/information or reorder keyboard targets');
  assert(!/\bcontent\s*:\s*["'][^"']+/i.test(additions), 'Do not introduce product text through CSS');
  assert(!/@import|https?:\/\//i.test(additions), 'Do not add remote style/font dependencies');
  return { baseline, protectedFiles, vueFiles: inventory.counts.vue_files,
    controls: inventory.counts.controls, apiCallSites: inventory.counts.api_call_sites, changed };
}
if (require.main === module) {
  // The negative checks must keep rejecting business/code additions.
  for (const file of ['backend/app/api/routes.py', 'frontend/src/App.vue', 'frontend/package-lock.json',
    'frontend/src/services/api.ts', '.env', 'migrations/new.py']) assert.equal(allowed(file), false);
  console.log(JSON.stringify(check(), null, 2));
}
module.exports = { check, baseline };
