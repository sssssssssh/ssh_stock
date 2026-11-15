# BIZ-PERF-FACTOR-RECOVERY-01 closeout

- TASK: BIZ-PERF-FACTOR-RECOVERY-01
- BASELINE_SHA: 883c369c7700b16557b9833f5042b071be886f01
- 分支 master；开始时 HEAD、origin/master、已认证 GitHub master 一致。
- ROOT_CAUSE_STATUS: PROVEN_SCOPED_COOPERATIVE_CANCELLATION_GAP
- FACTOR_RUN_STATUS: SCOPED_FIX_IMPLEMENTED / SOURCE_ONLY_VALIDATED / REAL_RECALC_NOT_RUN
- DB_STATUS: NOT_CONNECTED_UNTOUCHED
- B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0
- NEXT=CHATGPT_REVIEW；未暂存、未提交、未推送，无新 SHA CI。

## 范围与结论

本任务是用户新的业务实现授权，替代旧任务指针，但没有解除真实性能实验及数据库准入禁令。
已按 AGENTS.md 阅读五治理文件和相关业务权威文档，并检查现有实现与测试。
只修改一个生产文件，新增一个单测文件及本报告；任务书原字节保留，前轮 W05 两文件保留。

发现一个可复现的具体问题：默认所有优化关闭、无 input_window 时，FactorService
把 check_cancelled=None 传给真实因子引擎，因而跳过引擎已存在的五个取消/归属检查点。
Raw 读取结束后发生取消或 execution_token 变化，默认 CPU 计算仍继续，直到后续外围检查。
开启优化时已有这些检查，取消语义不应依赖优化开关。
这会延迟停止、占用数据任务串行执行位置，但不能据此断言它就是用户历史报错、
Worker 挂起或写入慢的唯一原因，也不能宣称真实性能已恢复。

最小修改是无条件传入现有 checkpoint；无新增检查位置，无公式、阈值、身份或发布逻辑修改。
这是协作停止，不是强制抢占：单次 pandas/NumPy 运算或 SQL 中仍需等到下个已有检查点。
真实 Execution 下完整非空 chunk 多出最多五次短观察 SELECT，可能有开销；没有速度提升实测。

## 精确业务调用链与边界

| 环节 | 当前源码入口 | 行为、事务与状态 |
|---|---|---|
| 用户入口 | frontend/src/App.vue submitRecalculation；frontend/src/services/api.ts enqueueRecalculateJob | 对已有 Raw 日期范围发起 POST /api/v1/jobs/recalculate |
| API | backend/app/api/v1/jobs.py enqueue_recalculate_job、_enqueue_job | 日期/交易日校验、manual 或 dirty 范围；API 只入队，不计算 |
| 入队 | backend/app/services/job_guard.py create_queued_ingestion_job、_acquire_ingestion_advisory_lock | PG 事务 advisory lock，fingerprint 去重、活跃任务/队列/依赖检查，插入 QUEUED 后 commit |
| 领取 | backend/app/jobs/job_worker.py _run_worker_loop、claim_next_job | 独立 Session，advisory lock、队首行锁；数据 lane 单 RUNNING，FIFO，记录 owner/token 后 commit |
| 执行 | 同文件 execute_claimed_job | 检查 RUNNING/owner/token，设置 Execution、超时、冻结 policy/observer，启动心跳；打开 PublicationWorkspace |
| 复算 | backend/app/services/recalculation.py run_recalculation | recalculate 分支不构造 provider；检查交易日、已有 Raw 完整性，预热250交易日，先 TradeStatus，再按月 Factor |
| Raw 检查 | 同文件 validate_recalculation_raw_prerequisites | 默认 check_raw_completeness(persist=False)，缺失时报 DataQualityError，不自动重新拉取或补数据 |
| 读取 | backend/app/services/factors/service.py FactorService.recalc 及五个 _read_* | 430日历日读取窗口；已有 daily/adj/basic/当前身份 trade_status/index，无外部 provider |
| 读保护 | backend/app/repositories/calculation_frame.py read_calculation_frame | yield_per/partitions 5000，有 checkpoint，finally 关闭 Result/observer；不把读取阶段与 CPU/写入混为一谈 |
| CPU | backend/app/services/factors/engine.py calculate_stock_factors | 五个现成 callback 点；默认路径原来不传 callback，本次修复这一调用参数 |
| 候选 | backend/app/repositories/replace_slice.py replace_slice_rows；backend/app/services/data_publication.py PublicationWorkspace | 记录 scope、已有键与当前键比对、删除 stale/upsert；workspace 把注册派生模型写入候选；FactorService commit 是阶段提交，不是最终公开发布 |
| 批次查询 | data_publication.py _lookup_batch、upsert | 每500行批次一次 lookup execute，SQL 内两个 LATERAL probe 检查 candidate/public；两个统计标签不等于两个 SQL。旧“反复查询”线索未证明热点，不改 |
| 下游 | recalculation.py run_recalculation | Market/Sector、Theme、Trend、Opportunity、跨表质量检查，再请求 Job SUCCESS |
| 原子发布 | backend/app/repositories/job_run.py _update_owned_data_job；data_publication.py finish_publication | SUCCESS 前 checkpoint；同终态 CAS 事务内发布，校验计数/质量/source/身份及 owner/token/cancel；RUNNING+owner+token 且未取消才成功，外层 commit |
| 查询 | backend/app/api/v1/stocks.py factors 对应 /stocks/{ts_code}/factors | 读公开 StockFactorDaily，当前 FACTOR_CALC_VERSION 与 strategy hash、日期过滤，不读候选 |

以上函数名以本基线源码为准；文件精确路径另见本报告末尾校核记录。
PublicationWorkspace.open 创建 PREPARING ledger、临时 overlay 和候选视图；close 清理临时资源。
finish_publication 本身不 commit；非 SUCCESS 路径将 ledger ABORTED。
原有 public swap、preimage、source 校验和发布预算均未修改。

Worker 的 JobCancelled、JobOwnershipLost、JobExecutionUnconfirmed 是 BaseException；
不会被 run_recalculation 的普通 except Exception 吞掉。取消由 Worker rollback 后
_finish_data_cancellation 收束子任务/root、重开 dirty ranges；归属丢失 rollback；
不确定执行由 _hold_unconfirmed_execution 保留 RUNNING 并标记 execution_unconfirmed，
不伪造成功或自动释放写入者。finally 停止/等待心跳、关闭 workspace/observer/policy、
重置执行上下文。默认事务 statement_timeout=300000ms、lock_timeout=5000ms；
checkpoint 使用独立短 Session 观察状态/owner/token/cancel。未连接数据库验证这些路径。

## 受控 RED → GREEN

固定 fixture：既有 test_factor_engine 的3股票×270日，daily 810行，目标末日3行；
所有优化关闭，Raw 读取返回副本，写入与 commit 仅计数。
基线 RED 的 service 来自固定 SHA 的 git show，不从临时改坏的生产代码读取。

| 断言组 | 原基线 RED | 当前 GREEN |
|---|---|---|
| 五个既有检查点分别取消 | 5个应抛未抛；各假写入1、假commit1 | 5个抛出同一 JobCancelled；写0、commit0 |
| 归属丢失、执行未确认传播 | 2个应抛未抛；各假写入1、假commit1 | 2个原异常传播；写0、commit0 |
| 最后 Raw 读取后取消/token变化，真实 checkpoint + 假观察 Session | 2个应抛未抛；各假写入1、假commit1 | 2个各观察1次即停止；写0、commit0 |
| 正常值、身份、scope、输入不变 | callback 次数0，预期5而失败 | callback5；3行；假写入1、commit1；全部因子值精确相等 |

RED 的“写入”只是被替换函数的计数，不是 PG 写入，也不证明真实取消能绕过发布。
实际候选与终态发布已有外围 fail-closed 检查，本次只提前停止 CPU 工作。
所有10项定向源码隔离用例 GREEN；另执行15项既有因子断言：
核心列、eligible全市场RPS、突破前高、历史ST、6组drawdown边界、
2组上市/nullable边界、2组全字段dtype/rank金标、取消不返回部分结果，全部通过。
保留既有 pandas pct_change FutureWarning，没有改算法、容差或测试断言。

此结果是 AST/source-only 诊断，不是原生 pytest 通过。
诊断抽取真实 FactorService/engine/checkpoint/metadata/identity 及测试函数 AST，
真实 numpy/pandas/SQLAlchemy 表达式运行；替换 logger、run_calculation 外壳、
模型列、Raw读、持久化和 Session。没有验证完整模块导入、ProgressStep、真实事务、
候选幂等/失败清理/原子发布、PG17或 Worker。Decimal/source 语义未修改，
其真实端到端等价性尚待验收。诊断装配曾漏绑定 service.checkpoint 到实际抽取函数，
修正诊断绑定后复验；没有为通过而改生产逻辑或断言。

## 离线验证与环境限制

- 普通针对性 pytest：factor_engine、recalculation_quality_gate 两文件收集失败，
  缺 loguru；扩大至新文件、factor_engine、business_factor_cpu、
  recalculation_quality_gate、job_worker 五文件仍是5个收集错误，前四缺 loguru，
  job_worker 缺 fastapi。没有实际执行单测，ENV_BLOCKED_MISSING_LOGURU_FASTAPI。
- 使用进程内安全启动：禁读 .env、禁网络、Engine.connect 拒绝所有连接，
  内存设置测试配置/关闭优化，禁 pytest cache；未启动服务或写业务数据。
- Ruff 定向检查失败：No module named ruff，ENV_BLOCKED_NO_RUFF。
- 未安装依赖；现有其他 Python 环境不满足3.12+/依赖条件，没有迁移环境或借机安装。
- 生产及新测试 AST 解析通过；git diff --check 通过。白名单与保全校核见下。
- 未执行真实 PG17/Worker、全量 pytest、Linux 新 SHA CI、真实性能试验；
  旧基线 CI 绿色不构成本次未提交改动验收。

复现源码隔离诊断：在仓库根、已有依赖环境，将下方脚本经
python -X utf8 -B - 运行。MODE=RED 会只读取固定基线 service；
MODE=GREEN 读取当前 service 并追加15项既有断言。禁止将该诊断替代原生测试。

## 独立审阅后的下一步与停止条件

先在具备既有完整依赖的 Python3.12+ 环境执行新增及上述受影响单测、Ruff，
由外层独立审阅再按授权提交和常规推送，逐一核查新 SHA 主CI、A4-1、A4-2、Publication。
本地没有新 SHA，也没有提出把旧 CI 当作本次通过。

随后优先取得一个用户实际失败 recalculate Job 的脱敏只读证据：
由操作者在既有已登录同源界面查看 /api/v1/jobs?job_type=recalculate&limit=20
和 /api/v1/jobs/queue，记录该 Job 的状态、阶段、失败阶段/错误码、
可用的心跳和进度字段、执行时间；字段以现有响应为准，不要求输出凭据、SQL参数或Raw。
本轮没有调用这些业务接口。根据证据区分连接、读取、CPU、候选、发布阶段，
下一次只修直接相关函数；若缺日志/连接部署证据则保持 UNKNOWN，不猜测调整。
不自动重拉 Raw、不自动重试/清理 RUNNING、不接触生产库。
实际可复算与性能验收需要另外批准的隔离 PG17、真实 Worker 和已冻结测量方案；
准入仍 NOT_APPROVED，不能现在执行。
如需超过代码白名单、迁移/DDL、冻结源码、依赖或workflow修改，应停止并交接。

## 保全记录

五冻结 Git blob（HEAD 与工作树一致）：

| 文件 | blob |
|---|---|
| scripts/business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| scripts/biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| scripts/perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| scripts/biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| scripts/business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

保留文件 SHA256：
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750
- 本任务书：e5689d2a71dee35e1e5102391b8e902b26d12bd3a40457d52cdc110b27fc7e3e

CODE_PATHS：
- backend/app/services/factors/service.py：仅默认路径回调传参，1个生产文件。
- tests/unit/test_factor_service_cancellation.py：1个新单测文件，10个参数展开用例。
- 本报告为唯一新增 closeout；治理/安全插件/冻结源码/历史代码/CI/依赖不改。

最终校核：1637个已跟踪文件的原始字节 SHA256 映射，仅将唯一修改的 service
替换回 HEAD 原字节后，排序 JSON 的 SHA256 仍为任务开始记录
a2ab225fbc66cc8c2673999dcb1893f12e8757d4eeac26da45090e73a52bd1a7。
因此其余1636个已跟踪文件原字节未变；暂存区为空。

## 源码隔离复现脚本

```python
MODE = "GREEN"
import ast
import copy
import hashlib
import json
import sys
import subprocess
import types
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import column, select

def load_nodes(path, ns, names=None, assignments=False):
    source = (subprocess.check_output(["git", "show",
                "883c369c7700b16557b9833f5042b071be886f01:" + path]).decode("utf-8")
              if MODE == "RED" and path == "backend/app/services/factors/service.py"
              else Path(path).read_text(encoding="utf-8"))
    tree = ast.parse(source)
    nodes = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and (names is None or n.name in names):
            n = copy.deepcopy(n)
            n.decorator_list = [d for d in n.decorator_list
                                if isinstance(n, ast.ClassDef)]  # Keep dataclass; strip pytest.
            nodes.append(n)
        elif assignments and isinstance(n, ast.Assign):
            if names is None or any(isinstance(t, ast.Name) and t.id in names for t in n.targets):
                nodes.append(n)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), ns)

engine = types.ModuleType("source_only_factor_engine")
sys.modules[engine.__name__] = engine
engine.__dict__.update(np=np, pd=pd, Callable=Callable, Any=Any, dataclass=dataclass, date=date)
load_nodes("backend/app/services/universe.py", engine.__dict__, {"is_stock_active_on"})
load_nodes("backend/app/services/factors/engine.py", engine.__dict__)

policy = types.ModuleType("app.services.calculation_policy")
policy.__dict__.update(ContextVar=ContextVar)
load_nodes("backend/app/services/calculation_policy.py", policy.__dict__,
           {"FLAGS", "effective_flag"}, assignments=True)
policy.active_policy = ContextVar("source_only_policy", default=None)

service = types.ModuleType("source_only_factor_service")
service.__dict__.update(pd=pd, uuid=uuid, date=date, timedelta=timedelta, Any=Any, Session=object,
                        hashlib=hashlib, json=json, datetime=datetime, UTC=UTC,
                        FactorConfig=engine.FactorConfig,
                        calculate_stock_factors=engine.calculate_stock_factors,
                        StockFactorDaily=SimpleNamespace(trade_date=column("trade_date")),
                        logger=SimpleNamespace(info=lambda *a, **k: None),
                        get_settings=lambda: None, checkpoint=lambda: None,
                        replace_slice_rows=lambda *a, **k: None,
                        run_calculation=lambda name, calculate, *a, **k: calculate(*a, **k))
load_nodes("backend/app/services/calc_metadata.py", service.__dict__)
load_nodes("backend/app/services/analysis_identity.py", service.__dict__,
           {"FACTOR_CALC_VERSION", "ANALYSIS_STRATEGY_KEYS",
            "analysis_strategy_config", "analysis_strategy_hash"}, assignments=True)
load_nodes("backend/app/services/factors/service.py", service.__dict__, {"FactorService", "_clean_row"})

execution_module = types.ModuleType("source_only_job_execution")
sys.modules[execution_module.__name__] = execution_module
execution = execution_module.__dict__
execution.update(ContextVar=ContextVar, UUID=uuid.UUID, dataclass=dataclass, select=select,
                 Session=object, current_execution=ContextVar("source_only_execution", default=None),
                 JobRun=SimpleNamespace(**{n: column(n) for n in
                     ("id", "status", "worker_id", "execution_token", "cancel_requested")}))
load_nodes("backend/app/services/job_execution.py", execution,
           {"Execution", "checkpoint", "JobCancelled", "JobOwnershipLost",
            "JobExecutionUnconfirmed"})
service.checkpoint = execution_module.checkpoint
ns = dict(SimpleNamespace=SimpleNamespace, uuid4=uuid.uuid4, pd=pd, pytest=pytest,
          calculation_policy=policy, factor_service=service, job_execution=execution_module,
          JobCancelled=execution["JobCancelled"],
          JobOwnershipLost=execution["JobOwnershipLost"],
          JobExecutionUnconfirmed=execution["JobExecutionUnconfirmed"])
ns["date"] = date
load_nodes("tests/unit/test_factor_engine.py", ns, {"_fixture_data", "_trade_status"})
load_nodes("tests/unit/test_factor_service_cancellation.py", ns)

def no_external(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen",
                 "os.system", "os.mkdir", "os.remove", "os.rename"}:
        raise AssertionError("SOURCE_ONLY_EXTERNAL_OPERATION_FORBIDDEN")
sys.addaudithook(no_external)

app = types.ModuleType("app")
services = types.ModuleType("app.services")
cases = [
    ("cancel_" + str(i), "test_default_factor_compute_cancels_before_any_candidate_write", i)
    for i in range(1, 6)
] + [
    ("stop_" + t.__name__, "test_default_factor_compute_preserves_execution_stop", t)
    for t in (ns["JobOwnershipLost"], ns["JobExecutionUnconfirmed"])
] + [
    ("real_checkpoint_" + str(lost), "test_default_factor_compute_observes_execution_after_raw_reads", lost)
    for lost in (False, True)
] + [("factor_identity_parity", "test_default_factor_compute_keeps_exact_factors_identity_and_scope", None)]
outcomes = []
with patch.dict(sys.modules, {"app": app, "app.services": services,
                             "app.services.calculation_policy": policy,
                             "app.services.job_execution": execution_module}):
    for label, name, arg in cases:
        with pytest.MonkeyPatch.context() as mp:
            fixture = ns["unoptimized_service"](mp)
            state = next(fixture)
            try:
                args = (mp, state) if arg is None else (mp, state, arg)
                ns[name](*args)
            except BaseException as error:
                assert MODE == "RED", (label, type(error).__name__)
                assert len(state[2]) == 1 and state[0].db.commits == 1
                if arg is None:
                    assert isinstance(error, AssertionError)
                else:
                    assert type(error).__name__ == "Failed" and "DID NOT RAISE" in str(error)
                outcomes.append("EXPECTED_RED")
                print(label, "EXPECTED_RED: cancellation/stop omitted; write=1 commit=1")
            else:
                assert MODE == "GREEN"
                outcomes.append("PASS")
                print(label, "PASS", "writes=" + str(len(state[2])),
                      "commits=" + str(state[0].db.commits))
            finally:
                fixture.close()
assert len(outcomes) == 10
print("SOURCE_ONLY_" + MODE, len(outcomes), "cases; actual service+engine AST; no DB/native module import")

if MODE == "GREEN":
    ns.update(np=np, replace=replace, assert_frame_equal=pd.testing.assert_frame_equal,
              assert_series_equal=pd.testing.assert_series_equal,
              FactorConfig=engine.FactorConfig, calculate_stock_factors=engine.calculate_stock_factors,
              _assign_eligibility=engine._assign_eligibility, _max_drawdown=engine._max_drawdown,
              _max_drawdown_array=engine._max_drawdown_array)
    load_nodes("tests/unit/test_factor_engine.py", ns)
    load_nodes("tests/unit/test_business_factor_cpu.py", ns)
    checks = [(n, ()) for n in (
        "test_calculate_stock_factors_core_columns", "test_rps_uses_only_eligible_universe",
        "test_breakout_uses_previous_high_not_today_high",
        "test_factor_eligibility_uses_point_in_time_st_status_not_current_name")]
    checks += [("test_numpy_drawdown_matches_original_including_zero_negative_nan", (v,))
               for v in ([], [0] * 60, [-1, -2, 0, 1, 2, -3] * 10,
                         [1, 2, 3, np.nan] * 15, [np.inf, 1, -np.inf] * 20,
                         list(np.random.default_rng(17).normal(size=60)))]
    for name in ("test_vectorized_listing_and_nullable_status_boundaries",
                 "test_factor_full_field_dtype_and_cross_market_rank_golden"):
        checks += [(name, (value,)) for value in (True, False)]
    checks += [("test_factor_compute_checkpoint_does_not_return_partial_result", ())]
    with patch.dict(sys.modules, {"app": app, "app.services": services,
                                 "app.services.job_execution": execution_module}):
        for name, args in checks:
            ns[name](*args)
    assert len(checks) == 15
    print("SOURCE_ONLY_EXISTING_FACTOR_REGRESSIONS=15 PASS; exact values/dtypes/PIT/ranks/cancel")
```
