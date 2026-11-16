# BIZ-PERF-FACTOR-RECOVERY-03-R3 closeout

日期：2026-11-16。STATUS=PHASE_A_FROZEN_CHAIN_BLOCKED / REVIEW_PENDING。
WORKER_FIXED=false；WORKER_NATIVE_RED_GREEN=NOT_RUN。
本轮仅新增本报告，没有修改生产、Controller/Seed、原测试、路由或旧合同。
没有暂存、提交或推送。NEXT=CHATGPT_INDEPENDENT_REVIEW。

## 基线与范围

master，HEAD=origin/master=已认证 GitHub master：
232baf9e13cd7b23731e59188c86e0e253c3a394。
GitHub 使用只读 fetch_commit(master) 核对，没有拉取、checkout、重跑 CI。
AGENTS、五治理及业务权威边界沿用本持久会话已读版本，重新核对文件摘要；
本轮读取 R3 任务书、R2 closeout、相关源码和冻结引用。
全部既有未跟踪文件保留，尤其 tests/unit/test_source_contract_r1_history.py。

本轮停止依据是任务书优先级 A.3：
“检查所有引用和冻结链；发现更深层无法在白名单内解决，报告准确阻断而不是继续造框架。”
以及末段“遇到超出白名单或安全边界立即停止”。
不是自动审批拒绝，也没有请求扩大权限、安装依赖或启动真实环境。

## 新确认的精确冻结链及影响

1. scripts/r1_integration_seed_loader.py:93，original_fixture_oracle 直接调用
   verify_business_sources()；当前 FrozenSeed 行为经该入口校验实际业务源码。
2. scripts/r1_integration_evidence.py:82–94，旧入口遍历旧 schema sources，
   验证实际文件规范化 LF 的完整 SHA256；Worker 在该集合内。
3. tests/unit/test_r1_reviewed_snapshot_v2.py:46–49 的 FROZEN 表，
   固定 SeedLoader 完整文件 LF/CRLF 两种摘要：
   6a8cd5ae64a81fa2d9bd992e2820616248ccba521f27740686743ab949f41a2e、
   5d000bb6bbf7c4a6c8047638b2db6de05b4631f2cba35215fef9c235bb3c04de。
4. 同文件:621–631 的
   ReviewedEvidenceTests.test_T26_all_frozen_boundaries_and_oracle_authorship
   在同一节点先检查八个原文件摘要，再检查当前 oracle 的 approval、reviewer、
   authorship 及三份 fixture 原字节摘要。

该测试文件不在 R3 白名单。T26 是混合节点，不能把整个节点当作纯历史节点路由，
从而丢失其对当前 oracle/fixture 的检查；R3 只允许真正历史性质节点历史执行。
也不能给 FROZEN 换摘要、接受新旧任选摘要、忽略 SeedLoader、patch 校验恒真，
或使当前测试读取旧 Worker 后宣称已校验当前 Worker。

因此显式 v2 SeedLoader 调用点虽然已经授权，其直接修改会确定性触发这一额外节点。
仅增加 v2 manifest 或路由 AC31 不能消除该约束。
本轮没有擅自将混合节点整体历史化，也没有另造隐式上下文选择来改变旧 v1 语义。
这里证明的是直接显式调用点方案受阻，不声称已排除所有未来经审阅的设计。

独立审阅需要裁决的最小范围：是否允许在上述白名单外测试中分离
“固定旧源码字节检查”与“当前 oracle/fixture 检查”，保持所有原断言及当前覆盖，
再仅对纯历史部分建立精确路由。没有该裁决，本轮不改此文件、不扩通用框架。

## 受控原测试正例与内存 RED

命令：仓库根 python -X utf8 -B -，运行下方脚本；退出码 0。
完整原 unittest 方法运行，没有抽取测试 AST、没有修改断言、没有写入源码。

| 视图 | testsRun | failure | error | 含义 |
|---|---:|---:|---:|---|
| 原工作树 | 1 | 0 | 0 | T26 基线正例通过 |
| 仅 SeedLoader 读取内存替换为显式 v2 调用 | 1 | 1 | 0 | 原摘要断言检测到变更 |

内存变更后 SHA256：
340a5fa72dd14e73da899711e6bdc765287b5186f6699bddaf0cd3d1519ce917。
失败明确是该摘要不在原两个允许摘要内；不是 CRLF 假阳性。
替换读取仅命中 SeedLoader 一次，结束后原文件原字节仍相同。
这是冻结链诊断 RED/基线正例，**不是合同迁移 GREEN，更不是 Worker 修复 RED/GREEN**。

```python
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "r3_frozen_probe", "tests/unit/test_r1_reviewed_snapshot_v2.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
node = "test_T26_all_frozen_boundaries_and_oracle_authorship"

def run():
    result = unittest.TestResult()
    m.ReviewedEvidenceTests(node).run(result)
    return result

original = Path.read_bytes
seed = Path("scripts/r1_integration_seed_loader.py").resolve()
base = run()
assert base.testsRun == 1 and base.wasSuccessful()
old = original(seed)
changed = old.replace(
    b"    verify_business_sources()",
    b'    verify_business_sources(version="r1.current-business-sources.v2")', 1
)
assert changed != old
reads = []

def read(path):
    if path.resolve() == seed:
        reads.append(path)
        return changed
    return original(path)

with patch.object(Path, "read_bytes", read):
    red = run()
assert red.testsRun == 1 and len(red.failures) == 1 and not red.errors
assert len(reads) == 1 and "AssertionError" in red.failures[0][1]
assert original(seed) == old
print("BASELINE_PASS_1 EXPECTED_HASH_RED_1 NO_SOURCE_FILES_WRITTEN")
```

## 原 12 节点逐项归属

以下分类保持 R2 结论；本轮没有迁移任何节点，也没有重新宣称 12 项通过。
完整前缀均为 tests/unit/。

| 文件 / 类 / 方法 | 归属 |
|---|---|
| test_r1_integration_controller.py / ControllerTests / test_composed_real_adapters_fake_io_not_just_callback_labels | 当前组合适配器行为，必须当前树验证 |
| test_r1_integration_seed_loader.py / SeedLoaderTests / test_AC07_generate_once_complete_original | 当前完整 fixture 生成 |
| 同上 / test_AC08_default_timestamps_frozen | 当前默认时间戳冻结行为 |
| 同上 / test_AC09_sequences_and_catalog_exact | 当前序列及 catalog 精确性 |
| 同上 / test_AC10_independent_dual_loads_and_entity_values | 当前双臂独立及实体值 |
| 同上 / test_AC11_source_tampering_partial_duplicate_theme_type | 当前篡改/缺失/重复拒绝 |
| 同上 / test_AC12_no_plan_only_proof_or_live_loading | 当前拒绝计划冒充证明/真实加载 |
| 同上 / test_all_frozen_timestamps_and_absent_nulls_have_explicit_origins | 当前时间及 null 来源 |
| 同上 / test_capture_callback_once_row_order_and_catalog_index_tamper | 当前单次捕获及篡改拒绝 |
| 同上 / test_capture_does_not_trust_replaced_generator | 当前独立校验负例 |
| 同上 / test_independent_oracle_catches_orm_default_not_generator_self_comparison | 当前独立 oracle 负例 |
| test_r1_real_root_protocol.py / ProtocolTests / test_AC31_source_sha_and_every_new_utf8_file | 固定源码字节历史候选；尚未注册路由 |

R2 的 29 项是此前分类/边界保护结果，本轮未重跑，不计入本轮新通过数。
Controller/Seed 原行为和 R2 现有测试均保持原文件；当前 v2 等价覆盖未完成。

## Worker 与环境限制

backend/app/services/job_worker.py:464–465 仍会在 Thread.start 失败后对非空但未启动
的线程 join(timeout=5)。生产缺陷尚未修复；未进入优先级 B。
预期修复方向仍为仅在 start 确实成功后 join，保留正常 timeout 和 join 异常传播，
但本轮没有写补丁或用 AST 模拟冒充原生验证。

本轮 importlib.util.find_spec 检查：fastapi、loguru、ruff 均缺失。
没有导入应用或读取 .env，没有安装依赖。
原生 Worker pytest、全量 pytest、Ruff 均 NOT_RUN / ENV_BLOCKED；
此前 Worker 收集缺 fastapi 的结果见 R2，不虚报本轮执行。
git diff --check：退出 0（已跟踪文件无 diff）；新报告另行检查尾空白。
没有新 SHA、Linux CI、新合同正反例或 Worker 故障矩阵验收。

## 保全与真实执行门禁

1646 个已跟踪文件原字节 SHA256 排序 JSON 映射摘要，开始与结束一致：
702a421ae1366d401ccccd0df2c665ac0edb45f8978907cc66241b4650898a8e。
所有已有未跟踪文件未写入；本轮精确新增只有本报告。

五冻结 Git blob（工作树规范化内容核对不变）：

| 路径 | blob |
|---|---|
| scripts/business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| scripts/biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| scripts/perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| scripts/biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| scripts/business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

A42331 安全插件 blob=64fb3709d5bd74ca1a407c87c461a4c52acaff67，未改。
没有更改旧 schema/hash、A42366 常量、CI、依赖或任何 Raw/Derived。
REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；SQL/MIGRATION=NOT_RUN；
REAL_FACTOR_RUN=NOT_RUN；PERFORMANCE/CLOUD=NOT_RUN；ROOT_ATTEMPTS=0。
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。
业务计算与心跳缺陷仍待解决，等待 ChatGPT 独立审阅该精确冻结链交接。
