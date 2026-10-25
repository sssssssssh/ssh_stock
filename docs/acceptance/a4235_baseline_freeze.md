# A4235 W00 基线与冻结边界

基线 master `7681b57b68aa2f402e1bac2dc59ade606700f759`；开工工作树干净，三个远端/本地引用一致。
旧同 SHA CI/工件已先落档于 a42342_final_review.md，含未关闭的旧 Reviewer 矛盾证据问题。

| 精确冻结文件 | SHA256 |
|---|---|
| scripts/a42341_calibration_runner.py | 1789ff74dbc71e1981ab79264a55f891de7fa49bd0611a10ece3c625e50e2347 |
| scripts/a42341_calibration_review.py | f156a58425bdfa44c96ce075240b396343173360c0134a98e470dbae4cac3d41 |
| docs/acceptance/v14_a4_2_3_4_calibration_protocol.md | b22df81e1e439a5109dc6a92c929adbfa7ac0384f1d3a1c4bd33ec4f65677b96 |
| docs/acceptance/v14_a4_2_3_4_calibration_protocol_v3_proposal.md | 065b529f759308c49630c5ce390864a7589b51fcb1be645ca420ed3575692220 |
| docs/acceptance/a42341_preparation_manifest.json | 4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e |
| requirements.lock | aa8d7f344bc70c749cb91375950ad0620a551add2933329b82520c35bd7c59b5 |

Git baseline blob 是冻结权威，不依赖待审工件自述。新 guard 对 baseline 中 backend/config/migrations/frontend/
.github/scripts/tests/docs/acceptance 的原有路径执行 Git 原字节 diff，并对完整 ls-tree 原文作 SHA256；原测试、SQL、模型、全部工作流、
Gate、profiles/policies/consumed、历史协议和证据不能改变。新文件仅 a4235 命名空间和此次追加文档。
完整 ls-tree 原文 SHA256：`b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9`。
新命名空间以外的新增生产/脚本/工作流文件也被拒绝；不只检查原路径是否修改。
四份权威 Markdown 仅追加新阶段边界，不重写历史结论。依赖和有效 8 次、128 点/64 对原顺序冻结。

G1 未批准：不建库、不启动 Docker/PG、不读业务 .env、不连接任何数据库。
G2=PENDING，A/B 均候选，C 为当前默认；G3=NOT_AUTHORIZED。
只实现静态/Mock 合同与硬拒绝的 live 骨架，不实现可激活的真实 adapter。
需要未来受信 harness 独立签发/验证、持久消费和清理链后才可另审 G1，不注册当前 profile 或 token。
