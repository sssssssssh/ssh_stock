# BIZ-PERF-FACTOR-RECOVERY-03 closeout

日期：2026-11-16。
BASELINE_SHA=232baf9e13cd7b23731e59188c86e0e253c3a394。
ROOT_CAUSE=CONDITIONAL_HEARTBEAT_START_FAILURE_MASKED_BY_UNSTARTED_JOIN。
STATUS=OFFLINE_REPRODUCED / PATCH_STOPPED_BY_PINNED_SOURCE_CONTRACT / REVIEW_PENDING。
CHANGED_FILES=docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_CLOSEOUT.md。
REAL_FACTOR_RUN=NOT_RUN；DB_HOTSPOT=UNPROVEN；NEXT=CHATGPT_REVIEW。

## 基线、范围与先决条件

开始master，HEAD、origin/master、已认证GitHub master一致为上述SHA。
仅本任务书及W05任务书/审计三个未跟踪文件，未发现其它工作树改动。
沿用本持久会话已读的五治理文件和相关业务权威文档；本轮逐文件核验五治理相对
此前已读c690b50版本字节未变，核对任务书与01、02、CI修复及R2的实际交付，
不重复应用01修复或已经撤回的02单SQL优化。

只读查询四个指定基线run的实际job结果：
主CI43771443208、A4-2 43771443183、A4-1 43771443164、
Publication43771443115的必需检查及汇总均success；
authorize/正式性能/容量等相关job仍skipped。
没有rerun/dispatch，CI只证明该精确基线工程检查，不证明业务现场成功。

并发检查的限制：Get-CimInstance Win32_Process拒绝访问；
Get-Process只能看到Codex桌面/CLI/host/runner进程名和PID，不能辨认其任务命令行。
所以“没有另一个同任务CLI”不能确认，标记UNKNOWN；不终止任何进程，不尝试越权查询。
本轮仅只读分析、纯模拟和新增独立报告，没有改现有业务/测试文件。

## 实际调用链

| 环节 | 精确源码与入口 | 关键行为 |
|---|---|---|
| 发起 | frontend/src/App.vue submitRecalculation；services/api.ts enqueueRecalculateJob；backend/app/api/v1/jobs.py enqueue_recalculate_job | POST /api/v1/jobs/recalculate，已有Raw范围校验后入队 |
| 队列 | services/job_guard.py create_queued_ingestion_job | advisory事务锁、fingerprint/队列/依赖检查，QUEUED并commit |
| 领取 | services/job_worker.py claim_next_job（124–206） | advisory锁、根RUNNING排他、FIFO队首；数据队首行锁不SKIP LOCKED；重新SELECT populate_existing，校验依赖/身份，owner/token，RUNNING后commit |
| 调度 | 同文件 _run_worker_loop（659–776） | 独立claim Session，取data_claim owner/token，另一个Session执行；没有自动重放未知Writer |
| 执行 | execute_claimed_job（210–505） | RUNNING与owner/token检查；Execution/Progress上下文；policy/observer；心跳线程；交易日保护；PublicationWorkspace.open |
| 已有Raw复算 | services/recalculation.py run_recalculation；factors/service.py FactorService.recalc | recalculate分支不构造provider；Raw预检和预热后月分块，五类已有输入、CPU引擎、metadata、候选写入 |
| 核对/去重 | repositories/replace_slice.py replace_slice_rows；repositories/upsert.py upsert_rows | scope登记、范围existing_keys、stale键差集/墓碑、route_upsert |
| 候选 | services/data_publication.py PublicationWorkspace.upsert / _lookup_batch / _store_batch | 每500行一次lookup，SQL内candidate/public两个LATERAL；每批一次store前checkpoint；不是两个进度标签两条lookup |
| 发布 | repositories/job_run.py _update_owned_data_job；data_publication.finish_publication | source/质量/身份验证，owner/token/未取消CAS，同终态事务发布；阶段候选commit不等于公开 |
| 查询 | api/v1/stocks.py factors | 查询公开StockFactorDaily，当前版本/config hash与日期过滤，不公开候选 |

取消/归属失权分别被Worker捕获并rollback；取消收束dirty ranges及子任务；
执行不确定保留RUNNING，不放行未知Writer。主计算与心跳Session分离；
heartbeat lease/progress有短事务限时和owner/token CAS。
finally停止心跳、join、关闭workspace/observer/policy并重置上下文。
本次重点反例位于这条清理链的join，不在因子公式或候选SQL。

领取/取消竞态静态审阅：claim的第二次SELECT仍带QUEUED条件与行锁，
populate_existing刷新；没有足够证据认定取消后仍能领取或双Writer。
不能只凭两次SELECT就删除锁后复核；本轮不做真实并发/锁证明。

## 可复现缺陷：心跳启动失败导致清理异常退出轮询

触发前提：RUNNING recalculate的owner/token匹配，
threading.Thread对象已经构造，但start()因资源限制等抛RuntimeError。
真实机器是否发生该事件UNKNOWN，没有读取现场日志。

精确因果：
1. execute_claimed_job第267–278行构造heartbeat_thread并start。
2. 启动异常进入普通except，rollback，正常可用的故障记录分支可把Job记为FAILED。
3. 第461–466行finally只检查heartbeat_thread非None，调用join(timeout=5)。
4. Python真实Thread.join在未start时抛
   RuntimeError("cannot join thread before it is started")，掩盖最初启动失败。
5. _run_worker_with_source（643–656）只捕获DBAPIError/PendingRollbackError，
   此RuntimeError继续外抛，服务心跳finally清理后本次Worker调用结束；
   无外部重启时后续队列不会继续轮询。是否有部署层自动重启UNKNOWN。

这不是“已证明当前RUNNING任务卡死”的结论：
模拟中的故障Job已FAILED，Execution/Progress上下文也已恢复；
证明的是条件性资源故障后Worker服务调用退出、后续队列可能停滞。
失败持久化本身不可用的情形、真实数据库事务和进程监督均未验证。
原有未知Writer安全策略不能因此改为自动FAILED/抢占。

## 纯离线RED证据

抽取当前源码的execute_claimed_job、_run_worker_with_source完整函数AST，
去掉observe_worker包装；没有import/运行真实Worker模块或启动Worker服务。
假Session/Job/更新函数只计数，假日志、policy/observer边界；
RefusedThread继承真实threading.Thread，覆盖start令其确定性拒绝，
join调用真实父类实现，因而实际观察到Python的未启动join异常。
外层轮询函数也仅调用注入的单次抛错回调，没有运行真实轮询。

输入：一个带owner/token的RUNNING recalculate、空metadata，零Raw行/候选行。
连续两次独立运行结果相同：

```text
RED 1 {'start': 1, 'join': 1, 'rollback': 1, 'failure_record': 1,
       'stop_set': 1, 'commit': 1} job=FAILED
escaped=RuntimeError_unstarted_join contexts_reset=True
TERMINAL_REDISPATCH_NOOP=True
OUTER_POLLING_ESCAPES_RUNTIME_ERROR=True
RED 2: 同上
```

commit为模拟的执行前事务边界调用，不是真实提交。
终态Job再次派发没有新增start/join/rollback/failure动作，未重算/重复失败记录。
无实际线程启动、数据库连接、SQL、Raw或生产进程操作。
诊断初版假Db遗漏执行前commit，使故障提前落在AttributeError；
补齐假边界后才得到以上目标RED，没有修改生产或降低断言。

GREEN=NOT_IMPLEMENTED。报告保留RED，没有制作假补丁或把mock改成成功当作修复。
现场根因=UNKNOWN；真实P0优先级仍需任务日志/部署证据确认。

## 为什么不直接修复

任务书第3项明确：生产源码一改就必然触发旧固定hash时，停止并提出兼容方案。
旧r1_business_compare_schema_v1.json直接钉住job_worker.py，
当前LF摘要与期望都是：
91069dd58733e442831977f58ee1c37616d1ef37a271d7845856421251d6e7da。
加入join保护就会改变摘要，重现02的合同阻断。
因此停止修改，不改旧schema/hash、R1测试、安全插件或workflow；
不通过在未冻结入口加通用RuntimeError重试来绕过原问题。
本次不新增性能框架或另一个泛用审计工具，复现脚本仅随本报告交付。

供独立审阅的具体兼容/修复方案：
1. 先明确批准这一文件/节点的合同版本处理；保留旧manifest/负例，
   不能给旧schema直接换新hash或把全部业务安全测试迁往历史。
   若选历史执行语境，逐节点审阅历史归属并复用既有独立checkout机制，
   当前Worker/取消/发布回归必须仍在当前源码验证。
   此步骤超出本任务两个业务/两个测试的实施范围，当前只提出不执行。
2. 获准后仅在execute_claimed_job的finally保护“未成功启动的心跳线程”join；
   不全局吞RuntimeError、不改变owner/token、不减少rollback，
   不自动释放未知Writer。优先用明确线程启动状态/ident判定保留正常join。
3. tests/unit/test_job_worker.py定向新增start失败、已启动正常join、
   故障记录失败/失权、上下文清理、无候选发布、后续轮询行为的fake用例；
   先完整原生离线RED，再GREEN。测试不可只断言日志或只复制实现。
4. 先从操作者提供的已有脱敏日志确认是否存在“can't start new thread”/
   “cannot join thread before it is started”、Job阶段/终态和Worker退出/重启事件。
   无该证据不得把此条件性缺陷当作用户历史挂起的根因。
   诊断只需相应短时间窗、错误类、阶段及Job匿名身份，不索取DSN/凭据/Raw。

## 候选写入计数与既有回归

本轮不恢复02单SQL优化，未发现可证明的逐行N+1。
固定边界fixture及S2键规模150股×23合成工作日共3450行：
当前每批lookup和store各一次，scope仍注册+UPDATE。

| 行数 | 批数 | lookup/store各 | source INSERT/UPDATE | reconcile | execute前后 |
|---|---:|---:|---|---:|---|
| 1 | 1 | 1 | 2/1 | 1 | 6→6 |
| 500 | 1 | 1 | 2/1 | 1 | 6→6 |
| 501 | 2 | 2 | 2/1 | 1 | 8→8 |
| 1001 | 3 | 3 | 2/1 | 1 | 10→10 |
| S2 | 7 | 7 | 2/1 | 1 | 18→18 |

这里只计对应假execute，不含真实observer/owner查询/flush/网络，不能据此证明DB热点。
复用既有closeout脚本，候选9项源码隔离断言、replace_slice既有6项通过；
五组重复写入输出摘要稳定，S2仍为
112c1736266f6515403a1c81bbb81be2ff18a6b390290c2e2fee5ba054b8051f。
因子取消源码隔离10项和既有算法15项通过，失败/归属9例假写0/commit0，
正常3行/5检查点。PIT/dtype/rank比较沿用既有严格断言。
这些是源码隔离回归，不是完整模块pytest或PG发布/Decimal端到端验收。
没有生产变更，性能前后计数相同、改善NOT_MEASURED。

原生安全pytest尝试四文件：test_job_worker、test_factor_candidate_write、
test_replace_slice、test_factor_service_cancellation；退出1，4个收集错误，
前者缺fastapi，后三者缺loguru，未执行用例。
使用前轮安全启动，禁.env与Engine.connect/网络，安全插件未改；未安装依赖。
Ruff尝试job_worker.py/test_job_worker.py：No module named ruff，ENV_BLOCKED。
git diff --check通过。原生完整Worker异常/并发回归仍待合格环境；
不能因工程CI绿色或模拟断言通过宣称真实因子复算/原子发布已可用。

## 保全与剩余验收

1646个已跟踪文件原字节SHA256映射的排序JSON摘要开始/结束均为：
702a421ae1366d401ccccd0df2c665ac0edb45f8978907cc66241b4650898a8e。
所有源码、旧测试/报告、策略、合同、安全插件、CI及依赖均未修改。
当前只有本closeout是本轮新增交付，无Git暂存/提交/推送。

保留资产SHA256：
- 本任务书：aae3179df7d44bd28ff6912d3f1f0132514c45b690b0c23123f7a3dd7d86343f
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750

五冻结blob核对一致：
- business_recalc_measure.py：782e45ba53c8de8df0d12ffa84c219855316cfda
- biz_perf_p1_04_diagnostic.py：714f78017ec252791ac6a89f9fb0e0a984333c37
- perf03_lnx_w04a_offline_contract.py：931fd4fec38551d9fac59791d2bde5ce0e6a1d48
- biz_perf_03_b_once.py：2ea473491f590893ad575b90a0ba42f932e37129
- business_sql_snapshot.py：e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6
a42331_pytest_safety.py仍为64fb3709d5bd74ca1a407c87c461a4c52acaff67。

B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0。
REAL_FACTOR_RUN=NOT_RUN；PG/Worker/SQL/迁移/数据重拉/云/正式性能试验均未运行。
下一步是上述现场短证据与窄范围源码合同裁决，再定向修复和业务验收；
不是继续扩展审计框架，也不自动进入性能或生产操作。等待ChatGPT独立审阅。

## 可重复RED脚本

仓库根使用python -X utf8 -B -运行，无应用/数据库依赖；
脚本仅执行抽取函数与固定假边界，真实Thread.start从未调用。

```python
import ast
import copy
import sys
import threading
import types
import uuid
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

def guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        if Path(args[0]).name == ".env":
            raise AssertionError("NO_ENV")
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                 "subprocess.Popen", "os.system"}:
        raise AssertionError("NO_EXTERNAL")
sys.addaudithook(guard)
source_path = "backend/app/services/job_worker.py"
tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
names = {"execute_claimed_job", "_run_worker_with_source"}
nodes = [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
for n in nodes:
    n.decorator_list = []
class Cancelled(BaseException): pass
class Lost(BaseException): pass
class Unconfirmed(BaseException): pass
class SqlError(Exception): pass
class PolicyChanged(Exception): pass
class SessionMarker: pass
stats = {}
class Event:
    def set(self): stats["stop_set"] += 1
class RefusedThread(threading.Thread):
    def start(self):
        stats["start"] += 1
        raise RuntimeError("SYNTHETIC_THREAD_START_REFUSED")
    def join(self, timeout=None):
        stats["join"] += 1
        return super().join(timeout=timeout)
class Db:
    info = None
    def __init__(self, job):
        self.job, self.info = job, {}
    def get(self, *args): return self.job
    def get_bind(self): return object()
    def rollback(self): stats["rollback"] += 1
    def commit(self): stats["commit"] += 1
def update_job(db, job, **kwargs):
    stats["failure_record"] += 1
    job.status = kwargs["status"]
def no_business(*args, **kwargs):
    raise AssertionError("BUSINESS_NOT_EXPECTED")
log = SimpleNamespace(**{k: lambda *a, **kw: None for k in ("warning", "error", "exception")})
context = ContextVar("offline_execution", default=None)
progress = ContextVar("offline_progress", default=None)
ns = dict(
    uuid=uuid, Session=SessionMarker, JobRun=object, current_execution=context,
    current_progress=progress, CalculationProgress=SimpleNamespace,
    Execution=lambda *args: SimpleNamespace(args=args),
    INGESTION_JOB_TYPES={"recalculate"}, PAPER_JOB_TYPES=set(),
    get_settings=lambda: SimpleNamespace(), logger=log,
    threading=SimpleNamespace(Thread=RefusedThread, Event=Event),
    JobCancelled=Cancelled, JobOwnershipLost=Lost, JobExecutionUnconfirmed=Unconfirmed,
    SQLAlchemyError=SqlError, DBAPIError=type("DbError",(SqlError,),{}),
    PendingRollbackError=type("PendingRollback",(SqlError,),{}),
    uncertain_database_error=lambda e: False, update_job=update_job,
    _run_heartbeat_loop=no_business,
)
for key in ("BACKTEST_JOB_TYPE", "PERFORMANCE_RISK_JOB_TYPE", "PERFORMANCE_TRADE_JOB_TYPE",
            "PERFORMANCE_PERIOD_JOB_TYPE", "EXPERIMENT_EVALUATION_JOB_TYPE",
            "WALK_FORWARD_VALIDATION_JOB_TYPE"):
    ns[key] = key
import __future__
exec(compile(ast.Module(body=nodes, type_ignores=[]), source_path, "exec",
             flags=__future__.annotations.compiler_flag), ns)
app = types.ModuleType("app"); app.__path__ = []
services = types.ModuleType("app.services"); services.__path__ = []
diag = types.ModuleType("app.services.performance_diagnostics")
diag.bind_task = lambda *a: None
policy = types.ModuleType("app.services.calculation_policy"); policy.PolicyChanged = PolicyChanged
with patch.dict(sys.modules, {"app":app,"app.services":services,
                             "app.services.performance_diagnostics":diag,
                             "app.services.calculation_policy":policy}):
    for attempt in (1, 2):
        stats.update(start=0, join=0, rollback=0, failure_record=0, stop_set=0, commit=0)
        identity, token = uuid.uuid4(), uuid.uuid4()
        job = SimpleNamespace(id=identity, status="RUNNING", job_type="recalculate",
                              worker_id="synthetic-worker", execution_token=token,
                              job_metadata={}, step=None)
        db = Db(job)
        try:
            ns["execute_claimed_job"](db, identity,
                expected_worker=job.worker_id, expected_token=token)
        except RuntimeError as e:
            assert str(e) == "cannot join thread before it is started"
        else:
            raise AssertionError("EXPECTED_UNSTARTED_JOIN_FAILURE")
        assert stats["start"] == stats["join"] == stats["rollback"] == stats["failure_record"] == 1
        assert job.status == "FAILED" and context.get() is None and progress.get() is None
        assert "data_task_timeouts" not in db.info
        print("RED", attempt, dict(stats), "job=FAILED",
              "escaped=RuntimeError_unstarted_join", "contexts_reset=True", flush=True)
        # Re-dispatching the now-terminal fake job has no new business/failure work.
        before = dict(stats)
        ns["execute_claimed_job"](db, identity,
            expected_worker=job.worker_id, expected_token=token)
        assert stats == before
        print("TERMINAL_REDISPATCH_NOOP=True", flush=True)
        # Outer service catches only DBAPI/PendingRollback; the join error stops polling.
        def run_loop():
            raise RuntimeError("cannot join thread before it is started")
        service_event = Event()
        service_thread = SimpleNamespace(join=lambda **kw: None)
        ns.update(_run_worker_loop=run_loop,
                  start_service_heartbeat=lambda *a: (service_event, service_thread))
        try: ns["_run_worker_with_source"]()
        except RuntimeError as e:
            assert str(e) == "cannot join thread before it is started"
        else: raise AssertionError("EXPECTED_POLLING_EXIT")
        print("OUTER_POLLING_ESCAPES_RUNTIME_ERROR=True", flush=True)
print("SOURCE_ONLY_REPRO_COMPLETE; no native thread start, DB, Worker loop or SQL executed")
```
