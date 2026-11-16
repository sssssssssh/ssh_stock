# FACTOR-RECOVERY-04-R1 closeout

执行收口日期：2026-11-17（任务书日期 2026-11-16）。
STATUS=PATCH_IMPLEMENTED / CONTRACTS_PASS / NATIVE_ENV_BLOCKED / REVIEW_PENDING。
原生候选等价验收尚未完成；未提交、未推送、未触发 CI。

## 基线、授权及范围

master，HEAD=origin/master=本轮只读认证 GitHub master：
bf7b6a35a453c7d82be363dec2e0f5157221db92。
开始 tracked clean，已有 W05、RECOVERY04 任务/诊断/JSON/测试均保留。
已读取 R1 任务书、前轮 receipt/evidence、真实完整 upsert、R4 来源合同及相关测试；
AGENTS、五治理和业务边界沿用本持久会话已读版本，五治理摘要重新核对未变。
没有启动另一 writer、子代理或后台执行；没有发现未知文件变更。

本轮修改六个 tracked 文件：data_publication.py，三个 r1_integration 脚本
（evidence/controller/seed_loader），test_source_contract_r1_history.py、
test_factor_candidate_write.py。
另按白名单调整既有未跟踪 test_factor_recovery04_candidate_preparation.py，
新增 r1_current_business_sources_v3.json 和本报告。没有新增泛用性能框架。

## 最小生产 diff

PublicationWorkspace.upsert 内，将原样的 updates 赋值表达式从逐行循环内
移至每批 staged=[] 之后、for row in batch 之前（9 行搬移；没有其他生产改动）：

```python
updates = (
    update_columns
    if update_columns is not None
    else [
        c.name
        for c in model.__table__.columns
        if not c.primary_key and c.name not in conflict_columns
    ]
)
```

None 才计算默认列；显式对象仍直接赋值，未复制、转 set/list 或预消费迭代器。
显式空列表继续不更新已有字段。真实注册模型列元数据在批内固定，
未发现需要依赖逐行重新求默认列的业务语义。
KEYS、500 行边界、SQL、事务、锁、now、序列 ID、逐行 NULL/JSON 合并、
首次 base_row、source_id、UUID、行顺序、trace、checkpoint 和 _store 均未修改。
_lookup_batch 仍是每批一条合并语句，未把两个 progress 标签算成两次 SQL。

## 独立 v3；v1/v2 仍严格

新增版本 r1.current-business-sources.v3，baseline=完整 bf7b6a3 SHA，
purpose=OFFLINE_INTEGRITY_ONLY、execution_authorized=false。
严格覆盖原 20 条来源，包含改动后的 publication、Controller、Seed 实际规范化 LF 字节。
manifest 不包含自己或 verifier，避免摘要递归；独立常量绑定其完整 SHA256：
63138e0fdd785d2b614b5a9794134512220534b3edb7522be51a5efbc1fdf918。

verify_business_sources 默认仍为旧 v1；v2 常量、manifest 和原默认 helper 版本不变。
复用既有严格校验体，仅显式按 v2/v3 选择固定 manifest、digest、baseline；
无漂移后 fallback、任选摘要、吞异常或 HEAD 授权。
Controller/Seed 的唯一当前调用点显式切至 v3，仍在当前工作树执行。

结果：
- 当前 v3 通过，包括无需旧 schema LF 读取替身的单独直接调用。
- 当前 v2 正确拒绝 INTEGRATION_BUSINESS_DRIFT，不接受新 publication/调用者字节。
- v2 仍可验证从固定 bf7b6a3 Git 对象复制出的真实历史字节树（临时目录，无应用执行）。
- v2/v3 均有 manifest 篡改、缺失/链接拒绝；v3 检查改动的四条来源篡改及错误路径。
- 未知版本继续在文件读取前拒绝；错误路径集合拒绝在读取任意外部路径前发生。
- v1 在 Linux LF 视图继续按旧 schema 拒绝当前业务漂移；未修改其默认路径或冻结常量。
- 历史 AC31、T26 拆分、A42366 的路由与原断言未改，当前行为未被历史化。

旧固定文件原字节 SHA256 不变：
- v1 schema：e023206e7209ff96ebeb0417dbd516a061c9dc58aee4bf98e9f63fc84e04ea47；
  其原 LF 固定值仍为 f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297。
- v2 manifest / 固定常量：
  9d7cd00c9883a04a65e147ef71611015340955503dce2b36227db940d1b799f6。

## 新增原生回归设计与真实执行边界

扩充现有 test_factor_candidate_write.py，复用 RecordingSession（真实 SQLAlchemy Session
子类、SQL 编译/记录，绝不连接数据库）。当前分支调用真实导入模块的
PublicationWorkspace.upsert，不以摘取 AST 代替当前生产方法。

基线 fixture 仅把该赋值还原到原位置，使用真实模块 globals 编译参考函数，
并验证其完整函数 AST SHA256 与 bf7b6a3 原方法严格相等：
083180e575856afe00b876f674e8b3cb352b1817dc5d37230eb21a8644e7e000。
没有伪造依赖模块、修改生产工作树或启动子进程。

新增 24 个参数展开用例，原九项断言保留：
- 20 项：1/500/501/1001/S2=3450 行 × 默认/空/显式/一次性迭代器，
  对比完整输出和 SQL/参数序列；预置两条已有候选以检测迭代器是否被意外预消费/物化，
  校验 NULL 保留、首次原像、批次边界与行数。
- 3 项：来源不匹配、缺键、第二批 checkpoint 取消；异常类型/身份、
  已完成首批 500 行及失败后未继续写入的假 I/O 状态一致。
- 1 项：真实 DataQualityDaily 元数据的 JSON 合并/NULL、既有 serial ID、
  整数型浮点计数规范化和首次原像。

这些新增原生用例 **未执行成功**；以下环境收集阻断不能计作它们通过。
完整原生候选文件预期 33 项（原九项加新 24 项），需要独立执行层实际验收。

保留原源码隔离辅助诊断，并只调整其基线重建以适应已搬移的生产表达式。
3 个 unittest 方法通过，最终 1.620 秒，退出 0；五种规模输出摘要与前轮证据一致：

| 行数 | 原默认列元数据检查 | 当前批内检查 |
|---:|---:|---:|
| 1 | 54 | 54 |
| 500 | 27000 | 54 |
| 501 | 27054 | 108 |
| 1001 | 54054 | 162 |
| 3450 | 186300 | 378 |

此诊断仍为源码摘取、真实元数据、假 I/O，不是原生模块/PG/整链性能证明。
前轮 JSON/receipt 原件未改写；不从上述计数推导生产提速百分比。

## 测试命令与结果

| 检查 | 本轮实际结果 |
|---|---|
| 五文件当前/历史合同 pytest | 93 passed，85.96 秒，pytest 返回 0，进程退出 0 |
| 新 v2 历史字节树正例 + 原治理 24 项边界保护 | 25 passed，1.05 秒，pytest 返回 0，进程退出 0；有 JUnit |
| 原源码隔离辅助 unittest | 3 passed，1.620 秒，退出 0；不能合称原生候选通过 |
| v3 直接调用/v2 当前拒绝 | 通过，无旧 schema LF 替身；v2 拒绝码为 INTEGRATION_BUSINESS_DRIFT |
| 原生 candidate_write、Worker、factor_service_cancellation、replace_slice | 4 个收集错误，pytest 返回 2，外层进程退出 1，0 测试执行；缺 loguru/fastapi |
| 全项目 python -B -m ruff check backend tests migrations scripts | 退出 1，No module named ruff |
| 修改文件 AST、≤100 行长、尾空白、git diff --check | 通过，不代替 Ruff/原生验证 |

五文件命令为安全 Python 启动后的 pytest.main，参数：

```text
tests/unit/test_source_contract_r1_history.py
tests/unit/test_r1_reviewed_snapshot_v2.py
tests/unit/test_r1_integration_seed_loader.py
tests/unit/test_r1_integration_controller.py
tests/unit/test_r1_real_root_protocol.py
-q -p no:cacheprovider
```

安全启动拒绝 .env、socket/network、shell；历史合同检查仅允许既有只读 Git 和
受控本地历史子进程。Windows 旧 schema 为 CRLF，五文件组只对该 schema.read_bytes
提供原 LF 内存视图，其他当前源真实读取；未写冻结 JSON，未用旧源替代当前代码。
当前 v3 自身另外在不使用该替身时直接验证成功。
原生业务测试启动另禁止 subprocess 和 Engine.connect，收集在缺依赖处停止。

25 项 JUnit 临时文件：.codex_tmp/FACTOR_RECOVERY04_R1_contract_boundary.xml；
summary=tests25/failures0/errors0/skipped0；SHA256：
ee135ca2590b3e4f0ffd454bc91358b773bdaa51d45190228ae41943bd17245a。
93 项组未另生成 JUnit；不把 25 项 XML 冒充 93 项或原生业务回归工件。
pytest atexit 清理既有 pytest-current 出现 WinError5 警告，测试进程仍退出 0；
没有删除用户临时路径或改变权限。

## 容器阻断、未执行项及交接

只读 docker inspect ssh-stock-factor-recovery-test（Networks）退出 1：
用户 Docker 配置读取及 docker_engine API 均 permission denied。
因此未能复核容器当前 Networks={}、挂载或依赖，未执行 docker exec。
没有重连网络、切换 Docker context/权限、绕过 sandbox、重建容器或 docker-compose。
依赖和锁版本未更改；没有安装依赖。

原生 Worker 30 项、候选 33 项、完整取消/发布单元回归和全项目 Ruff 仍为
ENV_BLOCKED / NOT_RUN，不能据合同通过宣布任务验收全部完成。
独立 ChatGPT 可在既有获准断网容器执行原生用例及全项目 Ruff；
本报告不构成容器网络、真实 PG/Worker、生产数据或正式性能操作授权。
只有完整审阅与验证后才决定保留/交付；本轮禁止提交推送，未尝试写 .git 或 SSH。

## 文件身份与保全

以下为本轮改动文件原字节 SHA256（manifest 另见上述固定值）：

| 文件 | SHA256 |
|---|---|
| backend/app/services/data_publication.py | 4ab37d2852887e6df601884891ebcefebc47783ca4548e61be3804348f8ed82e |
| scripts/r1_integration_controller.py | d09e36386b3045f52865a9ca585743769ede403ab9541601ce3c25180b6a4627 |
| scripts/r1_integration_evidence.py | 193bd7fc472f61d8aa34fa1d93cafca4fd88c18a1ef5b46441e10e5709159c47 |
| scripts/r1_integration_seed_loader.py | cd11e0edf89665f028e2b2f9d9cb930db5aac493e2a2c31e73b6ff3295d28ff4 |
| tests/unit/test_factor_candidate_write.py | 99505486f12e253e5ed742c212597d9a220aa494f1db3177757a6e4902ea388b |
| tests/unit/test_factor_recovery04_candidate_preparation.py | 82050bdca2e7aae0f1e8dc0a06797bc72b1611698aba858ec8b02d07880170b0 |
| tests/unit/test_source_contract_r1_history.py | 6c0cfef17478ad78c62005d125268d928bebb4b545a445459ea1482a869ad517 |

publication 规范化 LF SHA256（v3 内实际绑定值）：
7eb0e0b3e5b623f1ef74d616e76301e116492f13a095d49cef9ac7776bf61efe。
除七个白名单既有文件外，其他 1662 个输入原字节排序 JSON SHA256 映射保持：
a4103bb95f7749934da53c4b857660d5bca9d01967bc725702690f7eb48d9ed7。
包括本任务书、W05 两资产、旧 RECOVERY04 receipt/JSON、所有旧合同/源及治理文件。
五冻结源、安全插件、Worker、workflow、requirements、迁移和历史路由均未修改。

REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；REAL_SQL/MIGRATION=NOT_RUN；
RAW_RELOAD=NOT_RUN；FORMAL_PERFORMANCE=NOT_RUN；NEW_CLOUD_SPEND=0；
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。
当前为可审阅补丁，原生业务验证和独立审阅仍待完成，没有新 SHA/CI 通过声明。

## 2026-11-17 独立 Docker 审阅补充（覆盖此前 ENV_BLOCKED 结论）

ChatGPT 通过 Remote Desktop Commander 从已存在的断网容器 ssh-stock-factor-recovery-test 独立执行，不修改生产工作区。容器状态 running、Networks={}，/workspace 只读，无数据库环境变量。原生候选及辅助诊断 36 passed；Worker/取消/replace_slice 46 passed；全项目 Ruff All checks passed。直接在 Windows 挂载的 /workspace 运行五文件来源合同组出现 R1_SOURCE_CONTRACT_DRIFT；查证原固定 schema 字节含 CRLF，SHA256=e023206e...，与固定 LF SHA256=f6be0a5d... 不一致。

为区分平台换行与业务退化，在容器 /tmp/rec04-r1-lf 复制只读工作树，且仅将副本 docs/acceptance/r1_business_compare_schema_v1.json 的 CRLF 转为 LF；副本校验 SHA256=f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297，原件保持不变。在该隔离副本运行：
tests/unit/test_source_contract_r1_history.py
tests/unit/test_r1_reviewed_snapshot_v2.py
tests/unit/test_r1_integration_seed_loader.py
tests/unit/test_r1_integration_controller.py
tests/unit/test_r1_real_root_protocol.py
结果 **94 passed, 209 subtests passed in 61.61s**，exit 0。确认直接挂载下来源漂移由固定 schema 的 CRLF 引起，不应改写冻结源或放宽 v1 合同。独立阅读本轮生产和合同 diff：生产只将 updates 计算移至每批行循环前，v3 manifest 单独严格绑定，v1/v2 保留拒绝语义，Controller/Seed 显式指向 v3。离线审阅结论 PASS；尚无真实 PG17/Worker/生产性能证据，门禁仍 NOT_APPROVED。可按白名单非 force 提交推送，随后以新 SHA GitHub CI 为最终云端回归证据。
