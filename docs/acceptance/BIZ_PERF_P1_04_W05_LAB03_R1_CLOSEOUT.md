# W05-LAB-03-R1 定向测试时序整改回执

核查日期：2026-11-15（Asia/Shanghai）；本机核查时间 15:40 +08:00。
TASK=BIZ-PERF-P1-04-W05-LAB-03-R1；BASELINE_SHA=fc1cdc73cd6a2a4f10b55a6356953434ccf59bef。
状态：TEST_RACE_REPRODUCED / PATCH_IMPLEMENTED / REVIEW_PENDING / LINUX_CI_PENDING。
ROOT_CAUSE_STATUS=PROVEN 仅指旧测试自身的前导I/O竞争已受控证明；
CI实际失败参数、断言位置仍 UNKNOWN，不把合成复现写成本次CI现场还原。
最高状态 W05_LAB03_R1_CI_VALIDATED 尚未达到。

沿用用户指定的当前 Codex 桌面持久会话，未启动独立 codex exec。
期望归属 GP，projectId=01a15f75-2c79-7d30-9232-651a6ef4253d，
会话名 BIZ-PERF-P1-04 W05-LAB-03-R1 CI时序测试整改；
工具不能独立读取/修改桌面项目和会话名称，不能声称已独立核验这些元数据。

## 精确基线、来源和范围

首条命令为 `git status --short --branch`：master，唯一已有未跟踪文件为下发任务书。
HEAD、origin/master 均为完整基线 SHA；已认证 GitHub 只读
[master ref](https://github.com/sssssssssh/ssh_stock/tree/master) 返回同一 SHA。
没有拉取、切分支、reset、清理用户修改或更改 Git/SSH/代理设置。
只读进程清单未见名称含 docker/postgres/worker 的进程；没有探测服务、端口或数据库。

按 AGENTS 顺序完整读取五份治理文件，再核对相关 PRD、系统设计、PROJECT_RULES、
README；读取 LAB03 原任务/回执、本任务全文、完整目标测试与 supervisor、
A42331 安全插件、既有安全断言模式和 pytest 配置后修改。
治理文件仍有旧阶段指针；四文档维护通则与本轮三路径限制不一致，按用户最新明确范围执行。
本轮只修测试前提，不推进业务功能，不更新治理文件或四份业务文档。

仅三路径：

1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-03-R1.md`：下发原文不改；
   SHA256=44949bcc34420e05deb07f93ad7b460d25e7685cb5fcba431eaed250a45af25f。
2. `tests/unit/test_perf03_lnx_offline_supervisor.py`：只改目标测试，并紧邻增加一个时钟辅助类、
   两个三分支负例测试；其他测试原字节保留，CRLF 保持。
3. 本独立 closeout；无额外脚本文件、CI、依赖或生产代码修改。

## 已认证失败证据与不能推断的部分

[主CI 43684593024](https://github.com/sssssssssh/ssh_stock/actions/runs/43684593024)：
基线精确 SHA，push，attempt 1，completed/failure。
已认证 jobs/steps 和 test job 日志确认：
job 132722292238 / step 24 完整 pytest 失败；
`1 failed, 7647 passed, 1 skipped, 821 warnings in 2686.61s`。
step 28 test job Ruff skipped，不能报本次主测试链 Ruff 已通过；
另一 workflow-contracts job 的 Ruff success 不替代它。
路由/ci-opt-01-ci 失败为后续失败闭合，不另造独立根因。

下发任务书提供的已认证 safe artifact 摘要定位唯一条目
`tests.unit.test_perf03_lnx_offline_supervisor::test_rev1_synchronous_blocking_call_is_not_hard_preempted_3ea314badf5279b3`，
failure message/type=A42331_TEST_FAILURE、call/AssertionError、assertion_site=UNKNOWN。
本轮读取了该摘要及安全插件，没有重新下载/解密工件或反推参数哈希；
插件除精确白名单的旧 observer 用例外不提供断言位置，故无法确认 CI 参数和具体断言。
没有从无关数据库日志、SQL错误或其他CI归因。

本轮只读认证复核同SHA、push、attempt 1 的
[A4-1 43684593119](https://github.com/sssssssssh/ssh_stock/actions/runs/43684593119)、
[A4-2 43684593092](https://github.com/sssssssssh/ssh_stock/actions/runs/43684593092)、
[Publication 43684593046](https://github.com/sssssssssh/ssh_stock/actions/runs/43684593046)
均 completed/success。它们不是本次补丁的CI结果，没有 rerun/dispatch。

## 逐 point 因果与精确修改

原 supervisor 顺序：started=clock() → OwnedDirectory 构造 → prefix.json 写入（含fsync）
→ deadline=started+0.01 → 启动前 clock()<deadline → popen → while deadline检查 → 清理/归档。
不具备抢占同步调用的能力，生产逻辑保持原样。

| point | 原测试注入位置与正常超时 | 提前拒绝/断言冲突 |
| --- | --- | --- |
| popen | prelaunch检查通过才进入 slow_spawn；25ms返回后 while 报 MOCK_PHASE_TIMEOUT，按同一handle清理 | 构造/前缀IO耗尽10ms时，报MOCK_START_TIMEOUT且observed=[]；原测试却要求entered/returned，形成前提冲突 |
| prefix_io | prefix.json包装器先睡25ms，再执行原write；进入prelaunch时已超时，MOCK_START_TIMEOUT，无子进程 | 前导IO再慢也不跳过该write；原write/构造若自身抛错属于其他错误，不作为本次竞争证明 |
| fsync | prefix写入第一次fsync包装器先睡25ms，再执行原fsync；prelaunch报MOCK_START_TIMEOUT，无子进程 | 进入fsync之前无deadline检查；更早IO自身失败不属于本次证明；后续fsync不重复注入 |

新增 `_SynchronousBlockClock`：注入前返回0；block进入时以真实单调
`time.perf_counter()` 为锚，实睡0.025秒，记录独立阻塞时长；此后每次取时钟都读真实经过时间，
不在返回后重置，不冻结循环/清理计时。原 limits=(.01,.01,.01)、sleep(.025)、
parametrize三个point、elapsed>=.025、observed精确顺序、非COMPLETE和原first_failure集合均保留。
该测试验证同步调用不被抢占；前导预算语义仍由原 `test_prelaunch_deadline_starts_no_child` 覆盖，
未修改该测试或 supervisor 的真实预算逻辑。

统一 spawn 包装器仅对popen点注入；所有point启动前必须看到精确entered/returned，
否则抛有限固定错误 MOCK_BLOCKING_INJECTION_MISSING，避免未注入时冻结时钟进入轮询。
增加实际阻塞>=25ms、合成clock>=25ms、回执elapsed>=25ms、未接受phase、
仅popen分支回收过子进程、无owner pending/tickets/外发confirmation、
授权全false及原receipt校验。block断言只能进入一次。
慢准备负例在目录构造前真实等待25ms，并复用目标测试全部强断言；
缺失注入负例对三个point取消block，必须精确抛上述错误，不接受其他异常或静默成功。

## 受控 RED → GREEN 与验证

Windows 未执行整个 POSIX supervisor pytest 文件，未模拟平台支持或关闭平台校验。
下面诊断 AST 提取精确测试函数，执行真实标准库 supervisor/contract 算法，
只以内存目录替代 OwnedDirectory、无磁盘fsync、Child对象替代Popen；真实sleep保留。
没有真实mock child、POSIX dirfd IO、业务应用导入、DB、服务或网络操作。
所有现场验证和安全路径仍待 Linux；内存目录无法证明实际目录/链接/FD/进程安全。

| 验证 | 实际结果 |
| --- | --- |
| 首次修改前诊断：20ms内存目录构造延迟 | popen稳定触发旧断言失败、MOCK_START_TIMEOUT；prefix_io/fsync通过 |
| 精确基线/工作树受控对照：25ms内存构造延迟 | RED：popen断言失败且observed=[]，另两点通过；GREEN：目标3+慢准备3+缺失注入3，共9项通过 |
| 时钟纯单元诊断 | 4项通过：准备等待不计时、真实阻塞计时>=25ms、返回后仍前进、重复注入失败 |
| 源完整性 | AST可解析；原4个Assert AST和parametrize原样保留；白名单区外原字节不变；新增区域无>100字符行 |
| 17文件离线pytest | 985 passed in 24.94s，exit 0，无失败/跳过 |
| Ruff | python -B -m ruff check 目标文件：exit 1，No module named ruff；ENV_BLOCKED_NO_RUFF，未安装依赖 |
| git diff --check | exit 0；最终交接再核查 |
| Linux原POSIX测试、完整pytest/覆盖率/完整Ruff | NOT_RUN / 新SHA CI_PENDING；不能用内存GREEN或985项代替 |

离线pytest解释器退出时，既有pytest-current临时链接清理出现WinError5 PermissionError，
atexit忽略该异常，进程退出0；未改权限、删除临时链接或宣称清理成功。

离线命令（保留默认source_contract插件，禁用缓存写入）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_worker_gate.py tests/unit/test_biz_perf_p1_04_w05_root_bridge.py tests/unit/test_biz_perf_p1_04_w05_lab_plan.py tests/unit/test_biz_perf_p1_04_w05_readiness.py tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q -p no:cacheprovider
```

受控对照可复现代码：在仓库根目录用 `python -B -` 从stdin执行以下Python，
不生成额外测试/脚本文件。先只读git show固定基线，之后禁止真实子进程/网络；
Windows 3.12的time.monotonic分辨率可能较粗，提取测试的time引用在此诊断中显式使用
真实高精度单调perf_counter facade，原Linux测试源码的time.monotonic断言未改。

```python
import ast
import copy
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import perf03_lnx_offline_contract as c
from scripts import perf03_lnx_offline_supervisor as s

path = 'tests/unit/test_perf03_lnx_offline_supervisor.py'
old = subprocess.check_output(['git', 'show', 'fc1cdc73cd6a2a4f10b55a6356953434ccf59bef:' + path]).decode()
current = Path(path).read_text(encoding='utf-8')
target = 'test_rev1_synchronous_blocking_call_is_not_hard_preempted'
names = {target, '_SynchronousBlockClock',
         'test_rev1_blocking_injection_survives_slow_preparation',
         'test_rev1_missing_blocking_injection_is_rejected'}
# Windows Python 3.12 monotonic can be coarse; use a real, high-resolution
# monotonic perf_counter facade only in this extracted in-memory diagnostic.
wall = SimpleNamespace(monotonic=time.perf_counter,
                       perf_counter=time.perf_counter, sleep=time.sleep)

def extract(source):
    nodes = [copy.deepcopy(n) for n in ast.parse(source).body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    ns = dict(s=s, c=c, time=wall, subprocess=subprocess, pytest=pytest)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), ns)
    return ns

before, after = extract(old), extract(current)
# All remaining source must be unchanged, and all four original asserts retained.
left = "@pytest.mark.parametrize('point', ['popen', 'prefix_io', 'fsync'])"
right = "@pytest.mark.parametrize('entry', ['batch', 'cli', 'duplicate_final'])"
assert old.split(left)[0] == current.split('class _SynchronousBlockClock:')[0]
assert old.split(right)[1] == current.split(right)[1]
old_node = next(n for n in ast.parse(old).body if getattr(n, 'name', None) == target)
new_node = next(n for n in ast.parse(current).body if getattr(n, 'name', None) == target)
assert all(ast.dump(n) in [ast.dump(a) for a in new_node.body if isinstance(a, ast.Assert)]
           for n in old_node.body if isinstance(n, ast.Assert))
assert ast.dump(old_node.decorator_list[0]) == ast.dump(new_node.decorator_list[0])

def deny_external(event, args):
    if event in {'subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind'}:
        raise AssertionError('EXTERNAL_OPERATION_FORBIDDEN')
sys.addaudithook(deny_external)
original_supervise = s.supervise

for label, ns, tests in [
    ('RED_BASELINE', before, [target]),
    ('GREEN_WORKTREE', after, [target,
        'test_rev1_blocking_injection_survives_slow_preparation',
        'test_rev1_missing_blocking_injection_is_rejected']),
]:
    for test in tests:
        for point in ['popen', 'prefix_io', 'fsync']:
            results, children = [], []
            class MemoryDirectory:
                fd = 7
                def __init__(self, *_):
                    self.files = {}
                    time.sleep(.025)  # >10ms preamble, no filesystem operations.
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def check(self): pass
                def write(self, name, value):
                    s.os.fsync(self.fd)
                    self.files[name] = value
                def read(self, name): return self.files[name]
            class Child:
                returncode = None
                def poll(self): return self.returncode
                def kill(self): self.returncode = -9
                def wait(self, timeout):
                    assert timeout == .5
                    return self.returncode
            def spawn(*args, **kwargs):
                child = Child()
                children.append(child)
                return child
            def supervise(*args, **kwargs):
                r = original_supervise(*args, **kwargs)
                results.append(r)
                return r
            with patch.object(s, 'OwnedDirectory', MemoryDirectory), \
                 patch.object(s.os, 'fsync', lambda _: None), \
                 patch.object(s, 'supervise', supervise), \
                 patch.object(subprocess, 'Popen', spawn), \
                 pytest.MonkeyPatch.context() as mp:
                try:
                    ns[test](Path('.'), mp, point)
                except AssertionError as error:
                    assert label == 'RED_BASELINE' and point == 'popen'
                    frames = []
                    tb = error.__traceback__
                    while tb:
                        frames.append(tb.tb_frame)
                        tb = tb.tb_next
                    frame = next(f for f in frames if f.f_code.co_name == target)
                    assert frame.f_locals['observed'] == []
                    assert results[0]['first_failure'] == 'MOCK_START_TIMEOUT'
                    assert not children
                    print(label, point, 'EXPECTED_ASSERTION_FAILURE observed=[]')
                else:
                    assert not (label == 'RED_BASELINE' and point == 'popen')
                    missing = test == 'test_rev1_missing_blocking_injection_is_rejected'
                    assert len(children) == (1 if point == 'popen' and not missing else 0)
                    if not missing:
                        r = results[0]
                        assert r['first_failure'] == (
                            'MOCK_PHASE_TIMEOUT' if label == 'GREEN_WORKTREE'
                            and point == 'popen' else 'MOCK_START_TIMEOUT')
                    print(label, test, point, 'PASS')
print('AST_ASSERTIONS_AND_SCOPE=PASS; RED=1 expected failure/2 pass; GREEN=9 pass')
print('MEMORY_ONLY: no POSIX directory IO, real child, DB, service or network')
```

时钟四项独立诊断：

```python
import ast
import time
from pathlib import Path
import pytest
tree = ast.parse(Path('tests/unit/test_perf03_lnx_offline_supervisor.py').read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_SynchronousBlockClock')
ns = {'time': time}
exec(compile(ast.Module(body=[node], type_ignores=[]), '<clock-only>', 'exec'), ns)
observed = []
clock = ns['_SynchronousBlockClock'](observed)
time.sleep(.025)
assert clock() == 0 and not observed
clock.block()
assert clock.blocked_seconds >= .025 and clock() >= .025
before = clock()
time.sleep(.003)
assert clock() > before
with pytest.raises(AssertionError):
    clock.block()
assert observed == ['entered', 'returned']
print('CLOCK_ONLY=4 PASS: preparation excluded; real block counted; continues advancing; duplicate rejected')
```

## 冻结与原字节

下列HEAD Git blob与工作树仅内存归一CRLF后的Git blob逐一一致，未回写转换：

| 路径 | Git blob |
| --- | --- |
| scripts/business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| scripts/biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| scripts/perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| scripts/biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| scripts/business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

supervisor原字节SHA256=6b74c4e0308158bf133e6fe7ae552dd14ca3a7e919076be4181b677b674da796；
安全插件原字节SHA256=9b781894fbbf751ec4344ee1774402ef7892b2ae6ffb5f882a42900982d34323，
均与修改前一致。
目标测试修改前原字节SHA256=95c7bff14f7af6ed9a4d61a9a47770ecb56179f9e31d07081461ee6f57d88d77；
与基线blob展开为CRLF的字节一致。任务书原文hash保持不变。
所有其他跟踪路径由最终git diff与三路径白名单复核。

## 交付与剩余风险

ROOT_ATTEMPTS=0；B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；
REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；HOTSPOT=NONE_PROVEN。
未接触Docker/Compose/PG17/Worker/Scheduler/云/真实SQL/迁移/seed/性能试验，
未读取.env或凭据，未更改安全插件/历史CI/生产supervisor或其他历史代码。
没有放宽断言、增大deadline、缩短注入、skip/xfail/重试刷绿或改覆盖率。

PUSH=NOT_RUN_SANDBOX_INDEX_LOCK_DENIED；NEW_SHA=NONE；CI=LINUX_NEW_SHA_PENDING；
当前尚无本轮提交。Git正常暂存尝试及最终状态见下方追加回执。
NEXT=CHATGPT_INDEPENDENT_REVIEW。
外层先独立核对精确diff、三路径、任务书原文、断言语义、冻结及实时三方基线；
合格后正常提交、非force推送master，再验收新SHA主CI/A4-1/A4-2/Publication和Linux
完整pytest/Ruff。原POSIX文件不得跳过；新SHA若失败只做证据分析，不宣布CI验收完成。
不进入W05-RUN，不把本轮测试修复等同于生产安全/容量或性能授权。

## 最终交接回执

正常单次执行 git add -- 三个白名单路径，exit 1：
fatal: Unable to create .git/index.lock: Permission denied。
未改权限或换工具/身份/通道绕过；未执行commit/push，暂存区无变更。
HEAD/origin/master仍为起始SHA，NEW_SHA=NONE，目标推送分支master（本轮未推送）。
最终工作树恰好一份已跟踪测试修改和两份未跟踪Markdown，无其他脏文件。
测试diff为60行新增/10行删除；只涉及目标测试及紧邻辅助/负例。
最终从本报告逐一提取两段Python并真实执行：RED/GREEN 9项与时钟4项再次符合预期，
没有运行原POSIX pytest文件。报告命令固定原始基线SHA，后续提交后仍可复现。
原任务书原文字节及五冻结blob不变，supervisor和安全插件原字节不变。
最终遍历全部1635个跟踪普通文件，仅将目标测试的摘要替换回修改前摘要后，
排序JSON的SHA256与修改前完全一致：
2a350eacd104195d3aa1c0dc51dbdace2ee61cf937a011d80ac5b343b0b676a3。
因此其余1634个跟踪文件原字节未变；另按CRLF原字节比较目标测试白名单区前后也一致。
目标测试最终原字节SHA256=de9a7bb6012ae2dbcb2f208ebd6204f6f00b4bb9dea31d83aeb235caeb6c68db。
最终再次认证只读GitHub master ref，仍与本地HEAD/origin/master一致，无基线漂移。
git diff --check通过；两份未跟踪Markdown另用git diff --no-index --check -- NUL PATH检查，
无空白错误（exit 1表示新增内容；Git现有LF/CRLF提示不通过改配置或转换原文消除）。
初检发现本报告末尾多余空行，已修正；任务书原文保持不动。
NEXT=CHATGPT_INDEPENDENT_REVIEW；任务仍REVIEW_PENDING / LINUX_CI_PENDING。
