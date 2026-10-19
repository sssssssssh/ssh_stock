# V1.3 精确键查询

候选 lookup 不再通过全局 overlay；仅为本批输入自然键，以 JSON recordset 作为输入表，
按 publication/table/row_key 主键关联候选，按原自然键关联 public，通过原生 composite 转回类型。
删除掩码遮蔽 public，但 public 原像单独返回；首次 base_row 仍由原 ON CONFLICT 保留。
不改变计算查询使用的私有 VIEW，不增加索引、迁移、缓存或跨事务读取。

W02 在隔离 PG17 上通过 33 项既有发布/黄金回归；新增 7 项黄金、删除重建、列白名单、
NULL 保留、JSON 合并、原生类型和公开读取隔离回归通过。日志见本机忽略目录 v13-B*.xml/log。
这一提交暂保留额外 public/time 查询；W03 再复用同批返回值，独立衡量吞吐，不提前宣称性能通过。
