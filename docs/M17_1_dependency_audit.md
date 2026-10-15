# M17.1 前端依赖安全审计

审计日期：2026-10-15；Node v22.23.3，本地 npm ci 后使用官方 registry。
锁文件 SHA-256：2566e9325278f8806deea5d8945d1a52cf84d4314f62eaf15c62d4c97d899ea0。
本轮不改依赖版本或 package-lock.json；只把 package.json 的 dev 默认监听收紧为 127.0.0.1。
**依赖升级 DEFERRED**，不执行 audit fix --force。
告警数量是当日快照，不保证未来公告库不变。浏览器探针通过不等于 CVE 已修复。

## 结果与路径

全部依赖 11 项：4 Critical、3 High、4 Moderate；--omit=dev 为 4 项：2 High、2 Moderate。
omit-dev 保留的是声明为 production 的包，并不等于最终 Nginx 容器的执行路径。

| 包/锁定版本 | 等级 | 引入链与实际路径 | 修复评估 |
|---|---|---|---|
| echarts 5.6.0 | Moderate | 直接 prod，浏览器图表运行时 | 公告修复线 >=6.1.0，跨主版本需独立回归 |
| vite 5.4.21 | High | 直接 prod 声明；plugin-vue、vitest、vite-node 也引用；开发/构建服务器 | 审计建议 8.3.4，跨主版本，不直接强升 |
| esbuild 0.21.5 | Moderate | vite -> esbuild；开发服务/构建 | 公告受影响 <=0.24.2；随已验证 Vite 升级处理 |
| source-map-js 1.2.1 | High | vue -> compiler-sfc；vite -> postcss；coverage -> magicast | 公告修复线 >=1.2.2，兼容补丁候选，仍需构建/浏览器回归 |
| vitest 2.1.9 | Critical | 直接 dev；测试/UI 服务器 | 审计建议 5.0.4；现有 run 模式不等于漏洞消失 |
| @vitest/coverage-v8 2.1.9 | Critical | 直接 dev -> vitest | 与 Vitest 同步升级到兼容已修复版本，建议 5.0.4 |
| @vitest/mocker 2.1.9 | Moderate | vitest -> mocker；测试 mock/文件路径 | 独立公告修复线 >=4.1.11；随 Vitest 方案验证 |
| vite-node 2.1.9 | Moderate | vitest -> vite-node -> vite | 传递 Vite 风险，随测试工具链处理 |
| happy-dom 15.11.7 | Critical | 直接 dev，被测试工具使用 | 审计建议 21.0.1；DOM、模块及 Cookie 行为需回归 |
| tinypool 1.1.1 | Critical | vitest -> tinypool；测试 Worker | 公告修复线 >=2.1.2；随兼容 Vitest 方案处理 |
| brace-expansion 2.1.4 | High | vue-tsc -> language-core -> minimatch 9.0.9 | >=2.1.7 为当前公告补丁线；其他链已装 5.0.12，不能混淆 |

## 可追踪公告

- ECharts XSS：[GHSA-fgmj-fm8m-jvvx](https://github.com/advisories/GHSA-fgmj-fm8m-jvvx)。
- Vite：[map 路径](https://github.com/advisories/GHSA-4w7w-66w2-5vf9)、
  [Windows UNC](https://github.com/advisories/GHSA-v6wh-96g9-6wx3)、
  [fs.deny 绕过](https://github.com/advisories/GHSA-fx2h-pf6j-xcff)。
- esbuild：[开发服务跨域读取](https://github.com/advisories/GHSA-67mh-4wv8-2f99)。
- source-map-js：[索引 source map DoS](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)。
- Vitest：[UI 文件读取/执行](https://github.com/advisories/GHSA-5xrq-8626-4rwp)、
  [mocker 路径读取](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)。
- Happy DOM：[VM 逃逸](https://github.com/advisories/GHSA-37j7-fg3j-429f)、
  [Cookie 源混淆](https://github.com/advisories/GHSA-w4gp-fjgq-3q4g)、
  [模块代码注入](https://github.com/advisories/GHSA-6q6h-j7hj-3r64)。
- Tinypool：[Worker 选项](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3)、
  [run 选项](https://github.com/advisories/GHSA-85c8-ppgw-ccpr)。
- brace-expansion：[二次复杂度](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr)、
  [嵌套递归](https://github.com/advisories/GHSA-qhr7-859c-m2p7)、
  [逗号递归](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p)。

## 缓解、受影响与未知

最终镜像由 Nginx 仅服务静态 dist，没有 Vite/Vitest 开发服务器。构建机和本地开发仍安装
这些包，不能把静态部署说成整个供应链未受影响。dev 脚本原默认 0.0.0.0，本轮改为 loopback；
它减小网络暴露面，但浏览器跨源/本机恶意输入风险仍存在。不要向公网暴露
Vite、Vitest UI 或测试 Worker；不在测试沙箱运行不可信脚本/HTML、source map 或配置。

PAPER 的 paperCharts.ts 只接收有界日期、Decimal 字符串和受控 series，使用 richText tooltip，
不接任意 HTML/options。已缓解该输入链，但 ECharts 包仍受公告影响；其他图表/工具链不能凭
PAPER 探针判定全部无风险。Vue 模板转义不是库级漏洞的修复证明。source-map/模块编译的
所有潜在路径未证明不可达，状态保留“无法证明未受影响”。

## 独立升级与回退计划

1. 先评估 source-map-js/brace-expansion 兼容补丁，生成审阅后的最小锁文件差异及新审计报告。
2. 分别做 ECharts 主版本升级、Vite/plugin-vue/esbuild 构建链升级、Vitest/coverage/DOM/Worker
   测试链升级，不把三个重大改动和 PAPER 金融规则放进一个补丁。
3. 每个升级提交固定 Node 22，npm ci、audit 双报告、完整前端覆盖率、构建、1440/390 浏览器，
   复核图表、审批手势、刷新/丢响应、XSS、代理、Nginx 路由及生产预览。新增变更不能降低既有阈值。
4. 修复线以对应公告和当次 peer/engine 兼容验证为准，审计建议版本不是未经测试的安装承诺。
   有回归则回退该独立提交/镜像/锁文件；不改账户数据或回滚迁移。旧依赖风险重新明确记录。

复现：Node 22 下在 frontend 执行 npm ci、npm audit --json --registry=https://registry.npmjs.org、
npm audit --omit=dev --json --registry=https://registry.npmjs.org、npm ls --all。
CI 将保留带 Node/npm/锁文件摘要的审计附件；有效的非零漏洞状态不会被误记为“零告警”。
也可从仓库根运行 `node scripts/m17_1_dependency_audit.cjs`：要求 Node 22，保存忽略目录中的
生成报告，不包含环境变量/凭据。对应 Node 内置测试验证有效非零告警、异常 JSON、网络失败和
无效计数。审计服务不可用会失败，不以空报告伪装成功。依赖引入链通过上述 npm ls 单独复核。
