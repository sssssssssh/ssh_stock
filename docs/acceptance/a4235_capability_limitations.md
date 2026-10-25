# A4235 检测器能证明与不能证明什么

能证明：纯模型与指定反例的合同一致性；锁定驱动 PrepareManager 的阈值/键隔离行为；
本地冻结源文件、结构和摘要；旧 GitHub run 日志/下载 ZIP 的指定字节及计数。

不能证明：真实 PG17 owner/最小权限/物理实例；无扰动 cached plan 结构；C0/C1 prepared
稳态；真实 backend CPU namespace/时钟桥；长窗 Observer 的资源/对 lookup 的开销；
维护事件不存在；任何 C1 因果、P95、正式容量或生产授权。

prepared_capability.json 的 typed 内容是 PreparedCapability 模型（a4235.prepared.v1）；
纯模型只返回 DRIVER_MODEL_ONLY / REAL_NOT_PROVEN / C0_C1_NOT_PROVEN / prepared_stable=false。
未运行独立实机探针，不能输出 SYNTHETIC_OBSERVED，也不声称 cached plan VERIFIED。
本轮工件写入器只发布离线 capability/limitations/failure/manifest；不伪造真实 prepared 报告。

新 evidence_kind 只有 STATIC_ONLY/MOCK_ONLY，READY 输入在独立 reviewer 中明确拒绝。
API 调用者得到的普通 dict 或模拟 hash 不是签名。未安装任何真实签发、持久消费或数据库连接代码。
模拟 grant 的 expired/consumed/不同 nonce 检查不是一次性真实授权的实现证据。
CLI 仅静态检查 exit2、有效离线能力工件 exit3、拒绝 exit1，从不返回性能成功 exit0。

文件写入有2秒合同预算、failure先写/manifest最后；超预算撤销本次自有 manifest，保留首错收据。
OS fsync 等系统调用不能被 Python 检查强制抢占，故该预算只检测超时，不能证明硬实时终止。
无 manifest 的部分工件必拒绝；清理撤销失败是固定错误，不伪装清理完成。真实运行前需独立验证
存储/执行器的有界终止与异常审计。本轮不以模拟文件写入成功推断物理清理或实时保障。
