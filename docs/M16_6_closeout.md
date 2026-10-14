# M16.6 冻结研究合同交付与验收

## 实测状态

2026-10-14 核对完成：M16.6 A–F 及收尾补丁全部验收通过，功能封版，默认关闭捕获。用户业务库未迁移；继承的独立 P2 依赖升级不是本轮已解决项目。

- 规划基线：`07e288c3826618192b4022e8b63d0df06db679ec`，当前分支保持 `master`。
- A：`d625edc37744584472943eedf3cf9697a7f10920`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38340339216)。
- B：`c048b84b771510740b96aca3624e21c09f1556e5`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38356151219)。
- C：`ec49593bb1957c1137a3c8633be905685efb5f2d`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38358271783)。
- D：`54920b8631589adfff3acb9a51f9150fd25b2a5d`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38364353253)。
- E：`878ba1cae5609bf369e5cbd290928aaff0143874`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38373484728)，1277 pytest passed、后端覆盖率 87%、100 前端测试、前端构建、Ruff、Docker config/build/nginx 和迁移往返通过。
- F 基础：`974d07b6cd1e2525c5c2d5760fce780b869beffb`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38376180481)，1285 pytest passed、87% 后端覆盖率；current/heads 同为 0052；100 前端测试/81.42% 行覆盖率；Docker 和 1440px/390px Chromium 浏览器通过。
- F 审查补丁：`5d88006f904c22005fe30af2d8d14d0c4fb3bf3d`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38377760959)，1289 passed、同 Evidence 冲突/写后回滚和其他完整矩阵通过。
- 最终功能：`4f5f2d453704e73fac8c29c084baf10ffa27082a`；[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38379683263)，1298 pytest passed，后端覆盖率 87%，Ruff、Alembic、100 前端测试/81.45% 行覆盖率、build、Docker config/build/nginx、Linux Chromium 1440/390 全部通过；截图为该 run 的 `m16-6-synthetic-browser` 产物。最后文档提交的 SHA 以 Git HEAD/交付消息为准，不在文件中循环引用自身哈希。
- 本机完成 `npm ci`、1077 单元测试、Ruff、100 前端测试、81.45% 前端行覆盖率及 build；Node 18 有 engine 警告。浏览器用隔离 Node 22.23.3 + Playwright 1.64.0/Edge，1440px/390px 截图与交互通过；CI 使用 Node 22 和 Chromium。
- 本机没有可安全运行完整集成测试的数据库和 Docker；完整测试/DDL/容器由隔离 GitHub CI 执行。未对用户业务库写入、迁移或清理。

## 版本与接口

- Alembic 新 head：`0052_m16_6_frozen_research_contracts`，父版本 `0051_m16_5_evidence_archive`；旧迁移不改内容。
- 新表 `agent_frozen_research_contract`、`agent_frozen_contract_manifest` 仅追加；保留 0051 内容/hash/trigger，仅为复合 FK 增加原 Manifest 复合唯一键。
- M14/M15/aggregate/子 Manifest：`m16.6-m14-bundle-v1`、`m16.6-m15-window-v1`、`m16.6-m15-aggregate-v1`、`m16.6-contract-manifest-v1`。
- Report：`m16.6-report-v1` + `m16.6-report-snapshot-v4`；Comparison：`m16.6-report-comparison-v4`。旧 v1/v2/v3 和 AUTO 请求哈希形状不变，旧档案不补历史、不自动升级。
- `GET /api/v1/agent/reports/{id}/contracts?limit=20&offset=0`（limit 最大 50）、`GET .../contracts/{contract_id}`、`POST .../verify-contracts`（空严格 DTO）。
- 原 comparison POST 可选 `STRICT_SAME_SAMPLE` / `DIFFERENT_ASSUMPTIONS` / `WINDOW_DEGRADATION`；intent/mode 组合校验；新增 `GET /api/v1/agent/report-comparisons/{id}/export?format=markdown|html`。
- 所有新路径使用原 Cookie/owner 404；明细仅安全白名单投影，无原 Tool payload、订单、密钥或全量交易日；导出 HTML escape + CSP/nosniff/no-store。
- 算法未重跑，固定 `calculation_reproduced=false`；SHA 不声称抵抗可同时改数据、hash 和触发器的数据库超级用户。

## 36 类验收映射

以下 01–36 全部通过最终功能 CI，均是仓库内可执行测试路径，不使用生产数据库。U=tests/unit，I=tests/integration，V=frontend/src/components。

| 编号 | 场景与核心断言 | 测试证据 |
|---|---|---|
| 01 | 精确 M14 四包冻结 | I/test_m16_6_m14_capture.py、test_m16_6_contract_atomic.py |
| 02 | 混装不同 Run/Period 拒绝 | U/test_m16_6_contract_semantics.py 参数负例 |
| 03 | Period 缺失 Gap；非法/失败包不得完整冻结 | U/test_m16_6_contract_semantics.py Gap/关系负例；原 analytics_bundle 集成测试 |
| 04 | source/config/hash 篡改失败 | U/test_m16_6_contract_integrity.py、test_m16_6_contract_semantics.py |
| 05 | 日期缺失/重复/逆序/count 不符拒绝 | U/test_m16_6_contract_semantics.py |
| 06 | 明确选定报告后新增最新报告，保持原 ID/值 | I/test_m16_6_m14_capture.py |
| 07 | 不同 Benchmark 隐藏 delta | I/test_m16_6_report_api.py |
| 08 | 非支持 currency/frequency 拒绝，不假设相同 | U/test_m16_6_contract_semantics.py |
| 09 | execution/cost/assumptions 差异不授权 | U/test_m16_6_contract_policy.py、contract_semantics.py |
| 10 | 同口径精确 Decimal right-left | U/test_m16_6_contract_policy.py；I/test_m16_6_report_api.py |
| 11 | 同起止日期但交易日集合不同不授权 | U/test_m16_6_contract_policy.py |
| 12 | 样本/假设敏感性只上下文 | U/test_m16_6_contract_policy.py；I/test_m16_6_report_api.py |
| 13 | 相同 Evidence/来源/角色合同内容冲突不能覆盖，缓存相同内容和不同角色正常 | U/test_m16_6_resources.py、test_m16_6_contract_integrity.py；原 test_m16_5_archive_capture.py |
| 14 | canonical/历史 SHA 和 JSON 不变 | U/test_m16_6_contract_canonical.py、test_m16_5_report_binding.py；I/test_m16_5_closeout.py |
| 15 | 合同写入前或子 Manifest 已 flush 后失败，整体回滚回答/Turn/原 Archive | I/test_m16_6_contract_atomic.py before/after_manifest |
| 16 | 同 request_id 恢复无重复合同/调用 | I/test_m16_6_contract_atomic.py；原 test_m16_5_chat_archive.py 网络响应丢失用例 |
| 17 | cache_origin 保留，不发给 LLM | U/test_m16_6_private_capture.py |
| 18 | JSON/hash/owner/FK 篡改 409；未知版本不可核验 | U/test_m16_6_contract_integrity.py；I/test_m16_6_contract_migration.py |
| 19 | 最新业务数据变化不漂移 | I/test_m16_6_report_api.py；test_m16_2_2_research_integrity.py |
| 20 | 真实 Study/Validation/Window | I/test_m16_6_window_end_to_end.py；test_m16_2_2_research_integrity.py |
| 21 | Trial/Evaluation/Run 错配拒绝 | U/test_m16_6_window_semantics.py；I/test_m16_2_2_research_integrity.py |
| 22 | 其他窗口 OOS/包拒绝 | U/test_m16_6_window_semantics.py、test_m16_6_window_policy.py |
| 23 | Train/OOS 与窗口日期不一致拒绝 | U/test_m16_6_window_semantics.py |
| 24 | 不同样本只授权专用窗口退化 | I/test_m16_6_window_end_to_end.py；U/test_m16_6_window_policy.py |
| 25 | Study aggregate 不能替代 Window | I/test_m16_2_2_research_integrity.py；U/test_m16_6_contract_canonical.py |
| 26 | 多窗口分页/顺序变动独立锚点 | I/test_m16_2_2_research_integrity.py；V/ContractArchivePanel.test.ts |
| 27 | 四类 M15 Decimal 公式与符号；percent 单位标为百分点 | U/test_m16_6_degradation.py、window_policy.py、exports.py；I/test_m16_6_window_end_to_end.py |
| 28 | Sharpe NULL 保留、回撤符号不伪造 | U/test_m16_6_window_semantics.py、contract_semantics.py |
| 29 | 旧报告/比较可读可导出，不自动扩权 | U/test_m16_6_report_binding.py、test_m16_4_1_integrity.py；I/test_m16_5_archived_reports.py |
| 30 | Report v4 提交前失败不留已提交行 | I/test_m16_6_report_api.py precommit 回滚 |
| 31 | owner404/非法参数/条数/bytes/timeout；原归档/子合同共享 deadline | I/test_m16_6_report_api.py、contract_migration.py；U/test_m16_6_resources.py；最大窗口容量测试 |
| 32 | 全局/逐项无许可 UI 隐藏 delta | V/AgentResearchReports.test.ts；scripts/m16_6_browser_smoke.cjs |
| 33 | 审计 result 不作显示 fallback | V/AgentResearchReports.test.ts；浏览器审计值不显示 |
| 34 | DATE/IDENTIFIER 上下文不能绕过数值门禁 | U/test_m16_6_contract_policy.py、test_m16_5_context_comparison.py |
| 35 | 未知历史/合同版本不静默解释 | U/test_m16_6_contract_integrity.py、test_m16_6_report_binding.py、test_m16_5_offline_recheck.py |
| 36 | PG17 实际 Adapter→只读捕获→原子 Archive→Report/Comparison API；CI/DDL 回滚 | I/test_m16_6_contract_atomic.py、report_api.py、window_end_to_end.py、contract_migration.py；最新 CI |

差异说明：失败的已有 Period 包由既有精确 Bundle validator 直接拒绝；缺失 Period 冻结明确 Gap。非支持币种/频率在合同语义复核阶段直接拒绝；不制造可以比较的虚假合同。

## 容量与重现

- 单合同 128KiB、单 Turn 1MiB、默认 100 合同、最多 5000 交易日/源报告、离线 5 秒；开关和预算实际位于 `config/agent.yaml`，不是 `.env` 或策略 YAML。
- 最大 36 窗口（现行 planner 上限）的批量读取测量使用真实 PG17/服务产物。最终功能 CI：1/36 窗口均为 14 次 SELECT，分别 0.0304/0.2204 秒，合同 JSONB 31905/1148661 字节。36 窗口 108 合同同时超过默认 100 和 1MiB 硬限；写前拒绝，用户应分页查询（如每次 10 窗口），不能盲目放大硬限。本次观测值不是生产 SLA。
- SQL 批量读取、不按窗口 N+1；离线读取前先统计实际 JSONB bytes/count，超限/超时不伪造成功。
- 本机后端安全命令：`python -m pytest tests/unit`、`python -m ruff check backend tests migrations scripts`。
- 全量测试须显式将 `DATABASE_URL` 指向允许测试的 PG17；M16.6 临时库 helper 另要求 `TEST_DATABASE_URL` 或隔离 CI。不可直接对 `.env` 业务库运行完整测试；helper 不跳过失败。
- 浏览器：安装 Playwright 1.64.0 到独立临时工具目录，设置 `PLAYWRIGHT_MODULE` 为该模块路径，再运行 `node scripts/m16_6_browser_smoke.cjs`。本机可设置 `PLAYWRIGHT_CHANNEL=msedge`；CI 默认 Chromium，自动使用空闲 loopback 端口，结束关闭服务器。合成截图保存在被 Git 忽略的 `frontend/coverage/browser`。

## 依赖风险（独立 P2）

2026-10-13 实际官方 npm registry 审计：11 项（4 critical、3 high、4 moderate），不是 11 个新漏洞。镜像 registry 的 audit 返回 404，不能据此宣称安全；用命令 `npm audit --json --registry=https://registry.npmjs.org` 复查。未执行 `audit fix --force`，未改变应用 lockfile。

`npm audit --omit=dev` 仍报告 4 项（echarts/esbuild/vite/source-map-js，2 high、2 moderate）：当前 package.json 把 Vite/plugin 放在 dependencies，不能用“全是 devDependency”忽略。Compose 前端最终 Nginx 镜像只拷贝 dist，不启动 Node dev/test server；但 ECharts 进入浏览器包，source-map-js/Vue 编译依赖的最终 bundle 影响须随安全升级进一步核查。

| 依赖 | 直接/传递 | 本轮风险判断与后续验证 |
|---|---|---|
| echarts | 直接运行时 | audit 报 XSS，所有图表输入/Tooltip 均须升级评估；新合同 UI 使用 Vue 文本插值/escape 并通过 XSS 测试，不等于旧图表漏洞已修复 |
| vite | 直接开发期 | dev server 路径/文件读取；只绑定 loopback，禁止生产运行 dev server；升级后重测 Vue/代理/build |
| vitest、@vitest/coverage-v8、happy-dom | 直接开发/测试期 | UI server/执行隔离等 critical；只运行可信测试，不对外开放测试服务器；升级后覆盖率/DOM 回归全量执行 |
| @vitest/mocker、vite-node、tinypool、esbuild | 传递开发/测试期 | 分别经 Vitest/Vite 引入；随上游升级，检查 worker/mock、文件访问与测试语义 |
| brace-expansion、source-map-js | 传递 | 拒绝不可信编译/源码输入，升级锁文件后核对实际依赖路径与生产 bundle，不能只看顶级包版本 |

本机默认 Node 18 触发依赖 engine 警告；CI 的 Node 22 与本机隔离 Node 22.23.3 成功执行。本项目工具链至少使用满足依赖 engine 的 Node 22.22.2+（或满足对应 engine 的 24.15+），后续安全升级需单独验证 Node/Vite/Vitest/ECharts 的目标版本，不以本轮测试代替升级验收。

## 上线与回滚

1. 先备份和核对生产目标，隔离 staging 演练 0051→0052；本轮 CI 还验证空库降级再升级、已有合同拒绝降级。生产没有自动迁移或历史回填。
2. 已具备 Python/PG 环境无需重新创建环境；拉新代码并安装锁定依赖后，对核对过的部署库执行 `python -m alembic upgrade head`，再 `current`/`heads` 核对 0052。该命令只变表结构，不拉数据、补因子或重跑研究。
3. 在 `config/agent.yaml` 开启 `agent.archive.enabled` 与 `agent.frozen_contract.enabled`，默认都遵守既有配置，本轮 frozen_contract 默认 false。重启 API 后仅新 Turn 捕获合同；旧报告保持原权限。该能力不要求重拉 Raw 或补算因子。
4. 新报告在“研究报告”页显示合同与独立复核状态；显式选同样本/敏感性/窗口模式。TRAIN/OOS 必须先让工具选择同一个精确窗口，而非 Study aggregate。
5. 回滚优先关闭 frozen_contract 捕获，保留 0052 表、已有 v4 兼容读取；若退到不认识 v4 的后端，先隔离该报告入口。已有合同禁止强行 downgrade/DELETE；不删除用户报告、不复写 hash。前端需要和兼容后端一起部署。
6. 监测合同缺口/冲突/超时/字节/数目、比较授权与页面耗时。当前日志禁止源 payload/凭据；档案无隐式 TTL，容量接近上限时采用分页/明确资源拒绝，不能在线“修复”历史档案。

## Definition of Done

- [x] 无最新 DB 补历史路径；工具执行当时、同一只读来源事务捕获。
- [x] M14 四包/日期/基准/执行/会计/版本保存且离线核验。
- [x] M15 Study/Validation/Window/Trial/Train/OOS/双 M14 包真血缘核验。
- [x] 合同、子 Manifest、原 Archive、Assistant、Turn 共同提交；写前和写后异常共同回滚。
- [x] 旧 Manifest/Report/Comparison/Hash 保持；旧报告不静默升级；AUTO 幂等兼容。
- [x] 全局及逐项双门禁，未经授权无 delta/排名；审计 result 不作 UI/导出 fallback。
- [x] 同窗口 M15 原 Decimal 公式、正确符号、Sharpe NULL 和百分点语义；缺口安全降级。
- [x] 明确错误码、独立层级、未知版本拒绝解释、owner404、分页/取消/错误恢复/XSS。
- [x] 隔离 PG17、全量 pytest/Ruff、前端 coverage/build、Docker、双视口浏览器全部通过；0052 current=heads。
- [x] 真实功能 SHA/CI、36 类矩阵、开关、容量、无损回滚及 P2 风险已记录。

生产上线仍需用户核对连接目标、备份、staging 演练和开启开关；镜像构建/隔离 CI 成功不等于生产 DB 或 LLM 运行时连接已验证。继承 npm 告警 11 项和默认 Node 18 engine 警告仍是已披露的独立升级风险，不声称“安全问题全部消失”。
