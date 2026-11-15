# BIZ-PERF-FACTOR-RECOVERY-02 closeout

日期：2026-11-16；交付状态：SCOPED_PATCH_IMPLEMENTED / REVIEW_PENDING。
TASK=BIZ-PERF-FACTOR-RECOVERY-02；NEXT=CHATGPT_REVIEW。

## 基线与授权

开始核对 master，HEAD=origin/master=已认证 GitHub master：
3277c81bc85382e939f58ba5d414fef3682b4de8。
GitHub connector fetch_commit(master) 返回该精确 SHA；只读请求，没有 dispatch/rerun。
任务开始仅有本任务书及前轮 W05-GATE-01 任务书、审计报告三个未跟踪文件，符合任务预期。
RECOVERY-01 代码和 closeout 已在该基线，不重复修改。
按 AGENTS.md 核对治理及相关业务权威边界；本轮最新任务授权候选写入离线定位，
不解除治理记录中的 PG17、Worker、真实性能实验和生产准入限制。
本轮仅修改一个生产 Python 文件、新增一个单测及本报告，不更新历史治理指针。

ROOT_CAUSE_STATUS=PROVEN_REDUNDANT_SCOPE_INVALIDATION_STATEMENT。
DB_HOTSPOT=UNPROVEN；FACTOR_RUN_STATUS=REAL_RECALC_NOT_RUN。
DB_STATUS=NOT_CONNECTED_UNTOUCHED；ROOT_ATTEMPTS=0。
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。
没有暂存、提交或推送，没有新 SHA，也没有本补丁的新 SHA CI。

## 真实调用链与事务范围

以下位置按3277c81源码；修改只发生在 record_scope，后续行号减少8行。

1. backend/app/services/job_worker.py execute_claimed_job：
   冻结 policy、设置执行上下文/超时、启动独立心跳；对 recalculate 校验交易日，
   PublicationWorkspace.open 后调用 run_recalculation。此分支不构造 provider。
   Worker 实际位于 services/job_worker.py，不能沿用历史报告中的 jobs/job_worker.py 路径。
2. backend/app/services/recalculation.py run_recalculation：既有 Raw 完整性检查、
   预热，按月循环 FactorService.recalc（第153行）。不重复拉 Raw。
3. backend/app/services/factors/service.py FactorService.recalc：
   五类已有 Raw/状态读取→calculate_stock_factors→metadata 与清洁行→第83行
   replace_slice_rows→第93行阶段 commit。CPU 与候选写入为两个阶段；
   本轮不更改公式、预热、输入或 RECOVERY-01 的取消回调。
4. backend/app/repositories/replace_slice.py replace_slice_rows：
   workspace.record_scope→范围 existing_keys SELECT→stale差集→必要的 delete_keys→
   repositories/upsert.py upsert_rows→data_publication.route_upsert→workspace.upsert。
   不在本轮测试或生产补丁中跳过范围核对。
5. backend/app/services/data_publication.py PublicationWorkspace.upsert：
   检查 conflict keys、register_source(source, invalidate=name in CORE)，
   每500行一次 _lookup_batch→准备候选→_store→_store_batch。
   StockFactorDaily 没有 serial id 分配分支；其它带 id 模型可能另有 nextval 查询。
6. _lookup_batch（225–277）：一次 execute，三个参数 keys/publication/table_name。
   keys JSON 只含自然键 trade_date/ts_code，不传全量因子字段。
   WITH input_keys 用 public.stock_factor_daily 原生复合类型读取输入；
   两个 LATERAL 分别探测本 publication 的 candidate 主键和 public 自然键，
   返回 typed current、首次 public preimage 与 transaction_now。
   候选主键等值包含上下界、ORDER BY/LIMIT 1，public OFFSET 0 均保留。
   lookup_candidate 与 lookup_published 两个进度标签没有各发一条 SQL。
7. _store_batch（401–418）：checkpoint 后单个 JSON rows bind，原生复合类型 INSERT
   public.data_publication_row；ON CONFLICT 仅更新 row_data/source_id/is_deleted/
   trade_date/entity_key，首次 base_row 不覆盖。每批500行，候选不等于公开结果。
8. 原子发布是下游质量通过后的另一个边界：
   repositories/job_run.py _update_owned_data_job 调 finish_publication，
   并在同一事务做 RUNNING/worker/token/未取消 CAS 与 commit。
   finish_publication 自己不 commit；source、质量、身份、owner、锁与发布预算保持。
   API 仍查询公开表，不能从候选已暂存推断根 SUCCESS/PUBLISHED。

workspace.open 固定连接、建立 PREPARING 与临时 overlay；中间 service commit 可保存
私有候选，但不能向普通 API 发布。取消/归属丢失由 Worker rollback 收束；
执行不确定保持 RUNNING、不释放未知 Writer；finally 关闭工作区/心跳与执行上下文。
本补丁没有改变这些事务边界、锁序、发布条件、失败处理或源码身份校验。

## 根因、精确补丁与收益界限

可证明的重复往返位于 record_scope，而不是每500行的 lookup：

旧实现：
- register_source(source)：检查 root/child 所有权，INSERT source ON CONFLICT DO NOTHING；
- 再 UPDATE 同一 publication/source，把 validated_at、validation 置空。

同一文件已有 register_source(source, invalidate=True)，被 upsert 路径长期使用：
INSERT source ON CONFLICT DO UPDATE SET validated_at=NULL, validation=NULL，
并 expire 已缓存的 source 验证字段。record_scope 可以直接复用它。
新 source 插入时这两个可空字段本就是 NULL；已有 source 冲突更新时显式失效。
role、source身份、scope日期/表名不变，所有权检查仍在发 SQL 之前。
原来 INSERT 冲突检查后也紧接 source UPDATE；合并没有去掉既有更新锁或增加 commit。
真实 PG17 并发/触发器行为未运行验证，不能把静态等价分析升级为数据库实证。

唯一生产 diff：

```diff
@@ PublicationWorkspace.record_scope
         source = self.db.info["calculation_job_id"]
-        self.register_source(source)
-        self.db.execute(
-            update(DataPublicationSource)
-            .where(
-                DataPublicationSource.publication_id == self.job_id,
-                DataPublicationSource.source_job_id == source,
-            )
-            .values(validated_at=None, validation=None)
-        )
+        self.register_source(source, invalidate=True)
```

收益是每次 record_scope 少一次 execute，不是每个500行批次少一次查询。
upsert 自身的 source invalidation 仍保留，以保护直接 upsert 调用者，
也不跨 scope/事务缓存查询结果。不认为两个 registration 都可无条件删除。
没有证明 N+1、没有修改 lookup SQL、没有声称30%收益或历史挂起已解决。

## 离线 RED → GREEN

新测试：tests/unit/test_factor_candidate_write.py，9个参数展开用例。
先添加测试，在未改生产源码时观察 RED，再做上述1行替换/9行删除。
最终复验 RED 仅从固定3277c81 git show 加载旧 publication 源码；GREEN 加载当前源码。
未通过回写旧代码、降低断言、跳过/重试或调大超时得到结果。

测试直接进入实际 replace_slice_rows→upsert_rows→route_upsert→PublicationWorkspace
scope/lookup/store 函数。SQLAlchemy 模型和 SQL 编译是真实的，边界 Session 只记录和
返回固定结果，不执行 SQL、不持有 Engine、不打开连接；CPU/Worker 没有运行。
源码隔离运行抽取 publication AST，去掉 observed 包装，替换 ProgressStep，
执行真实 repository 模块及新测试函数体。它不是完整应用模块导入或原生 pytest。

fixture：
- 1、500、501、1001行边界；
- S2 固定键规模沿用 business_synthetic_dataset 的150股票、2025年1月23个
  synthetic weekdays，共3450因子候选行、7批，固定数值、版本/hash/root/time。
  只复用 S2 请求月份键规模，没有生成原900日 Raw，也没有跑完整 S2 计算或真实性能实验。
- repeat同范围同payload两次，检查候选内容/身份、source失效与行数精确不变。

| 行数 | 批数 | lookup旧→新 | store旧→新 | source execute旧→新 | reconcile | 记录execute总数旧→新 |
|---|---:|---|---|---|---:|---|
| 1 | 1 | 1→1 | 1→1 | 3→2 | 1 | 6→5 |
| 500 | 1 | 1→1 | 1→1 | 3→2 | 1 | 6→5 |
| 501 | 2 | 2→2 | 2→2 | 3→2 | 1 | 8→7 |
| 1001 | 3 | 3→3 | 3→3 | 3→2 | 1 | 10→9 |
| S2 / 3450 | 7 | 7→7 | 7→7 | 3→2 | 1 | 18→17 |

scope单独测试：旧 INSERT+UPDATE 两次，新一次 INSERT ON CONFLICT UPDATE。
6个计数用例基线 EXPECTED_RED，3个失败/归属/取消用例原来与现在均通过；当前9项均PASS。
计数严格限定这里拦截的 execute，不是整个 root SQL 数：
不含 owner db.get 的潜在 SELECT（2次调用不变）、scope ORM add 最终 flush、
独立 checkpoint/心跳/进度观察与事务控制。正式总数不能直接减到本表数字。

参数规模（前后不变）：
lookup SQL 编译6499 UTF-8字节、3个绑定名；
每批至多500键，key JSON单批最大27000字节；
store每批1个 rows JSON绑定，500行最大730500字节。
S2 keys合计186300字节，store rows合计5040450字节。
以上是本合成payload规模，不是驱动网络包、PG执行计划或实际业务分布。

候选规范化 JSON SHA256（RED=GREEN，且每侧重复两次相等）：

| 行数 | SHA256 |
|---|---|
| 1 | ce85260cd96b836a8275ce93ab584d78ade8ef5550a1d51dd43ab8401dda4ed6 |
| 500 | f56780bca9a4ed9d0ce72d310fca4971525b2afab8ab51a3b5c14770f77c758f |
| 501 | 86944b5ac9c9369fb1a3e265d53d9efd5383507331749258ec1e6aaeefa6d77b |
| 1001 | cf90a0414fb171f6b23ba344036db82d9337f970f071c7a8768f2b39cceba274 |
| S2 | 112c1736266f6515403a1c81bbb81be2ff18a6b390290c2e2fee5ba054b8051f |

这些摘要证明本模拟新候选路径的全部序列化输出和身份相等；
不证明数据库已有 public/tombstone/preimage、并发幂等或原子发布已经验收。

参考耗时：同一进程内两次完整 replace调用+模拟编译/存储/摘要，
最终一次有界诊断的旧/新秒数：
1行0.003362/0.002411；500行0.126504/0.085732；
501行0.085374/0.083018；1001行0.170347/0.168234；
S2为0.578894/0.633223，S2模拟时间反而增加。
这是单次 Python/mock 观测，含编译与JSON、进程/缓存噪声，没有DB往返，
不能用于收益估计或选择性宣称提速。不执行多轮正式性能测量。
初始逐用例 RED 因计数断言提前退出、GREEN还做重复检查，两者用例耗时不可直接比较。

## 验证结果与未满足项

- 定向源码隔离：9项GREEN；5组输出前后/重复一致。
- 既有 tests/unit/test_replace_slice.py 的6项源码断言在两侧均PASS：
  signal surviving id、forward FK/cascade、3组stale删除、state algo scope。
  真实模型/SQL编译，假Session，不是PG验收。
- 新测试还校验 cached source 两验证字段expire、所有权失败在SQL前停止、
  source写入失败不记录scope、store前取消传播同一异常且无候选store。
- 原生 pytest（安全进程内启动，新测试、replace_slice、factor_service_cancellation）：
  退出1，3个收集错误，缺loguru，未执行任何测试。
  Settings禁读.env，数据库URL仅子进程内存测试值，Engine.connect被拒绝，禁网络，
  原有安全pytest插件保留，没有安装依赖或绕过插件。
- Ruff：退出1，No module named ruff；ENV_BLOCKED_NO_RUFF。
- 新测试及修改模块AST解析通过，新代码行长检查通过；git diff --check通过。
- 全量 pytest、完整Ruff、原生模块回归：ENV_BLOCKED；没有以AST结果冒充。
- tests/integration/test_publication_lookup_v13.py 的真实typed lookup/NULL、
  public preimage、tombstone/rebuild，以及 test_publication_cancel_v13.py 的锁/取消、
  原子发布等验收 NOT_RUN，当前用户禁止数据库与Worker。
- PIT/公式/Decimal/source hash/generation身份计算不改；静态检查相应代码原字节未变。
  完整金融结果和发布等价仍待新SHA Linux/隔离PG验收，不能凭mock宣称正常因子任务已恢复。

## 保全与最终范围

唯一修改生产文件：backend/app/services/data_publication.py。
唯一新增测试：tests/unit/test_factor_candidate_write.py。
唯一新增closeout：本报告。本任务书不改；前轮W05两文件不改。
无迁移/DDL、索引、依赖、配置、workflow、安全插件、冻结源码修改。

开始1640个已跟踪文件原字节 SHA256 映射的排序JSON摘要：
965229326b32f44d8cf6b0bf4c5de8e28b04eba835e2d530b2b587c83a4ccbd1。
最终把唯一修改的 publication 文件还原为 HEAD 原字节后，仅在内存计算映射，
摘要相同，证明其余1639个已跟踪文件原字节未变。

| 五冻结文件 | HEAD=工作树Git blob |
|---|---|
| scripts/business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| scripts/biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| scripts/perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| scripts/biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| scripts/business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

未跟踪保留资产原字节SHA256：
- 本任务书：ad56039bb7834f9c9b5bdd5b94352bb9d28c5e35c1ce4d5e8e1aee8f8bbf887a
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750

## 独立审阅与下一步

到此停止实施，等待ChatGPT独立审阅。
先在既有完整依赖环境执行新增9项及相关单元回归、Ruff；
获外层授权后才提交/非force推送，核查新SHA主CI、A4-1、A4-2、Publication。
当前基线CI成功不能验收未提交补丁。

DB_HOTSPOT仍UNPROVEN。下一业务证据应来自同一实际失败/慢Job的已脱敏、
只读阶段/批次与现有诊断摘要，区分 scope reconcile、每批lookup、prepare、store、
独立观察和最终publish；不要因两个进度标签推断两次lookup，
不要仅凭历史144万行/ClientRead猜测数据库瓶颈。
若确需计划/锁等待/资源实测，须先另批隔离PG17与真实Worker接线及精确协议，
保持原S2/正式规模和原门槛；本轮不能连接业务库或执行EXPLAIN。
不扩W05工具、不自动重拉Raw、不自动重试或清理RUNNING，
无可信证据时停止进一步优化；不能把这一条往返减少当作整体性能问题解决。

## 源码隔离复现

仓库根已有Python3.12+、SQLAlchemy、pytest环境，以 python -X utf8 -B - 运行下方脚本。
MODE=RED读取固定SHA，MODE=GREEN读取工作树。模型是原生导入；
progress/observed外壳是明确的诊断替身，不能替代原生pytest。
只读取源码及Git对象，编译SQL字符串，不向数据库执行任何SQL。

```python
MODE = "GREEN"
import ast
import copy
import json
import os
import sys
import types
from pathlib import Path
from datetime import date
from time import perf_counter
from unittest.mock import patch

from sqlalchemy.engine import Engine
import subprocess
baseline_source = (subprocess.check_output(["git", "show",
    "3277c81bc85382e939f58ba5d414fef3682b4de8:backend/app/services/data_publication.py"]).decode()
    if MODE == "RED" else None)

def guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        if Path(os.fsdecode(args[0])).name == ".env":
            raise AssertionError("OFFLINE_ENV_READ_FORBIDDEN")
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise AssertionError("OFFLINE_EXTERNAL_FORBIDDEN")
sys.addaudithook(guard)
sys.path.insert(0, str(Path("backend").resolve()))
def no_connection(*args, **kwargs):
    raise AssertionError("OFFLINE_CONNECTION_FORBIDDEN")
Engine.connect = no_connection

# Models and SQLAlchemy imports are native. Only observation/logging wrappers are replaced.
class ProgressStep:
    def __init__(self, *args, **kwargs):
        self.batch_count = kwargs.get("batch_count")
    def report(self, *args, **kwargs):
        pass
progress = types.ModuleType("app.services.calculation_progress")
progress.ProgressStep = ProgressStep
publication = types.ModuleType("app.services.data_publication")
source = baseline_source or Path("backend/app/services/data_publication.py").read_text(encoding="utf-8")
tree = ast.parse(source)
nodes = []
for node in tree.body:
    if isinstance(node, ast.ImportFrom) and node.module.startswith("app.services."):
        continue
    node = copy.deepcopy(node)
    if isinstance(node, ast.FunctionDef):
        node.decorator_list = [d for d in node.decorator_list if isinstance(d, ast.Name) and d.id == "lru_cache"]
    if isinstance(node, ast.ClassDef):
        for method in node.body:
            if isinstance(method, ast.FunctionDef):
                method.decorator_list = []
    nodes.append(node)
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.job import JobRun
execution = dict(ContextVar=ContextVar, dataclass=dataclass, UUID=UUID, Session=Session,
                 select=select, JobRun=JobRun)
execution_tree = ast.parse(Path("backend/app/services/job_execution.py").read_text())
selected = [n for n in execution_tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
            and n.name in {"JobCancelled", "JobOwnershipLost", "JobExecutionUnconfirmed"}]
exec(compile(ast.Module(body=selected, type_ignores=[]), "job_execution.py", "exec"), execution)
publication.__dict__.update(ProgressStep=ProgressStep, checkpoint=lambda: None,
                            JobOwnershipLost=execution["JobOwnershipLost"],
                            JobCancelled=execution["JobCancelled"])
with patch.dict(sys.modules, {"app.services.data_publication": publication,
                             "app.services.calculation_progress": progress}):
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "data_publication.py", "exec"),
         publication.__dict__)
    from app.repositories.replace_slice import replace_slice_rows
    test_path = "tests/unit/test_factor_candidate_write.py"
    test_tree = ast.parse(Path(test_path).read_text())
    test_nodes = []
    for node in test_tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "app.services":
            continue
        node = copy.deepcopy(node)
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
        test_nodes.append(node)
    ns = dict(publication=publication)
    exec(compile(ast.Module(body=test_nodes, type_ignores=[]), test_path, "exec"), ns)
    instances = []
    original = ns["RecordingSession"].__init__
    def track(self, **kwargs):
        original(self, **kwargs)
        instances.append(self)
    ns["RecordingSession"].__init__ = track
    cases = [("test_factor_scope_invalidates_source_in_one_statement", ())]
    cases += [("test_factor_candidate_path_bounds_queries_and_preserves_rows", (n,))
              for n in (1, 500, 501, 1001, "S2")]
    cases += [("test_scope_source_failure_does_not_record_scope", ()),
              ("test_scope_rejects_unowned_source_before_sql", ())]
    for name, args in cases:
        started = perf_counter()
        try:
            ns[name](*args)
        except AssertionError:
            assert MODE == "RED", (name, args)
            assert name.startswith("test_factor_"), name
            outcome = "EXPECTED_RED"
        else:
            outcome = "PASS"
        db = instances[-1]
        kinds = [kind for kind, _, _ in db.calls]
        lookups = [p for kind, _, p in db.calls if kind == "lookup"]
        stores = [p for kind, _, p in db.calls if kind == "store"]
        print(name, args, outcome, "counts=" + json.dumps({k:kinds.count(k) for k in sorted(set(kinds))}),
              "key_bytes=" + str(sum(len(p["keys"].encode()) for p in lookups)),
              "row_bytes=" + str(sum(len(p["rows"].encode()) for p in stores)),
              "seconds=" + format(perf_counter() - started, ".6f"))
    with ns["pytest"].MonkeyPatch.context() as mp:
        ns["test_candidate_stop_before_store_is_not_swallowed"](mp)
    print("cancel_before_store PASS")
    # Compare complete output twice even when RED's query-budget assertion stops early.
    import hashlib
    for size in (1, 500, 501, 1001, "S2"):
        db, _ = ns["candidate_session"]()
        rows = ns["factor_rows"](size)
        hashes = []
        paired_started = perf_counter()
        for attempt in range(2):
            db.calls.clear()
            assert replace_slice_rows(db, ns["StockFactorDaily"], rows,
                scope_filters=[ns["StockFactorDaily"].trade_date >= min(r["trade_date"] for r in rows),
                               ns["StockFactorDaily"].trade_date <= max(r["trade_date"] for r in rows)],
                key_columns=["trade_date", "ts_code"]) == len(rows)
            hashes.append(hashlib.sha256(json.dumps(list(db.candidates.values()),
                                                    sort_keys=True).encode()).hexdigest())
        assert hashes[0] == hashes[1]
        print("OUTPUT", size, hashes[0], "repeat_equal=True", "two_calls_seconds=" + format(perf_counter()-paired_started, ".6f"), "source=" + json.dumps(db.source),
              "lookup_sql_bytes=" + str(max(len(sql.encode()) for kind,sql,p in db.calls
                                           if kind == "lookup")),
              "max_key_bind_bytes=" + str(max(len(p["keys"].encode()) for kind,sql,p in db.calls
                                             if kind == "lookup")))
    reg_path = "tests/unit/test_replace_slice.py"
    reg_tree = ast.parse(Path(reg_path).read_text())
    for node in reg_tree.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
    reg_ns = {}
    exec(compile(reg_tree, reg_path, "exec"), reg_ns)
    reg_ns["test_signal_replace_slice_removes_stale_and_preserves_surviving_id"]()
    reg_ns["test_signal_forward_eval_uses_cascade_lifecycle"]()
    day = ns["DAY"]
    for model, existing, rows, filters, keys, stale in [
        (reg_ns["SectorFactorDaily"], [(day,1),(day,2)], [{"trade_date":day,"sector_id":1}],
         [reg_ns["SectorFactorDaily"].trade_date == day], ["trade_date","sector_id"], "2"),
        (reg_ns["StockFactorDaily"], [(day,"000001.SZ"),(day,"000002.SZ")],
         [{"trade_date":day,"ts_code":"000001.SZ"}], [reg_ns["StockFactorDaily"].trade_date == day],
         ["trade_date","ts_code"], "000002.SZ"),
        (reg_ns["MarketDaily"], [(date(2026,9,14),),(day,)], [{"trade_date":day}],
         [reg_ns["MarketDaily"].trade_date >= date(2026,9,14), reg_ns["MarketDaily"].trade_date <= day],
         ["trade_date"], "2026-09-14")]:
        reg_ns["test_replace_slice_removes_stale_derived_rows"](
            model, existing, rows, filters, keys, stale)
    reg_ns["test_state_replace_slice_only_deletes_current_algo_version"]()
    print("EXISTING_REPLACE_SLICE_SOURCE_ASSERTIONS=6 PASS")
    print("SOURCE_ONLY", MODE, "9 cases; 5 repeated-output comparisons; no DB/Worker/SQL execution")
```

原生pytest安全启动（本机实际因缺loguru收集失败；不安装新依赖）：

```python
import os, sys
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy.engine import Engine
def guard(event,args):
    if event == "open" and isinstance(args[0], (str,bytes)):
        if Path(os.fsdecode(args[0])).name == ".env":
            raise AssertionError("OFFLINE_ENV_FILE_FORBIDDEN")
    if event in {"socket.connect","socket.bind","socket.getaddrinfo","os.system","subprocess.Popen"}:
        raise AssertionError("OFFLINE_NETWORK_OR_SHELL_FORBIDDEN")
sys.addaudithook(guard)
with patch.dict(os.environ, {
    "DATABASE_URL":"sqlite+pysqlite:///:memory:","APP_ENV":"test","TUSHARE_TOKEN":"",
    "LLM_ENABLED":"false","PERF_DIAGNOSTICS_ENABLED":"false","WORKER_DIAGNOSTICS_ENABLED":"false",
    "AB_MERGE_READ_ENABLED":"false","FACTOR_INPUT_REUSE_ENABLED":"false",
    "RAW_PREFLIGHT_BATCH_ENABLED":"false","FACTOR_CPU_OPTIMIZATION_ENABLED":"false"}):
    sys.path.insert(0, str(Path("backend").resolve()))
    from app.core.config import Settings
    Settings.model_config = {**Settings.model_config, "env_file":None}
    def no_connection(*args,**kwargs):
        raise AssertionError("OFFLINE_DATABASE_CONNECTION_FORBIDDEN")
    with patch.object(Engine, "connect", no_connection):
        raise SystemExit(pytest.main(["tests/unit/test_factor_candidate_write.py",
            "tests/unit/test_replace_slice.py","tests/unit/test_factor_service_cancellation.py",
            "-q","-p","no:cacheprovider"]))
```
