# 独立 G1 控制库源文件（未安装、未连接）

001_control.sql 只用于未来单独审定的 PostgreSQL17 专用控制实例，不是股票 Alembic。
由独立管理员预置 g1_consumer 和隔离 Unix socket/peer 映射，数据库名必须 a42361_control_ 前缀；
前缀不是隔离证明，还须独立 owner 收据与 instance_identity 匹配。不得套用到 stock_db。
角色审批写入者与 consumer 分开；consumer 不能 UPDATE 审批或重置消费。
schema owner 必须是受信独立运维，不能是 probe/controller。DBA 篡改不在数据库 trigger 的防护能力内。

消费：锁定审批 → INSERT SELECT + ON CONFLICT DO NOTHING RETURNING → append-only审计 → commit →
另一服务线程/进程通过新连接读取已提交回执。回执丢失、未知提交、进程崩溃都永久停止本次运行，不重试。
创建预约 UNIQUE(token_id,event)；CREATE_REQUESTED 的唯一提交必须先于 mkdir/Podman。
本阶段只交付事务适配器与 schema；真实并发/掉电/故障切换验证 NOT_RUN。

部署前还缺独立审批写入服务、B 域 RPC peer ACL/并发 receiver、PG owner 隔离证明和收据服务部署。
代码里的 LocalService 客户端不是已经部署的服务；不得据此填写 CODE_READY。
停止/恢复只能由独立管理员对 append-only 日志核对，不删除消费记录，不通过换 nonce 重跑。
