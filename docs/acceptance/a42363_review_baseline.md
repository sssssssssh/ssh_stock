# A42363 20261027 集中整改基线与 RED 证据

基线 `master` / `origin/master`：`a8a675ea8b93dadbba9e905a7a4af67eba163d99`，开始时工作树 clean。
历史普通 CI 40360506303 attempt 1：4590 passed、674 warnings、覆盖率 89.28%。
这些数字仅是基线，不能作为新提交验收。新提交的最终 SHA/CI/ZIP 信息放在交付报告；
仓库文档不能预填尚不存在的自身 commit SHA。

任务书的 `re` 事实经 `git show` 校正：基线 resources.py 已有 `import re`。
先写的 Secret/Container 两条格式合法删除模型在基线均通过，未伪造 NameError。
同批其他回归真实结果 **12 failed, 2 passed, 0 skipped, 0.202s**：
未去敏异常、删除不重放、独立命令预算、bootstrap 成本协议、伪 Owner 自证、停止回执重放、
E 未委托直接读取、最后一轮后 C 漂移、候选 parser 与机读能力矩阵。
本机原始 JUnit `a42363-review-red.xml` 保留在忽略的审计目录，交付报告引用其 SHA。

后续失败分类另保留：首次集成 4 failed/21 passed（动态角色断言误用旧前缀、
模型 A receipt 误将 EXISTS bool 当序号、正例未闭环）；修复测试模型语义后重新验证。
扩展模型 32 failed 源于新增测试缺少 copy 导入，原始 XML 保留，不能算生产缺陷证据。
新增 API 的最终 GREEN 和 Linux 实际结果以最终 SHA 工件为准，不删除旧失败日志。

六份历史 manifest 原字节：

| 文件 | SHA256 |
|---|---|
| docs/acceptance/a42351_reviewer_overlay_manifest.json | `ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648` |
| docs/acceptance/a4236_overlay_manifest.json | `d93bf795a59cb0a168f0e96f4382d58efcbdc2833bc43e22ebde3254a09c1156` |
| docs/acceptance/a42361_overlay_manifest.json | `a88d62d980751cfe182bcffc0a450c21d57195810bdce4e24c80f43c4ff1fb64` |
| docs/acceptance/a42362_overlay_manifest.json | `692b2ca9f3f1f95404a6ec953b557d6a6b510123a522b9f357163d3b016b1817` |
| docs/acceptance/a42363_overlay_manifest.json | `92f67e70c19eee81ef2ce19283aa9969748480cbc36921df01ebba902bc64662` |
| docs/acceptance/a42363_complete_overlay_manifest.json | `d3f5bdce5c9a05b578eda1f599f9404f78f696170d233a3da1d105008ebbd9ff` |

新第七层清单：`a42363_review_overlay_manifest.json`，允许路径精确为 28 条，
不接受目录前缀。旧六份 manifest 不改，逐个在真实收口 commit 上验证其旧 pin。
旧全部 tests Git blob 必须与基线相同；complete_guard 对当前消费者提供累计视图，
独立 review_guard 另外检查 a8 基线的精确增量、隐藏索引、HEAD 全量 FD walk。

初始本机全量 unit+integration_offline 为 3755 passed/8 failed，8 项为旧测试 Linux
`/proc`/长 AF_UNIX 路径依赖；这些旧测试不改、不 skip，必须在最终 Ubuntu CI 真正执行。
