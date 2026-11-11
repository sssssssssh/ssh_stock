# BIZ-PERF-P1-03 归因交付回执

## W00 基线和授权

开工时本地 `master`、HEAD、`origin/master` 与实时 GitHub `master` 均为 `f9d12d66e73405e17425822769cd9aff560c00c3`，工作区和 index 干净。按仓库治理与业务权威边界检查范围。相对 `1fbb98c5b189be2a49fb9f576fc27d72fd9e853a` 仅新增两份 P1-02 归档文档，治理和业务源码未漂移。Git 传输的 `ls-remote` 在 github.com:443 超时；实时值另经认证的 GitHub refs API 与 GitHub 连接器交叉确认。

本轮授权为只读源码与归档核验、离线统计、文档提交推送和普通自动 CI。真实 PG17、云库、Worker/Scheduler、OFF/ON、容量、一次性 Actions、部署及手动重跑均未执行。归档仅新增本回执及[整链热点归因](BIZ_PERF_P1_03_ROOT_HOTSPOT_ATTRIBUTION.md)。无需新解析器和测试文件，已用 Python 标准库一次性离线读取现有 JSON/GZIP。

### 工程 CI 台账

| 运行 | SHA、尝试和状态 | Job / Step |
|---|---|---|
| [P1-02 归档 Main CI 42975755604](https://github.com/sssssssssh/ssh_stock/actions/runs/42975755604) | `f9d12d66e73405e17425822769cd9aff560c00c3`，attempt 1，开工及交付前只读查询均 `in_progress`，结论 `PENDING` | [test 130374329879](https://github.com/sssssssssh/ssh_stock/actions/runs/42975755604/job/130374329879) 的 step 24 全量 pytest 正在运行，尚无失败节点可定位。dependency-audit、workflow-contracts、lookup-diagnosis 完成并通过。authorize、ui-visual-acceptance、lookup-tail-attribution、capacity 跳过。 |
| [更早的基线 Main CI 42954512719](https://github.com/sssssssssh/ssh_stock/actions/runs/42954512719) | `1fbb98c5…`，attempt 1，`completed/failure` | 全量 pytest 6,681 通过、1 失败、1 跳过。从 artifact `13829230685` 的脱敏 JUnit 定位 `tests/unit/test_a42341_environment_guard.py::test_A42342_T16_T18_real_cli_corruption_and_wrong_identity_rejected[failure]`。以旧 SHA 测试源码中的参数唯一匹配 JUnit 后缀哈希。失败断言已脱敏，原因仍 `UNKNOWN`。 |
| P1-03 归档提交 | 自动 CI 按推送后的精确 SHA 查询 | 无手动 dispatch 或 rerun。 |

工程 CI 与性能判断分列。P1-01 是局部微基准 P95 超限、`NO_MEASURABLE_GAIN`，源码已撤回。P1-02 是测量汇总失败导致首档未落盘、`INCONCLUSIVE`，源码已撤回；候选 GREEN 不替代撤回后源码测试。P1-02 Windows 的 `WinError 1314` 仅为既有符号链接环境失败。三个事实均未改写旧证据。

## W01–W04 证据、执行与停止点

仓库外保留 `.codex_tmp/biz_perf_p1_03/`。其中 `source_inventory.md` 为 W00 源码盘点与基线 Git blob，`source_hashes.sha256` 记录 59 个治理、源码和证据输入的精确路径及工作字节 SHA256，`evidence_matrix.json` 含 15 行脱敏归因矩阵，另有开工与交付前 GitHub Job/Step 快照及历史失败节点的 artifact/JUnit 哈希。原始 SQL、参数、凭据与业务行情不入 Git。

| 核心证据 | SHA256（本地读取字节） |
|---|---|
| `biz_perf_01/baseline.json` | `3ef6caf2835b7f50e4349d7fe0990561238191d95deefc505ae51f80f49ded15` |
| `biz_perf_01/end_to_end.json` | `f4a11fd58c0b2b5ccb36351edc8a2f86c5cc01b045d50660c2db2fd645ff848d` |
| `biz_perf_01/raw/1m-0-old.json.gz` | `f622f04f64dfe567c319ff4a68f6f57a33bdb200ca62debf3f4312c52f2ec0ca` |
| `biz_perf_01/after.json` | `88a1aa607024073f325aa02790d20205f24dc66ebec2b0b3f35e48efa358cd74` |
| `biz_perf_01/query_counts.json` | `a63060c9b5e4d635a8c25a790c9f4e051f0a4b1b893d128c581307fc3341a266` |
| `biz_perf_01/validation.json` | `e68d848f786adf4cd2ad7c40ca2e5b5361f871f760eb092e9f2fafdaba406b41` |
| `biz_perf_03_a_r1/localization.json` | `2d69588428e83cdc007636639a3ce92524bbb03c4b6a928f08e003077f86e242` |
| `biz_perf_03_a_r1/verification.json` | `a1ad816568ba6397185b3b2fba72680068642394c1c0ebe66ce8abed65a84d8d` |
| P1-02 仓库外 `local_attribution.json` | `124982898b891fc7bc77b3cc116e1c8c636e09b74524264455f486286e4fc06e` |
| 仓库外完整 `source_hashes.sha256` | `85073d0d574ff1d53d92c50653de81f7225b3b9c7a5d41007ff25653b71e2191` |
| 仓库外 `evidence_matrix.json` | `77b355ce5315d532c3e07667498ac18d3dc51d13db0bea577a6b38dac5b00df8` |

| 实际验证 | 结果 |
|---|---|
| `git status --porcelain=v1`、`git rev-parse HEAD origin/master`、`git ls-remote origin refs/heads/master` | 本地版本与范围已核对。直连超时后用 GitHub API 核实远端。 |
| GitHub GET `git/ref/heads/master`、`actions/runs/42975755604` 及其 jobs/artifacts；读取历史 artifact `13829230685` 的脱敏 XML | 核对精确 SHA、attempt、Job、Step 和历史失败节点，只读。 |
| `python -B -`，仅标准库 `json/gzip/hashlib` 及只读 Git | 交叉核对 18 条历史样本、相同记录和已归档 SQL 计数，复算 Top 3。检查 R1 OFF 缺 receipt、P1-02 首档无已落盘样本及恢复 blob。退出 0。 |
| `python -m ruff check --no-cache backend tests migrations scripts` | Ruff 0.16.4，通过，退出 0。 |
| `git diff --check`、`git diff --cached --check` 与暂存文件范围检查 | 通过，只包含两份归档文档。 |
| pytest / 新测量 | `NOT_RUN`。本轮仅文档及离线数据核对，未新增脚本/单测，无性能样本生成。 |

AC-01～AC-05 的基线、授权、同记录数字、计量边界和前序撤回证据均已记录。AC-06～AC-07 的当前热点为 `NONE_PROVEN`，历史方向优先考虑 `calculate_stock_factors`。仅提出一个隔离合成根观测，需另行授权。AC-08～AC-10 的交付范围、静态检查和未测状态见本回执。

```text
SOURCE_MUTATION=NONE
ROOT_OBSERVATION=HISTORICAL_ONLY
ROOT_HOTSPOT_NOT_PROVEN
CURRENT_HOTSPOT=NONE_PROVEN
HISTORICAL_TOP3=factors.compute > recalculation.raw_prerequisites > candidate_lookup_batch
NEXT_SINGLE_HOTSPOT=PROVISIONAL
PG17_ISOLATED_TEST=NOT_RUN
REAL_ROOT_OFF_ON=NO_GO
PERFORMANCE_GAIN=NOT_CLAIMED
D04_OWNER=PENDING
R1=PARTIAL
NEXT=CHATGPT_INDEPENDENT_REVIEW
```
