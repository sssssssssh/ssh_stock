# 独立 G1 控制库源文件（未安装、未连接）

001_control.sql 只用于未来单独审定的 PostgreSQL17 专用控制实例，不是股票 Alembic。
由独立管理员预置 g1_consumer 和隔离 Unix socket/peer 映射，数据库名必须 a42361_control_ 前缀；
前缀不是隔离证明，还须独立 owner 收据与 instance_identity 匹配。不得套用到 stock_db。
角色审批写入者与 consumer 分开；consumer 不能 UPDATE 审批或重置消费。
schema owner 必须是受信独立运维，不能是 probe/controller。DBA 篡改不在数据库 trigger 的防护能力内。

消费：锁定审批 → INSERT SELECT + ON CONFLICT DO NOTHING RETURNING → append-only审计 → commit →
B本地另开连接，重验专用PG17实例后读取已提交回执；不RPC回调自身。回执丢失、未知提交、进程崩溃
都永久停止本次运行，不重试。日志预约同样提交后新连接读回原details再确认。
创建预约 UNIQUE(token_id,event)；CREATE_REQUESTED 的唯一提交必须先于 mkdir/Podman。
本阶段交付事务适配器、schema及受控监听FD receiver源码；真实并发/掉电/故障切换验证 NOT_RUN。

部署前还缺独立审批写入服务、受信FD/安装/服务管理、PG owner 隔离证明和收据服务部署。
代码里的 LocalService 客户端不是已经部署的服务；不得据此填写 CODE_READY。
停止/恢复只能由独立管理员对 append-only 日志核对，不删除消费记录，不通过换 nonce 重跑。

ConsumerService只接受D的consume、C的journal、C/owner/E/D的receipt，不接受SQL、DSN或外来callback。
传输处理器不bind/listen、不在import/CLI中运行；单帧≤64KiB、绝对网络期限≤2s，不自动重试。
本次仅模型测试，不曾打开socket服务/控制数据库。handler物理终止依然依赖未齐的独立监督链。

新schema源码将签名绑定的fixture_uuid作为消费的唯一列持久化；journal的INSERT SELECT同时核对名称
从该fixture派生，拒绝替别的fixture预约。只适用于未来审定的新建独立实例；不是对既有控制库或业务库
的在线升级，不运行DDL。真实PG17约束/权限/并发验收仍待独立基础设施准入。
