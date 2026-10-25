# A42361 信任模型与实现边界

状态 **PARTIAL_OFFLINE_TESTED / BLOCKED**；不是 CODE_READY，也不是 G1 批准。

## 实现与信任分离

W01 提供真实 OpenSSL3 Ed25519 验签。canonical ASCII JSON 是 UTF-8 子集；重复键、浮点、非规范编码、
未知字段和隐式标量转换拒绝。签名覆盖 payload 原字节，不覆盖自行整理后的不同字节。
配置中的固定 issuer/kid/key 与外部 registry 实时撤销/托管审查摘要匹配，再核对独立 approval。
两名不同审批者的摘要必须不同，签发者不能兼任审批者；审批绑定 exact SHA/source/overlay/run/attempt、
fixture UUID/nonce/marker、scope、image digest、预算和审计对象。时钟/撤销不可用立即关闭。
不含签发器/正式私钥/正式 token。RFC8032 测试钥仅用于真实密码学正确性，不是独立审批。

部署配置由独立管理员 root-owned、只读 FD 与另行固定摘要提供，不从仓库/环境/自由路径加载。
root 是配置文件所有者，不是容器或 probe 的运行身份。配置读取不能证明部署现实独立性；
Python 私有对象 seal 只约束代码调用顺序，不是防同进程攻击的 OS 安全边界。
生产管理员必须另外维护 TEST_ONLY denylist/公钥托管审核；无法数学识别任意随机测试公钥被恶意标成正式钥。
不能将 usage 标签单独视为托管证明。

| 域 | 职责 | 当前责任人/部署 |
|---|---|---|
| A issuer/registry/approval | 私钥、公钥、撤销、两人审批 | UNRESOLVED，未部署 |
| B consumer | 专用 PG17 控制库、唯一消费、提交回执 | UNRESOLVED，适配器/schema 已写，真实集成 NOT_RUN |
| C controller/PG owner | rootless 创建、最小权限、身份与精准清理 | UNRESOLVED，owner 服务端/部分创建回收未齐 |
| D supervisor/worker | 固定16 SQL、同连接、外层强制终止与写盘 | UNRESOLVED，worker/kill 原语已写，隔离 launcher 未齐 |
| E absent auditor | 独立销毁与不存在原始证据 | UNRESOLVED，只有客户端协议，非现实证明 |

七个 peer UID/socket 必须各异；C 不持 B 控制库凭据，D 不持 C 容器权限，外部 Unix peer 由 SO_PEERCRED 核对。
RPC 固定域/方法、≤64KiB 帧与绝对 deadline；B的receiver/ACL已有源码，其余域服务端未齐。
客户端成功≠服务端已部署。receiver的网络期限不能中断阻塞handler，部署前仍需进程外监督。

## 对外具体协议（仅B receiver源码；全部未安装）

固定帧：4字节网络序长度 + canonical JSON `{schema_version:"a42361.rpc.v1",method,body}`。
不能有外来 SQL/DSN/shell callback/公共端口；未知方法在客户端先拒绝。

- registry/key-status：issuer、kid、公钥SHA；返回相同绑定、revoked、observed_at、custody_review_sha256。
- approval/approval：approval_id；返回闭合 Approval schema 的完整记录。不可把输入 approved 布尔当结果。
- B/consume：原始 envelope_hex 和独立绑定；B 须重新验签/审批，提交后返回 receipt_sha256、committed。
- B/receipt：token/payload 摘要；新连接读实际提交记录，字段由 PostgresConsumer.read_receipt 定义。
- B/journal：CREATE_REQUESTED 或 SECRET_CREATED 的闭合请求；原子唯一预约后返回 event、request_sha256、committed。
- PG owner/create、receipt、run：bootstrap secret、独立 PG 身份/权限、受监督进程绑定的短期 probe lease。
  该 owner 服务端、秘密保管/初始化预算实现 **未齐，BLOCKED**，不接受调用者自报身份。
- C/create、destroy：只接受 B 已提交摘要；创建返回创建摘要/绑定，销毁返回 requested/destroyed/absent 三收据。
- D/run、terminate：只允许已批准新 fixture 的自有 worker，不接受外来 PID/argv；实际 launcher **未齐**。
- E/journal、absent：独立核验归属后保存顺序证据，不得复述 C 的 absent=true；真实服务 **未齐**。
- 独立 Reviewer 的各域 receipt 查询必须返回原始持久收据摘要、绑定和 COMMITTED_VERIFIED；
  不能仅在 bundle 内互相重 hash，未部署时最多 OFFLINE_CONTRACT_VALID、exit2、qualifies=false。

外部服务、权限分离和 operator 值都没有通过本次提交自动建立。完整工程缺口见 unresolved_methods。

## 2026-10-26 B接收与会话身份续作

`ConsumerService.serve_once(fd)`只接收独立管理员已bind/listen的AF_UNIX FD，不创建socket路径、
不注册CLI/后台循环。先验证InstalledDeployment、B自身UID、安装路径/监听socket，再以SO_PEERCRED
取得对端身份；D可consume，C可journal，C/PG-owner/E/D可receipt，其他方法/身份先拒绝。
peer_uid不来自请求JSON。每连接只处理一个规范帧，分片不重置绝对deadline；未知异常只有固定去敏码。
错误响应是闭合`a42361.rpc-error.v1`，客户端只抛Fault，无自动重发。

B重新核验原始envelope、独立Git绑定及审批；commit返回后用**另一连接**核验PG17、专用库/角色/
instance_identity，再读已提交消费或日志。禁止原writer连接/同事务视图/内存字典作为回执；读不到、身份不符、
关闭失败或ack丢失均未知提交，不退款、不重试、不创建fixture。B无需回调自身RPC才能获得回执。
请求schema及journal的UUID/摘要/三项派生名称/secret字段在数据库连接前验证；不能透传SQL或任意资源路径。

worker的预连接`a42361.probe-lease.v2`不接受backend_start字段，只绑定lease_id、受监督worker PID、
payload/creation/角色摘要、socket/库、固定100ms/只读和期限。连接使用lease特有application_name；连接后
owner的`a42361.probe-session.v2`必须交叉绑定同lease/PID/creation/payload/system identifier/角色及真实
backend PID/start，再进入原固定16SQL。两阶段仍只有接口及离线控制流验证，owner实际证明方法没有补齐。
Python私有入口和测试注入不产生OS信任；独立服务管理/审批写入/owner/监督缺失时仍BLOCKED。

ControlService也校验完整ConsumptionReceipt schema及与grant逐字段等价，而非只比较token/nonce/head。
新控制库源schema持久化唯一fixture_uuid，资源预约CAS校验三项名称从该已消费fixture派生；
只有`a42361-`前缀相同不构成资源授权。此DDL只供未来新建独立控制库审阅，不是业务迁移，也没有执行。
