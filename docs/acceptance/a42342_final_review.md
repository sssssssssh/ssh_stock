# A42342 最终同 SHA 回执（追加，不覆盖历史 closeout）

核对日：2026-10-25。源码/远端 master：`7681b57b68aa2f402e1bac2dc59ade606700f759`。
开工工作树干净，HEAD、origin/master、`git ls-remote origin refs/heads/master` 一致。

## 三层证明

1. 仓库源码：旧 runner/reviewer、v2/v3、manifest 与 baseline 文件 SHA 已核对，见 a4235_baseline_freeze.md。
2. 实际日志：[主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/40070964756)
   test job `120804096889`，attempt 1，3337 passed / 674 warnings，coverage 89.28%。
   [专项](https://github.com/sssssssssh/ssh_stock/actions/runs/40070964706)
   contracts job `120804096584`，attempt 1，A4233 319、A4234 109、A42341 241 passed，Ruff 成功。
   主 CI authorize、lookup-tail-attribution、capacity、publication-release-gate 均 skipped。
   主 CI 迁移 current=heads=`0058_data_publication`；原构建/前端/浏览器步骤 success。
3. 实际 ZIP 下载：以下 SHA256 为本地对下载 ZIP 字节计算，并与 GitHub API digest 一致；不是仅 metadata。

| 工件前缀（完整名字为前缀-SHA-run-1） | ID | ZIP SHA256 |
|---|---|---|
| a42331-safe-ci | 12552690781 | 5737e377ff57524f2c99e19fc17b6ba7265b8d83e4a4feb338549ce4ccff7003 |
| a4233-contract | 12551660343 | 9c43d8c243714063c09a86dac885cb67032cc44653711396868e48820279e56f |
| a4234-contract | 12551136937 | e41c0654612c178b28add00d030caf2279a34b0e8aa6d7a3b910a7b34e4faf80 |
| a42341-contract | 12551042062 | 09dd0c5d43acdc9d4ebeddb64dbca5c14c06b17a66e6afca2c429f1e0f77a88a |

safe-ci 的 full JUnit 为 3337/0/0/0，failure.json 绑定上述 SHA/run/attempt，六份 JUnit hash/bytes 已核对。
三项专项 tests.json 计数分别 319/109/241，均绑定上述 SHA/run/attempt。
A42341 的独立 expected 从当前冻结源码与外部核对的 run/attempt 构造；两 bundle 实际离线解析：
完整 128 点、64 对 SIMULATED_ACCEPT；未完成前缀 3 点、SQL_TIMEOUT 和 CLEANUP_FAILED 为 SIMULATED_REJECT。
A4233 ZIP 内容及 tests.json 已核对，但本次不重新认证其微型物理环境身份；三 tick 不代表长窗能力。
其他工件仅 API metadata 核对，不声称全部下载或重新运行。

## 不能隐去的遗留问题

CI 成功是真实事实，但不是所有负例均已覆盖。纯内存复核再次发现：用 MockObserver 在 position 1
注入 OBSERVER_INVALID 后，将末点 STOP_TIMEOUT 的 joined 改 true、末点/顶层 cleanup 改 true、
清空 cleanup codes，旧 review 仍返回合法 INCOMPLETE / SIMULATED_REJECT。
worker_finished 仍为 null、生命周期仍只有 INIT/RUNNING/STOP_REQUESTED，与 joined=true 矛盾。
这是上轮已报告且尚未获准补丁的安全合同缺口，不能以 CI 绿色称其修复。
首次复核脚本误读返回键 decision 导致 KeyError；更正为 calibration_decision 后实际复现成立。

本轮任务明确冻结旧 Reviewer，因此不修改、重签或删除历史证据；新 A4235 不调用旧 Reviewer
作为能力信任源，另行严格检查生命周期。遗留缺口需独立授权整改，不能标记旧逻辑完全验收。
以上不影响如实存档 CI 回执，但总体能力和真实性能继续 BLOCKED_WITH_EVIDENCE。
