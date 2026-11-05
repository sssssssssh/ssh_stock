# BIZ-PERF-04-B 确定性离线股票数据

2026-11-06。开发前 master/HEAD/origin/master/实时远端为
9df4cfed0d0153b09b0f4038882fa8423fe732e1，clean。负责人已验收关闭 04-A，
本轮不修改其源码、合同、报告或旧工件，仅实现 04-B，交付后 REVIEW_PENDING。

## 固定配置与数据语义

入口 scripts/business_synthetic_dataset.py，仅 Python 标准库；无应用、Provider、数据库、
Worker、网络调用或 .env 读取。普通 pytest 只运行 S1 与 S4 的受限前缀，不生成百万行。

| 级别 | 股票数 | 开市日 | 日线行数 | 全部表行数 |
| --- | ---: | ---: | ---: | ---: |
| S1 | 4 | 665 | 2660 | 14905 |
| S2 | 150 | 665 | 99750 | 403557 |
| S3 | 752 | 665 | 500080 | 2006081 |
| S4 | 2165 | 665 | 1439725 | 5767487 |

所有配置固定 seed=0（常量分布不使用伪随机数）、generator_version=
`biz-perf-04-b.generator.v1`、calendar_version=`synthetic-weekdays.v1`、dataset_id。
请求区间 2025-01-01～2025-01-31；起点前 900 自然日（2022-07-16），至请求结束共931自然日。
日历是明确的合成周一至周五，不代表真实交易所节假日。保持250交易日预热和430日回看
要求及足够输入覆盖；本阶段只准备数据，不计算因子、不执行预热或根任务。

S1 逐表与旧 business_recalc_measure.py 的真实 seed_rows/播种片段做离线执行对照。
使用真实 ORM 列定义，但数据库调用被内存记录器替代；只比较 ORM 实际映射列，
补上 trade_calendar 的原 exchange=SSE 默认值。原脚本、S1 数据逻辑完全不改。
旧 IndexDaily 播种复制了 StockDaily 的非映射 source_updated_at，ORM不持久化该字段，
新离线行也不包含它。这不是股票数据语义差异。

配套合同：每个股票/开市日恰好一条复权因子1、一条 daily_basic（close=20，
两类市值1000000）、一条涨跌停（pre_close=20/up=22/down=18）。
股票日线与指数均为原常量 OHLC/成交量额，指数固定三只原配置代码。
sector=101 / SW / BIZ，所有股票自历史起点为成员；不生成题材快照。
ST、停牌两张表为空，每开市日各有一条对应 PASS 质量事实（expected/actual=0）。
相关日期时间固定2026-10-27T00:00:00+00:00，与旧种子一致。
未显式指定的可空字段/ORM默认值继续按原模型语义处理。数据库自增ID不属于离线业务摘要。

## 文件与校验合同

每表一个 JSONL，固定日期/代码顺序；行内字段按键排序、紧凑JSON、UTF-8、LF，
禁止NaN/Infinity。分块大小1～4096，仅影响缓冲，不进入数据身份；内存为日历常量+
一个分块+一行校验，不保留全量主键集合或全量数据。

manifest 包含完整配置、逐表实际行数/字节/SHA256、总行数/字节、总摘要及准备资源观测。
总摘要对 config+tables 的规范JSON计算；资源计时、分块参数不参与身份，重复运行保持摘要。
这套离线规范摘要不等于旧 PostgreSQL to_jsonb 表摘要，旧 Run/hash 原样保留。

验证器逐表流式比较固定版本的预期规范行，逐字节验证业务字段、日期、主键顺序及唯一性、
股票/sector引用、值域/空值、配套表完整性；因此删行、重复行、改价格/代码/成员、
非规范顺序或编码均拒绝。随后校验实际计数/字节/摘要和 manifest 汇总。
该验证器只支持四档固定常量分布，不是任意市场数据质量验证器；扩展分布须新版本合同。
校验不依赖 manifest 自报摘要；即便重算被篡改文件哈希也不能绕过预期业务行检查。
未知文件/字段、symlink、超长行、非法配置及错误元数据类型均拒绝。

资源观测是数据准备成本：generation.wall/cpu 为生成阶段，peak_process_rss_bytes 为
独立生成子进程生命周期峰值（不是精确阶段增量/进程树指标），chunk_size为配置。
验证成本独立通过外层生成+验证计时记录，不当作 Worker 耗时或性能验收收益。
准备结果无任何容量、性能或生产许可字段/授予能力，不进入04-C状态模型。

## 显式执行与回滚

```text
python -m scripts.business_synthetic_dataset --scale S1 --output <new-directory>
python -m scripts.business_synthetic_dataset --scale S4 --output <new-directory> --chunk-size 4096
python -m scripts.business_synthetic_dataset --output <existing-directory> --validate-only
```

输出必须是新目录，不覆盖已有文件；失败保留不完整目录且无完整 manifest。
只有全部生成结束才写 manifest，CLI随即完整校验；不得将单独生成文件视为校验已通过。
不导入本脚本到现有 BIZ03 controller，不更改一次性授权/Environment/协议/Workflow。
任何 S2～S4 Worker 根任务、装载数据库、冷/热测量、容量实验都须另行批准。
回滚采用新提交撤销新生成器/新测试/新文档，不动历史代码和原始验收。

## 实测与验证

显式离线生成四档，每档以 chunk=256、4096 各生成校验一次，逐表及总摘要相等。
实际表摘要、总摘要、字节数、两次生成资源见 biz_perf_04_b_generation.json。
原始大文件保存在仓库外临时目录，不提交生成数据、缓存或构建产物。
定向与相关历史合同413 passed / 0 failed / 0 errors / 0 skipped，JUnit 7.876秒；
Ruff全范围、git diff --check通过。S4生成CPU约16.907秒、wall约16.978秒，
4096分块峰值RSS 23019520字节；256分块峰值17842176字节。
这些是独立子进程准备成本，不是业务根性能。最终定向测试统计/JUnit摘要见 biz_perf_04_b_validation.json；Ruff与diff检查同轮执行。
最初兼容测试发现记录器保留非映射Index字段及测试总行数笔误，已按真实ORM持久化语义
修正记录器并校正预期14905；没有变更原测量/业务代码或旧断言。

剩余边界：合成常量价格/工作日日历不能代表真实行情分布、停牌、缺失和复杂PIT。
无数据库集成/全量Worker、金融输出或性能测量；这些仍NOT_RUN。
标准库resource观测目标为本轮macOS与既有Linux环境，Windows CLI资源采样未适配。
04-B交付后停止，04-C～F未授权。
