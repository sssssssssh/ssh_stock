# FACTOR-RECOVERY-03-R1：Worker心跳启动异常修复与固定源码合同兼容
日期：2026-11-16；用户中心目标：恢复因子计算成功率和Worker持续服务，随后定位真实性能瓶颈。
基线 master=232baf9e13cd7b23731e59188c86e0e253c3a394。前轮报告 docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_CLOSEOUT.md 已独立阅读，确实在 job_worker.py:268-278 Thread.start 异常后 finally:464-465 对未启动线程join导致RuntimeError二次覆盖，且外层只捕获DB异常，Worker轮询可能退出。前轮仅源码AST模拟RED，不等于现场根因。
## 本次明确范围
1. 先核对Git及全部未跟踪文件，保留前轮03任务书/closeout和W05文件，不覆盖。阅读AGENTS、治理文件和现有固定合同机制。精确定位旧 r1_business_compare_schema_v1.json 对 job_worker.py 的SHA钉住位置及所有消费者，说明为什么02曾CI失败。不要直接改旧manifest hash、关闭测试、修改安全插件、降低断言。
2. **优先寻求安全兼容的真实修复**：在当前业务Worker实现中仅针对“Thread.start未成功”的心跳join增加准确保护；不吞正常已启动线程的join异常，不更改owner/token/失败发布/未知Writer语义。编写原生单测RED→GREEN：启动失败、正常启动、失败记录异常、context清理和后续轮询。只允许当前 job_worker.py 与相关单测最多2个文件，以及新增closeout；如固定源码合同会阻断，必须先找已有可复用的版本化/历史checkout能力，给出具体可审阅的最小合同兼容迁移方案。**不得自行改旧固定合同或hash**；需要合同迁移超出白名单则停止代码修改，报告阻断和精确所需文件。
3. 若合同兼容问题暂不可安全解决，可先增加不会违反冻结合同的离线回归测试，或只交付明确的差异/最小迁移方案；不得为制造绿灯而跳过当前Worker的真实测试。
4. 定向安全测试、Ruff/格式、相关R1合同测试；本机缺依赖则记录ENV_BLOCKED，不安装不放松；不得连PG17、Worker服务、Raw、云端或迁移。所有当前未跟踪原件保留。
5. 输出 docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R1_CLOSEOUT.md，列出 RED/GREEN、精确diff、是否真正修复、CI兼容性、阻断及下阶段与因子计算直接相关的最短路线。**不提交不推送**，等ChatGPT独立审阅。下一阶段必须回到Worker可靠性/候选写入耗时/因子复算，不扩展W05审计。
