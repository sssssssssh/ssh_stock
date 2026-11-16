# BIZ-PERF-FACTOR-RECOVERY-03-R4 closeout

日期：2026-11-16。
STATUS=PATCH_IMPLEMENTED / CONTRACT_TESTED / WORKER_NATIVE_ENV_BLOCKED。
WORKER_FIXED=NOT_YET_VERIFIED；WORKER_NATIVE_RED_GREEN=NOT_ACHIEVED。
NEXT=CHATGPT_INDEPENDENT_REVIEW。没有暂存、提交、推送或触发 CI。

本轮已经实施 R4 授权的 T26 拆分、当前业务来源 v2 和 Worker 最小保护，
没有再次停在 R3 已获授权的范围问题上。
合同测试通过；但 Worker 原生测试在修复前后均因依赖缺失无法收集，
因此本任务的原生 Worker RED/GREEN 验收尚未完成，不能宣称 Worker 已验收修复。

## 基线和保留输入

master；HEAD=origin/master=已认证 GitHub master：
232baf9e13cd7b23731e59188c86e0e253c3a394。
GitHub 使用只读 fetch_commit(master) 核对；没有 fetch/checkout/reset 分支。
AGENTS、治理及业务权威边界沿用同一持久会话已读版本，重新核对五治理摘要；
读取 R1–R3 closeout、R4 任务书及相关源码。
未启动另一个 Codex writer。此前已有的任务、报告和测试均保留。
既有未跟踪 tests/unit/test_source_contract_r1_history.py 按 R4 白名单继续修改，
其余既有未跟踪文件未写入；原文件没有被删除来消除阻断。

## 精确修改范围

修改 9 个已跟踪文件：

| 文件 | 实际整改 |
|---|---|
| scripts/r1_integration_evidence.py | 保留默认 v1 校验；增加显式 v2 分派、固定 manifest 摘要和全文件检查 |
| scripts/r1_integration_controller.py | 唯一 preflight 校验调用显式选择 v2 |
| scripts/r1_integration_seed_loader.py | 唯一 oracle 校验调用显式选择 v2 |
| scripts/source_contract_governance.py | 新增独立 R1 固定 commit/tree、精确路径和唯一 AC31 节点；旧 A42366 常量未改 |
| scripts/source_contract_history.py | 新增只读 Git 对象检查与唯一 R1 AC31 隔离执行；旧执行分支保留 |
| scripts/source_contract_pytest.py | 收集阶段仅替换精确 AC31 unittest 节点，避免父进程运行其生命周期 |
| tests/unit/test_r1_reviewed_snapshot_v2.py | 拆分历史冻结字节与当前 oracle/fixture 断言 |
| backend/app/services/job_worker.py | start 成功标记及 join 条件，三个窄位置 |
| tests/unit/test_job_worker.py | 新增当前模块原生 pytest 夹具及 7 个参数展开回归用例，原测试不删不改 |

修改 1 个既有未跟踪文件：tests/unit/test_source_contract_r1_history.py，
保留原 Controller 正反例，扩充 v2/历史来源拒绝、T26 保全与隔离节点检查。
原“拟议 Worker 修改”探针改为追加内存篡改字节，避免依赖旧 join 条件文本。

新增 2 个文件：
- docs/acceptance/r1_current_business_sources_v2.json；
- 本报告。

没有修改两个原 Controller/Seed 测试文件、旧 schema、旧 hash、历史原断言、
安全插件、CI、依赖、迁移或其他生产文件。

## T26：历史和当前分别验收

原名 test_T26_all_frozen_boundaries_and_oracle_authorship 保留，
现在只验证固定历史树中的八份文件。
FROZEN 八项和全部摘要字面量原样保留，没有接受新旧任选摘要。
read_r1_historical_file 验证：

- commit=232baf9e13cd7b23731e59188c86e0e253c3a394；
- tree=d21c4a1d870c68177175ebee276b7c1f350345f7；
- 精确注册版本、路径、普通 blob 类型及 100644 模式；
- Git blob 对象内容和对象 ID 一致；Git replacement 禁用；
- 缺失对象、未知版本/commit/path、树不符、blob 篡改拒绝。

该只读检查没有 checkout、网络或工作树写入。
原测试代码和 fixture 仍保存在该固定 Git 树中；路径也可由同一只读 helper 验证。
没有发现此测试文件自身的新增上游冻结引用需要越界修改。

新增 test_T26_current_oracle_authorship_and_fixture_bytes 始终读取当前工作树，
保留 approval=PENDING_D04、reviewer=NOT_SIGNED、原 authorship 和三个 fixture
SHA 检查，未加入历史路由。
原当前断言语句与拆分后断言的 AST 逐项相同；FROZEN AST 相同。
这是静态保全检查，行为证明另外由真实 T26 方法及 oracle 损坏负例完成。
oracle approval 内存损坏被当前原断言捕获。

## 当前来源 v2 与旧 v1

version=r1.current-business-sources.v2；baseline 固定为完整 232baf9 SHA；
purpose=OFFLINE_INTEGRITY_ONLY；execution_authorized=false。
manifest 完整覆盖旧业务源 18 个文件，以及当前 Controller、SeedLoader，共 20 个。
Worker 必须与当前实际磁盘字节的规范化 LF SHA256 相等，不从 HEAD 推定。

manifest SHA256：
9d7cd00c9883a04a65e147ef71611015340955503dce2b36227db940d1b799f6。
当前 Worker LF SHA256：
7f137e4db226711697b4128028d2e6b4a495da1508d740c1215e0420870b2d44。

manifest 的固定摘要由 verifier 常量绑定；manifest 不包含自身或 verifier，
避免自摘要递归。它不是执行许可，也不替代现有运行时安全验证。
读取前检查文件及父目录链接，未知版本、缺文件、链接、错误摘要、
manifest/路径集合变更均拒绝，没有 fallback 或 hash bypass。
v2 对文本统一 LF，独立校验旧 schema 的原固定规范化摘要，
没有改旧 load_schema，也没有给旧 v1 接受额外摘要。

verify_business_sources() 默认仍走旧 v1 sources/原校验。
Worker 新字节使旧 v1 在当前树拒绝 INTEGRATION_BUSINESS_DRIFT，测试明确保留此事实。
当前 Controller/Seed 显式选择 v2，真实当前组合行为和独立 oracle 正反例继续执行，
没有 patch verify_business_sources=True，也没有把它们送往历史树。
原 SeedLoader 全 10 项、Controller 全文件均参加本轮回归。

原 12 节点归属保持 R2/R3 逐项结论：Controller 组合 1 项、Seed 10 项是当前行为；
仅 ProtocolTests.test_AC31_source_sha_and_every_new_utf8_file 是历史字节节点。
没有整目录、整类或通配历史化。

## AC31 隔离与严格计数

只注册唯一精确 AC31 node。父 pytest 收集时换为无 unittest Class 父级的 Item，
不会先执行当前 setUpClass/setUp/body/tearDown。
子进程在独立临时本地 clone 中 checkout 固定旧树，
先验证 commit/tree、原测试 Git 对象及当前未改的原测试字节。
没有 fetch/network；临时 clone 仅写入新建、受控 .codex_tmp 子目录，未写仓库根 .git。
环境去除 DB/PG/pytest 注入变量，禁止 .env、网络、shell 和再次启动外部子进程。
原 A42366 的 commit/tree、路由列表、73 项语义和原 validate_result 定义未改。

原 unittest 方法完整执行，子进程额外观察其原 setup/body/teardown 调用，
只接受依次各一次；不替代原方法，不吞异常。
JUnit 必须恰好一 suite、一唯一 case，计数 1，零 failure/error/skip，退出 0，
并精确匹配 tests.unit.test_r1_real_root_protocol.ProtocolTests 和原方法名。
返回 receipt 标注固定历史 SHA、HISTORICAL_ONLY_NOT_CURRENT_AUTHORITY，
performance_eligible=false、g1_authorized=false，不授予真实执行权限。

实际额外探针将父进程当前类的 setUpClass/setUp/body/tearDown 全部设为抛错，
精确 AC31 历史节点仍通过（1 passed，1.54 秒，退出 0）；说明未偷跑当前生命周期。
随后补强子生命周期及精确 JUnit 检查，最终回归再次通过。

## Worker 最小 diff 和未完成验收

```diff
 heartbeat_thread: threading.Thread | None = None
+heartbeat_started = False
 ...
 heartbeat_thread.start()
+heartbeat_started = True
 ...
-if heartbeat_thread is not None:
+if heartbeat_thread is not None and heartbeat_started:
     heartbeat_thread.join(timeout=5)
```

start 未成功时不 join；成功后仍以 timeout=5 join，不捕获正常 join 错误。
失败记录、owner/token、CAS、取消/失权、发布、事务和已有清理代码未修改。
没有通过捕获 RuntimeError 吞掉 join 异常。

新增测试直接使用当前 execute_claimed_job、真实 update_job/CAS SQL 编译，
Session、线程及外部业务执行为假对象；不启动 OS 线程或 Worker 服务：

| 测试 | 目标（均尚未执行成功） |
|---|---|
| test_heartbeat_start_failure_records_failed_without_join_or_replay | 原 start 错误记录 FAILED，不 join、不执行业务、不重放；清理上下文 |
| test_started_heartbeat_keeps_join_timeout_and_error[False/True] | 正常 join=5 与原 join 异常对象传播；上下文清理 |
| test_heartbeat_cleanup_preserves_cancel_and_ownership[两类型] | 取消/失权分支，回滚，不发布、不执行业务 |
| test_heartbeat_start_failure_allows_next_poll | 真实 _run_worker_loop 配假 Session/claim，首任务失败后下次 poll 执行另一任务 |
| test_heartbeat_start_failure_cannot_override_lost_cas | 真实 repository CAS 返回 0 时不伪造 FAILED，失权传播与清理 |

这些是 5 个函数、7 个参数展开用例。外部 publication/cancellation 边界使用假对象，
不能单独证明真实数据库发布/取消竞争；原相关回归保留但本机同样受缺依赖阻断。
未运行 AST Worker 模拟来替代原生测试。

## 实际命令与结果

| 检查 | 实际结果 |
|---|---|
| 修复前 python -X utf8 -B - 安全启动 pytest test_job_worker.py -k 指定新用例 | 退出 1；缺 fastapi，收集错误；0 测试执行，非缺陷 RED |
| 合同首次四文件原生回归 | 77 passed，62.63 秒，退出 0 |
| 扩展至五文件、Worker 新字节进入 manifest 后 | 86 passed，65.85 秒，退出 0 |
| 最终五文件原生回归 | **88 passed，65.61 秒，退出 0** |
| 旧保护 24 项 + 受影响历史/T26 3 项 | **27 passed，12 deselected，3.24 秒，退出 0**；其中 3 项与 88 组重复，不能相加作唯一测试数 |
| v2 不提供旧 schema LF 读取替身的独立检查 | 1 passed，0.03 秒，退出 0；与 88 组重复 |
| 修复后 Worker/candidate_write/replace_slice/factor_service_cancellation 原生回归 | 退出 1；4 个收集错误，分别缺 fastapi/loguru；0 测试执行，ENV_BLOCKED |
| python -B -m ruff check backend tests migrations scripts | 退出 1；No module named ruff，ENV_BLOCKED |
| 修改 Python 文件 AST 与行长 | 通过，全部行长不超过 100；不能替代完整 Ruff |
| git diff --check | 退出 0；新文件另查尾空白 |

最终历史路由补强时出现过一次 2 failed/25 passed：
JUnit 精确类名最初误用无 tests.unit 前缀，新增拒绝检查正常失败；
读取实际 case 元数据后改为精确完整类名，随后 27 项及最终 88 项通过。
没有为通过而接受任意后缀、跳过 JUnit 检查或放宽失败/skip 计数。

默认 Python 及两个已有 Conda 环境均未提供完整依赖；没有安装、升级或造依赖替身。
没有执行全量 pytest；当前原生业务测试不能收集，且真实 PG 集成不在授权范围。
多文件测试结束时 pytest atexit 清理既有 pytest-current 路径出现 WinError5 警告，
测试退出码仍为 0；没有删除该用户路径或越权。

五文件安全复现脚本（仓库根 python -X utf8 -B -）：

```python
import os, sys, platform
from pathlib import Path
from unittest.mock import patch
import pytest
platform.platform()
def guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        if Path(os.fsdecode(args[0])).name == ".env":
            raise AssertionError("NO_ENV")
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "os.system"}:
        raise AssertionError("NO_EXTERNAL")
sys.addaudithook(guard)
sys.path.insert(0, str(Path("tests/unit").resolve()))
original = Path.read_bytes
def lf(path):
    raw = original(path)
    return raw.replace(b"\r\n", b"\n") if path.name == (
        "r1_business_compare_schema_v1.json"
    ) else raw
with patch.object(Path, "read_bytes", lf):
    result = pytest.main([
        "tests/unit/test_source_contract_r1_history.py",
        "tests/unit/test_r1_reviewed_snapshot_v2.py",
        "tests/unit/test_r1_integration_seed_loader.py",
        "tests/unit/test_r1_integration_controller.py",
        "tests/unit/test_r1_real_root_protocol.py",
        "-q", "-p", "no:cacheprovider",
    ])
raise SystemExit(result)
```

Windows 旧 load_schema 钉住 Linux LF 原字节，故只有该旧 schema 读取使用 LF 内存视图。
当前 Worker/Controller/SeedLoader 不换回旧字节；没有改任何原断言。
v2 自身已独立验证在无此读取替身时可用。
本组是当前原测试方法原生执行与有限平台模拟，不等同于新 SHA Linux CI。

Worker 修复前后安全启动均安装 .env/网络/子进程禁止 hook；
修复后另以 Engine.connect 拒绝一切连接，再调用上表四文件 pytest。
收集在缺依赖处终止，没有应用连接、真实 SQL、服务启动或业务数据访问。

## 保全与门禁

除 9 个白名单 tracked 文件外，其余 1637 个 tracked 文件保持基线原字节：
将这 9 个路径在内存恢复 HEAD 原字节和既有行尾后，全体 1646 文件排序 JSON
SHA256 映射恢复为 R3 基线值：
702a421ae1366d401ccccd0df2c665ac0edb45f8978907cc66241b4650898a8e。
原 reviewed_snapshot 测试为 LF，其余八文件为 CRLF，最终保留各自原行尾。

五冻结 blob 与工作树规范化内容一致：

| 文件 | Git blob |
|---|---|
| scripts/business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| scripts/biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| scripts/perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| scripts/biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| scripts/business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

A42331 安全插件 blob=64fb3709d5bd74ca1a407c87c461a4c52acaff67，未修改。
无暂存、提交、推送、新 SHA 或 CI dispatch。
REAL_PG17=NOT_RUN；REAL_WORKER_SERVICE=NOT_RUN；REAL_SQL/MIGRATION=NOT_RUN；
REAL_FACTOR_RUN=NOT_RUN；PERFORMANCE/CLOUD=NOT_RUN；ROOT_ATTEMPTS=0。
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。

剩余验收：具备既有依赖的获准离线环境中，先对未加布尔保护的旧 Worker 字节运行
新增当前模块测试取得真正 RED，再对当前补丁取得 GREEN，完成原取消/发布回归和 Ruff；
独立审阅后若另行授权交付，再核查新 SHA Linux CI。
目前补丁应按“合同已验证、Worker 原生未验证”审阅，不能据本报告宣布真实因子计算恢复。
