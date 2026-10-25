# A42361 密码学与外部运行依赖审查

本地requirements.lock中没有cryptography/PyNaCl，虚拟环境也未安装；已有OpenSSL 3.6.2。
本轮不修改Python锁、pyproject或工作流，不静默安装任何新依赖。
Ed25519交由既有OpenSSL原语，禁止自写签名算法；规范编码只做字节封装和严格检查。
部署方必须独立固定可执行文件版本及SHA256、只读归属、provider配置和安全更新来源；
仓库runtime-lock只是未配置模板，不含正式信任根、密钥或自动下载器。

开发CRYPTO_VECTOR使用本机已有OpenSSL；CI使用其既有OpenSSL3。不同环境的工具版本只记录测试事实，
不冒称同一已审核部署二进制；真实部署缺少审定digest时拒绝。
密钥只用于临时测试/RFC向量；测试key域不可被部署注册表接受，不生成正式批准。
OpenSSL子进程只进行本地验签，不创建G1资源；shell=false、净化环境、固定参数、输入有界、固定错误码。
私钥不进入probe/仓库；生产验签过程只接受独立只读注册表中的公钥。

官方依据：[OpenSSL3.0 pkeyutl](https://docs.openssl.org/3.0/man1/openssl-pkeyutl/)、
[OpenSSL3.6 pkeyutl](https://docs.openssl.org/3.6/man1/openssl-pkeyutl/)、
[RFC8032测试向量](https://www.rfc-editor.org/rfc/rfc8032.html)。使用Ed25519的raw输入模式，
不预哈希、不混用Ed25519ph/ctx；本轮测试成功不是人工审批或部署证明。

其他依赖仅复用已锁psycopg3.3.4、Pydantic与标准库；PG17/Podman仅交付部署源/固定参数，未安装或运行。
PG镜像、Podman/OS/cgroup能力及独立服务协议仍需管理员供应链与许可证审阅，不能以模板名当已部署。
正式信任服务/资源配置不从.env、CLI或待审bundle获取；控制面与股票数据库迁移完全分离。
