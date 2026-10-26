# 有界材料入口 v1 · r10 候选采用契约

2026-10-26。ITER-0022 的实现基线。采用[来源评审14](../research/2026-10-26-continuous/14-material-source-adoption.md)的有界实验建议；不把参数改记成用户已确认的长期经济制度。服务端与客户端已实现，实际验证及未完成边界见[迭代结果](../iterations/ITER-0022-results.md)。

## 世界、来源与身份

显式新场景 `wilderness-material-access-v1`，规则 r10、存储10；默认r8和旧库保持原规则，不迁移。初始四树共12木材、所有角色零库存。原树不再生。保留r9赠送及原实例、回执、actor-state前置条件。

新增来源 `wood-source-east`，中心 `[28,10]`；矩形 `[27,9,29,11]` 自创建时禁止建筑占地重叠，始终不阻挡行走。来源初始关闭、存量0；停止服务后执行 `enable-material-source --instance <worldInstanceId>`，在同一个库内一次性开启。重复开启不重置任何状态，错误实例或仍有计时服务运行时拒绝。

固定实验名册：a1/a1_alias 属 `local-operator`，a2 属 `declared-late`，a3 属 `declared-third`。别名出生 `[5,7]`，a2保留 `[26,17]`，a3出生 `[27,10]`。名册是研发声明的实验输入，所有凭据实际仍由本机操作者控制，不证明现实独立人；旧r9 a1/a2归属不改。HTTP不得修改分组，离线issue-session只轮换既有名册成员会话。

## 时间、预算与分配

服务单调时间从最后已提交毫秒数继续，每250毫秒尝试持久检查；离线不累计，系统UTC跳变不影响生产和期限。未提交尾部时间可损失。同库第二个计时服务由排他文件锁拒绝；独立克隆双写不在保证内。GET只读取；后台以及居民写事务用同一时钟、同一SQLite写锁处理到期和生产。

开启时持久记录enabledAtServiceMs，第一周期是其后10000服务毫秒，不追补开启前的时间。此后每10000服务毫秒一个周期，输入 `min(3, 6-stock, 12-generated)`；满容量周期跳过且不欠发。总额外输入最多12，包含已预约未采的自然存量最多6。周期、实际输入、issuedWood、不可变事件和账本原子提交。生产不会发到个人库存。

每个已知operator最多一份 queued/active；预约量3，成功事务序号FIFO。记Q为queued数、R为active未采数、N为自然存量、B为未输入预算，只有 `3Q+R+3 <= N+B` 才接纳新请求。到期/取消释放未采资格；已采库存不回收。重新申请使用新命令且到队尾。授予时固定剩余3和截止时间 `grantedAt+60000`，部分采集不续期，`serviceMs>=expiresAt` 到期。推进先按时间顺序处理到期和生产，再以实际事务当前服务时间授予，不能用历史生产周期回填新租期；授予只能占用当前未预约的3木材。

## 请求和观察

沿用 `/v1/worlds/foundation-01/commands`、Bearer和必填 `World-Instance-Id`；支持显式 `actor-state-v1`。所有动作冻结原commandId和参数；幂等回执优先查询。新增动作：

```json
{"type":"reserve_material","sourceId":"wood-source-east"}
{"type":"cancel_reservation","reservationId":"m..."}
{"type":"harvest_material","reservationId":"m..."}
```

reserve只入队，后台/下次写事务授予；返回固定reservationId、queueSequence和queued状态。cancel/harvest只允许原申请actor，别名不能代领。harvest一次1，实际距离<=1.6且完整线段可通行，库存<12；绑定自己的active原预约，不用池总余量证明本次采集。回执包括预约remaining前后、inventory前后、sourceId、quantity=1和位置。到期或取消后的旧未执行采集明确拒绝，不自动换预约；已提交原命令仍返回旧成功事实。

观察增加 `materialAccess`：version/sourceId/position/buildExclusion，active开关、serviceMs、nextProductionAtMs、generatedWood/inputBudget/stockWood/freeWood，reservationQuantity/leaseMs/productionIntervalMs/capacity，当前组唯一有效 `currentReservation`、本人最近20份 `recentReservations`、全队列 `queue`，以及固定声明名册 `controlRoster` 与 `controlBasis=declared-local-fixture`。预约含reservationId、actorId、operatorId、requestCommandId、queueSequence、status、requestedAtMs、grantedAtMs、expiresAtMs、remaining。队列与当前资格以本次观察为准，旧reserve回执不冒充当前active状态。

resourceAudit增加initialWood=12、generatedWood、sourceWood；wildWood继续指四棵旧树。守恒式 `12+generated = wildWood+sourceWood+inventoryWood+embodiedWood`，issuedWood=12+generated。环境事件actorId/commandId为null，生产、授予、到期分别写业务版本；时钟心跳自身不增加业务版本。授予/到期不改变个人库存，不伪造本人动作。harvest为本人成功动作，沿用本人后续动作失效规则。

拒绝码包括 `MATERIAL_SOURCE_INACTIVE`、`MATERIAL_SOURCE_NOT_FOUND`、`RESERVATION_ALREADY_ACTIVE`、`SOURCE_BUDGET_EXHAUSTED`、`RESERVATION_NOT_FOUND`、`RESERVATION_NOT_ACTIVE`、`INVENTORY_CAPACITY_EXCEEDED`、`UNREACHABLE`；建造侵入保留地仍是AREA_OCCUPIED。所有业务拒绝保存原回执；503仍为未知结果。原回执查询先于环境推进；新请求事务可能先确认环境生产再拒绝居民动作，mutated=false只表示此居民命令未生效，不承诺整个世界快照不变。

## 验收边界

同一新候选实例先合法采空、建桥、早期方留6且拒赠，再开启来源；a2真正预约、走到来源、采3、建本人平台，旧桥/6库存/回执保持。另验竞争、别名、部分采集到期、取消、重启无离线补发、总预算/容量、故障原子性、双服务拒绝、空满地块通行及禁止占地。Godot与Python使用正式接口，保留原意图、实例和预算。

这只验证声明人口和有限预算下的创造入口；有限来源耗尽、无桥西岸、隐藏共同控制、长期先发差距、无限人口和世界扩展仍需继续研究。正常真实时钟与任何故障时钟证据分列。

## Python 居民任务

目标显式增加 `materialAccess: {"sourceId":"wood-source-east","quantity":3}`，同一目标必须为 `buildRecipeId=platform.v1`，任务须 `allowMaterialAccess=true`、`allowBuild=true`。原任务规范和实例不可变；不会把别人或同组别名已有的预约接过来。示例见 `tests/fixtures/material-access-platform.json`。

这类任务另需 `budgets.queries`，整数1—5000。第一次观察计入1，此后每次观察、原回执查询、原预约事件查询在发出前累计并保存，失败也计费；恢复不会重置。原有 commands、wood、seconds、modelCalls 上限照常执行。`--fixed-reference` 表示固定选择、真实模型调用0；选择计数不等于调用模型。

任务只申请一次原预约，逐次领3木，建造本人平台后到达并返回。预约取消、到期或原命令业务拒绝后停止；预算耗尽保留未决原请求，不换ID、不自动再排、不补额度。reserve成功需原回执和原 `materialReserved` 事件一致；超出最近20份列表仍按原事件游标查询。采集须校验原预约remaining及本人库存前后，不能以来源存量或当前余额替代。

公开报告分列 `materialReservation`、`materialHarvests`、`materialWoodHarvested` 和独立建造事实，包含累计查询预算。浏览器只检查导入报告的内部一致性，不重新连接世界认证；Godot新r10未决记录为v4，旧r8/r9记录继续原格式与恢复规则。
