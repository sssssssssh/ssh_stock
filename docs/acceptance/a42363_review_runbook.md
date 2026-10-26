# A42363 运维停止与审查复现

本轮只能运行离线单元/文件进程模型和既有普通CI。不要加载业务.env，不连业务库，
不要启动服务、PG/Podman/真实cgroup，也不手动触发高成本workflow。

开发复现：专用venv，Settings.model_config.env_file=None，DATABASE_URL与
TEST_DATABASE_URL均为synthetic用户的本机127.0.0.1:1不可达离线目标，PYTHONPATH=backend；
运行新增 test_a42363_review.py / review_guard.py / integration_offline review_process.py。
冻结校验必须在提交后clean HEAD运行；不因dirty测试失败删缓存或改旧pin。
全量 python -m pytest 和 python -m ruff check backend tests migrations scripts
在普通Ubuntu CI上执行，PG17为应用CI专用合成库，不是G1执行环境。
前端由既有CI执行coverage/build。本次不修改workflow和依赖。

完整部署前必须提供并独立审查：Linux/cgroup v2+rootmanager私有FD；固定Podman二进制
和专属rootless store；PG17镜像构建/签名/SBOM/entrypoint/health；owner/probe非交互
认证；固定issuer/两独立审批者及撤销；专用控制库角色ACL；E跨UID只读可见性；
所有旁路writer阻断；已审批新预算/GUC/资源协议；grant精确SHA和receipt reader来源。
这些目前未安装；本清单不是自动授权。任一未知不得发凭据或首SQL。

停止顺序：先停止新consume/create/run；D终止原owned scope并保留Guardian；
C stop成功回用原receipt，不明ACK不重发；按原创建身份反向reconcile；独立E核对
B/C和store后双轮8观察；每域从自身持久源新连接读；Reviewer维持nonqualifying。
首错保存，清理错另列。无法证明权限/归属/存在/不存在→UNKNOWN_QUARANTINED。
Volume继续隔离；不得rm-f/prune/前缀批删。创建或删除已尝试绝不因ACK丢失重放。
发布未知保留PUBLICATION_ATTEMPTED/.incomplete，不重新写出成功D收据。
残留清单使用原ID/epoch/namespace/sourceSHA和原始ledger，不从同名对象补造ID。

最终交付报告在工作区忽略审计目录，含最终40SHA、git diff路径、每个普通workflow
run/attempt/job/log、JUnit case身份、API artifact digest、下载ZIP实际SHA分开核对。
先等待当前SHA ordinary CI，Observer未触发记NOT_TRIGGERED；G1/L2/高成本记NOT_RUN。
任何失败不把旧绿色run替代为最终SHA。报告不记录凭据、连接私密信息或签名下载URL。
