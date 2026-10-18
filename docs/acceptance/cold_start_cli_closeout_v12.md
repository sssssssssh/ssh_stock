# 冷启动与安全入口 V1.2 验收

## W01 复现

冻结基线 f3158dd5317f1da2ba950522b300f66b70d9f901；完整 CI 39139452440 成功。
Pandas 3.0.5 / NumPy 2.3.3，Alembic 单头 0058_data_publication。
修复前 `tests/unit/test_cold_start_v12.py`：43 failed / 31 passed（JUnit 保存在隔离实验产物）；
完整输入黄金样本两项已通过。bool/nullable boolean 正常掩码不误报，object 负整数与部分左连接稳定复现。
机会缺失样本分别真实抛出 None 比较 TypeError 与 object NA rolling DataError。

可复现：`python scripts/cold_start_comparison.py --output .codex_tmp/cold-start-comparison.json`，
以及 `python -m pytest tests/unit/test_cold_start_v12.py`。仅使用合成内存数据。
版本决定见 ../design/cold_start_version_decision.md。后续阶段/同 SHA 门禁结果随实现补齐。

## 授权边界

不连接真实生产库、不调用真实 Provider、不部署、不重启业务服务、不自动回填；
容量实验仅在显式指定的专用 PG17 合成库进行。不得将 CI 成功解释为生产上线批准。
