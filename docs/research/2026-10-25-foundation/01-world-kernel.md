# 最小世界内核：首轮技术建议

检索日期：2026-10-25。已读 AGENTS.md、章程、决定记录、架构候选与首轮实验。本文是建议，不将 P11、Q02、Q06—Q08 改为已决定；未写应用、运行数据库或验证性能。下列官方链接均已实际打开；“事实”来自文档，“推断／建议”是本项目判断，“待验证”尚无运行证据。

## 首轮选择与边界

**建议：C#/.NET 10 模块化单体＋SQLite，同一进程裁决命令；先完成观察、移动、消耗材料生成对象、重启恢复。** 普通类和模块接口足够，对象、资源、回执放在同一数据库统一提交；首轮不引入 ECS、Actor、微服务或脚本运行时。

| 路线 | 文档事实与适用判断 | 首轮取舍／反例 |
|---|---|---|
| .NET 单体 | 适合把权限、对象与资源放进同一提交边界；这是工程建议，不是性能保证 | 起步成本低；若核心玩法依赖连续碰撞、浮力，手写物理内核反而增加成本 |
| 游戏引擎内核 | Godot 支持无显示器的专用服务器，不能以“无法无画面测试”排除引擎。[官方导出文档](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_dedicated_servers.html) | 实时物理成为验收核心时优先评估；当前先隔离表现层，场景保存不能代替跨对象资源事务 |
| ECS | Unity 将实体标识、组件数据与系统处理分开。[官方概念](https://docs.unity3d.com/Packages/com.unity.entities@1.4/manual/concepts-intro.html) | 推断：大量同类对象逐步模拟适合它；几十个对象的命令核算尚无采用收益证据 |
| Actor／Orleans | Grain 默认逐请求执行；跨 Grain 事务需显式启用和事务状态存储。[调度](https://learn.microsoft.com/en-us/dotnet/orleans/grains/request-scheduling)、[事务](https://learn.microsoft.com/en-us/dotnet/orleans/grains/transactions) | 独立实体跨节点分布时再评估；“钱包 Actor 扣款后物品 Actor 崩溃”不会因单线程自动原子化 |

**事实：**.NET 10 是 LTS，支持至 **2028-11-14**；官方当前补丁 **10.0.13**，保持支持需要跟进补丁。.NET 8 虽仍是 LTS，已接近 2026-11-10 支持截止。[支持策略](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core) 本机 SDK 10.0.302／runtime 10.0.10 是派工给定事实，不等于最新版；本轮不升级。

## 最小模型与模块

以下均为建议；首轮可以按目录分模块，不必拆服务或引入框架。

| 边界 | 必要状态与职责 |
|---|---|
| 身份／命令入口 | Resident：ActorId、OperatorId、类型、所控 EntityId；会话独立，人类和 Agent 共用动作权限 |
| 世界 | WorldId、RegionId、区域规则版本、逻辑时间；Entity：稳定 ID、位置、生命周期、DefinitionId／Version、RuleSetVersion、Revision |
| 资源 | 资源类型及整数最小单位；持有者／容器、数量、Revision；变更记录关联命令、来源、去向和原因。制造明确消耗及产物；初始供给单独记来源，不预定货币或通胀 |
| 规则 | 不可变规则版本、内容哈希、参数和适用范围；读取状态并提出变更，由内核核验提交，不直接写库 |
| 持久化／观察 | CommandReceipt 保存去重键、请求哈希、结果；事件记录裁决输入、版本与变更。观察仅返回获准的已提交状态 |

数据库 SchemaVersion、并发 Revision、定义版本与规则版本分别维护。首轮保留当前状态与关键变更，不建设完整事件溯源；资源数量不隐藏在任意 JSON 中。

## 存储取舍

**事实：**SQLite 每个数据库同时只有一个 writer；WAL 可读写并行，不能并行写入，且要求同机访问，不适合跨机器共享文件。[隔离](https://www.sqlite.org/isolation.html)、[WAL](https://www.sqlite.org/wal.html) **建议：**单主机、本地文件、短事务适合首轮；WAL 是否启用由隔离实验确认，不凭连接数推断吞吐。

PostgreSQL 可并发处理事务，但同一目标行更新仍会等待；默认 Read Committed 的两次查询可能看见不同状态。[官方隔离说明](https://www.postgresql.org/docs/18/transaction-iso.html) **建议：**跨行不变量需锁住共同约束记录（固定顺序），或用 Serializable 并整笔重试。**失效条件：**写入等待持续超过预先约定预算，或需要多主机写入／故障切换，重新评估 PostgreSQL；它增加服务、备份和连接管理成本，也不能消除热点争抢。

SQLite 部分结构变更需建新表、复制数据、重建索引和检查外键；PostgreSQL 的 ALTER TABLE 默认取得强排他锁，具体子命令有例外。[SQLite 迁移步骤](https://www.sqlite.org/lang_altertable.html)、[PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html) **建议：**编号 SQL 迁移，先备份并在副本验证，首轮停写迁移；换库要重测类型、约束和隔离语义，不能只换连接字符串。

## 命令原子提交顺序

1. 验证身份、请求格式；以 `(WorldId, ActorId, CommandId)` 建唯一去重键，规范化语义参数后计算哈希。
2. 开启短写事务，再查回执：同键同哈希返回原结果；同键异参拒绝。必须在检查旧 Revision 之前识别已成功重试；首轮不清理回执。SQLite 可用 BEGIN IMMEDIATE 提前取得写权。[官方说明](https://www.sqlite.org/isolation.html)
3. 在事务内读取当前状态、权限与冻结的规则版本，检查预期 Revision、材料和容量；过期版本返回冲突，不擅自改成最新版执行。
4. 条件更新资源和版本，同时创建实例、变更记录与成功回执；任一步失败整笔回滚。确定的业务拒绝可仅保存失败回执；基础设施错误不冒充业务拒绝。
5. 提交成功后才返回成功并更新观察结果。提交结果不明时，保持同一命令 ID 查询回执；禁止换 ID 重做。锁忙只有限退避；读转写失败须重新读取并重试整笔事务，不能只重试扣料语句。[驱动事务文档](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions)

**反例：**先扣料提交、再生成物品，或提交后另写回执，都会留下半完成或重复交付窗口。事务内不调用 LLM、网络服务；外部决策先形成输入，入事务后重新校验。

## 时间、规则与下一步

**建议：**首轮用持久化整数逻辑时间和显式 Advance 命令；调度器走同一命令入口，时间及状态同事务提交。延时任务记录到期时间与稳定任务 ID，按“到期时间、ID”排序，停机先暂停世界时间。离线补偿、固定帧物理另立实验，不能直接用离线时长乘产量。

新规则先增加不可变版本和声明式配方，旧实例继续绑定旧定义／规则；跨版本交互没有明确转换就拒绝。升级用显式迁移并核对 ID、资源和任务，缺失旧处理器时阻止相关动作，不静默套新规则。发布主体仍属 Q02，本文不授权玩家改全局规则。

**待验证：**交协调者实验覆盖并发争抢最后一份材料、同键重试／异参、扣料后故障回滚、提交后响应丢失、重启、时间重复推进、旧实例读写及迁移失败；记录余额、实例数、回执和等待时间，不预造性能阈值。另记录原生 `sqlite_version()` 并锁定依赖：官方 WAL-reset 修复为 3.51.3+，另有 3.44.6／3.50.7 回补，不能凭 NuGet 版本认定已修复。[WAL 第 11 节](https://www.sqlite.org/wal.html) 协调者已告知拟用缓存包组合并核实原生版本，实际结果以其证据为准。
