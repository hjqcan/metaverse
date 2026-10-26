# 公共育林与木斧 v1

2026-10-26，ITER-0028 实施契约。采用[研究21](../research/2026-10-26-continuous/21-forestry-bootstrap.md)的具体方案，产品和分项验收见[结果报告](../iterations/ITER-0028-results.md)。本文固定本轮实验规则，不把这些数值升格为用户对长期经济的确认。

## 采用与原历史

仅对已停服、具有持续材料政策和 `workshop-v1` 的原r10存储13显式执行 `adopt-forestry --instance <原实例>`，升级为存储14。地画可有可无，已有地画必须保持。重复采用不新增物资、时间、事件或林位；不允许自动采用、重置原实例或替换旧作品。

同一事务登记 `forestry-v1`、参数、空采种点和四个空林位；初始种库存0、林木0、斧0。采用时沿用原 `material_source.service_ms`，首次产种在采用时刻后60000毫秒。原来源相位、全部木材、原树、工具、箱、作品、原命令和材料账保持。

采用须重新验证五处3×3米保留区不碰原建筑、居民、岩石、河道、尚有木材的原树或原材料来源保留区；不因研究快照曾可用而跳过当前状态。采用后所有新建筑都不得覆盖这些保留区。它们是公共设施占地，不授予私人土地权。

| ID | 中心 `[x,z]` | 固定碰撞半径 | 建筑保留区 |
|---|---|---|---|
| `nursery-west` | `[7,6]` | 0.30 | `[5.5,4.5,8.5,7.5]` |
| `forest-west-north` | `[7,12]` | 种下至整株采完0.45；空位无碰撞 | `[5.5,10.5,8.5,13.5]` |
| `forest-west-south` | `[7,16]` | 同上 | `[5.5,14.5,8.5,17.5]` |
| `forest-east-north` | `[21,7]` | 同上 | `[19.5,5.5,22.5,8.5]` |
| `forest-east-far` | `[29,5]` | 同上 | `[27.5,3.5,30.5,6.5]` |

## 物品、时间与队列

- 本人2木、现场公共工作台制作本人持久木斧 `wooden_axe.v1`，产物 `wooden_axe`，内含2木，不消耗、不转让。原 `wooden_mallet`、`craft_tool`、三项旧工坊配方及其回执不改变。
- 采种点每60000服务毫秒最多产1种，库存容量4。采用时为0；满时跳过该周期，不积欠。被预约的种子仍计在这4份库存内，领取才扣除。
- 种子为独立非负整数库存，没有本轮玩法携带上限，不进箱、不转让。数量仍须是可精确表示和保存的整数，不得溢出；不把种子当木材。
- 一个FIFO育林队列，排序为原入队事件序号。同声明 `operatorId` 最多一份 `queued/preparing/growing/harvesting`；别名合并，不声称该分组等同现实独立人。
- 分配先取已无有效授权的成熟树，再取空林位；同类按上表林位顺序。严格处理队头，不让后到者凭已有种子跳过等待种源的队头。
- 分配空位时，若队头居民本人已有种子，不保留公有种子；否则须同时保留1份未被保留的种库存。无种库存则保持排队。获得空位后90服务秒内领取所保留种子并种下；本人已有种子的授权不能额外领种。
- 分配已有成熟树不需种子，授权60服务秒。新分配从实际授权时刻开始，不按过去某个空位出现时刻倒签。
- 领取种子不延长期限。种前可取消 `queued/preparing`；已领种子仍属领取者。种下或分配成熟树后不取消、不自续；到期按下面规则处理。

每次种植消耗本人1种，生成全新 `plantId`，绑定固定 `plotId`、原种植授权、种植者及原命令。120000服务毫秒后只成熟一次，成熟事务把3份新生态木材发行至该株 `standingWood`。种下立即具有0.45米树干碰撞；成熟不扩大碰撞，树冠只渲染。种植时重新检查实际树干不会覆盖任何居民，且操作者在1.6米内并有可达交互射段。

原种植授权在生长中保持 `growing`，成熟转 `harvesting`；种植者优先权在该株 `maturesAtMs + 60000` 到期。超过期限，原授权成为 `expired`，成熟树和3木保持，交给FIFO下一份新授权。延迟处理可以补记已经到期的成熟与原优先权到期；新分配仍从本次实际服务时间起算。

采收须本人木斧、本人有效授权及原 `plantId`，在1.6米内且交互通路可达。整株原子转移3木并生成1个新繁殖种子；木库存必须≤9，否则整笔拒绝，不能部分领取。完成后该株成为 `harvested`，碰撞消失，授权 `completed`，林位变空；第二轮须显式重新入队，不能自动续种或把旧采收命令改指下一代。

停服不累计时间。观察、身份切换、重试或重启不额外生产。服务延迟只能补记真实累计服务时间内到期的变化；原来源和林业共用同一单调服务时基，但分别记生产事实。

## HTTP动作与完成事实

使用现有认证、实例头、`actor-state-v1`、原命令持久化与事务接口。动作字段必须完整且无额外字段；整数不能用浮点或布尔替代。下列版本均为整数1，不接受未知版本。

```json
{"type":"craft_forestry_tool","capabilityVersion":1,"entityId":"原公共台ID","recipeId":"wooden_axe.v1"}
{"type":"reserve_forest","capabilityVersion":1}
{"type":"cancel_forest_reservation","capabilityVersion":1,"reservationId":"原授权ID"}
{"type":"collect_seed","capabilityVersion":1,"sourceId":"nursery-west","reservationId":"原授权ID"}
{"type":"plant_tree","capabilityVersion":1,"plotId":"forest-west-north","reservationId":"原授权ID"}
{"type":"harvest_tree","capabilityVersion":1,"plantId":"原植株ID","reservationId":"原授权ID","toolId":"本人原木斧ID"}
```

入队成功只证明原入队事实。分配由权威时间推进产生后续事件，不能把原入队回执改写成后来的分配结果。保留种子、实际领取、实际种植、成熟发行与整株采收各有自己的事实，不互相代替。

每个成功动作返回 `result.action` 与 `result.forestryAction`；公共事件的完整本人版本含同一 `forestryAction`。只读 `GET /v1/worlds/{worldId}/forestry/actions/{authorActorId}/{commandId}` 返回原动作记录；只准作者本人读取完整明细。他人事件仅保留原事件身份及类型，不暴露私人库存变化。公开林地观察仍显示种植者、成熟树和当前授权，不能据此宣称完整信息保密。

`forestryAction` 固定字段为：

| 字段 | 原事实 |
|---|---|
| `capabilityVersion/authorActorId/operatorId/commandId/action` | 版本、原身份、完整规范化原动作 |
| `position/serviceMs/stateVersion/eventCursor/completedAtUtc` | 动作发生的坐标、服务时间、版本、事件及UTC记录 |
| `inventoryWoodBefore/inventoryWood/seedsBefore/seeds` | 本人动作前后库存 |
| `nurseryStockBefore/nurseryStock` | 该动作前后采种点库存，不是后续观察的余额 |
| `reservationBefore/reservation` | 本动作前后原授权快照，无则null |
| `plantBefore/plant` | 本动作前后原植株快照，无则null |
| `tool` | 本次产出的木斧或采收所用本人木斧，无则null |

原回执、本人原事件和原明细一致才确认成功。环境事件至少区分 `forestSeedProduced`、`forestReservationGranted`、`forestReservationExpired`、`forestTreeMatured`。成熟记录须绑定原plantId、原种植事实、到期服务时间、3木与唯一原事件。

`World-Capabilities` 须声明 `workshop-v1,forestry-v1`。已采用世界中，缺少林业能力的新观察或新效果返回 `CLIENT_CAPABILITY_REQUIRED`；原已存回执查询与相同原命令重放优先于能力栅栏，保持原字节。新版遇到不认识的林业能力、损坏原pending或异实例，暂停并保留原身份和请求；不能据此清空旧pending或更换plantId。

## 观察结构

`observation.forestry` 包含 `capability:"forestry-v1"`、`version:1`、`adoption`、固定 `policy`、`nursery`、四个 `plots`、当前未采完的 `plants`、所有当前 `reservations`（queued/preparing/growing/harvesting）、本人 `seeds`、本人 `tools` 与唯一木斧配方 `recipes`。原 `workshop` 结构不变。唯一配方条目固定为 `{id:"wooden_axe.v1",definitionId:"wooden_axe",woodCost:2,requiresWorkbench:true}`，不含 `requiresTool`。本人动作事件类型为 `forestryActionCompleted`，字段为 `seq/stateVersion/actorId/commandId/type/forestryAction`。新命令采已采完的旧株返回 `409/FOREST_TREE_NOT_MATURE`，不影响下一代。

- `adoption`：`worldInstanceId/adoptedServiceMs/stateVersion/eventCursor/baseStorageVersion`。
- `policy`：`seedIntervalMs:60000/nurseryCapacity:4/preparationLeaseMs:90000/growthMs:120000/harvestLeaseMs:60000/woodPerTree:3/seedsPerHarvest:1/groupLimit:1/interactReach:1.6`。
- `nursery`：`sourceId/position/radius/buildExclusion/serviceMs/nextProductionAtMs/productionPeriod/generatedSeeds/stockSeeds/reservedSeeds/freeSeeds`。
- `plot`：`plotId/position/radius/buildExclusion`，按上表固定；当前植株通过 `plants[].plotId` 关联。
- `reservation`：`reservationId/actorId/operatorId/commandId/requestedAtMs/queueOrder/status/plotId/plantId/reservedSeed/grantedAtMs/expiresAtMs`。ID与入队事实不可变；未分配时后三个时间/目标可为null，reservedSeed为0或1。`growing.expiresAtMs` 为null，成熟后设为原到期时刻加60000。
- `plant`：`plantId/plotId/planterActorId/operatorId/reservationId/commandId/plantedAtMs/maturesAtMs/state/standingWood/stateVersion/eventCursor/matureEventCursor/harvestActorId/harvestCommandId/harvestEventCursor`。`stateVersion/eventCursor` 固定为种植事实；后续引用无则null；状态为growing/mature/harvested。旧已采植株由不可变动作明细与原事件保留。
- `tool`：`toolId/ownerActorId/workbenchId/commandId/stateVersion/eventCursor/definitionId:"wooden_axe"/definitionVersion:1/embodiedWood:2`。

原树节点仍在 `resourceNodes`；新种植不冒充旧树。新灌木与未采完的树干以 `terrain.obstacles` 中明确的圆形障碍供所有导航使用：灌木 `{id:"nursery-west",kind:"forestry_nursery",position:[7,6],radius:0.3}`；植株 `{id:<原plantId>,kind:"forestry_tree",position:<对应林位中心>,radius:0.45}`。展示须区别原岩石、幼苗、成熟树与空林位。交互只可按完整id从射段中排除正在操作的目标，不得因此忽略沿路其他植株；普通行走不排除任何目标。

## 材料与验收

`resourceAudit.generatedWood` 保持原材料来源产量；增加 `forestGeneratedWood/standingForestWood/forestryToolWood`，`toolWood` 为旧锤与新斧内含木材合计。

`initialWood + generatedWood + forestGeneratedWood = wildWood + sourceWood + inventoryWood + embodiedWood + toolWood + storedWood + standingForestWood`。

独立 `seedAudit`：`nurseryGeneratedSeeds + harvestGeneratedSeeds = nurseryStockSeeds + residentSeeds + consumedPlantSeeds`；另给出 `reservedSeeds`，不再加到等式右边。成熟发行、采收转移分别在各自对应事务中原子登记，不使用观察差额推定来源。

四位使未采木材≤12；每株最短120服务秒，四个独立声明组充分参与时林业长期新增上界6木/分钟，与原来源18相加为24的上界，不是保证产量。当前四个居民只有三个声明组，原自然史正常流程最多同时维持三株，林业上界更紧为4.5木/服务分钟；四位满载只作为规则一般上界，不冒认本轮实测。种子持有不创造新林位。首轮固定公共地不等于自由造林，也不解决外部建筑围路、身体占位、无限人口或现实身份合谋。

验收至少覆盖：原历史显式采用/重启/重复采用；种源0起步与保留/领取区别；FIFO、别名和两种到期；未成熟不可采、整株容量与本人斧；两代plantId和原命令未知结果；种下及成熟前后冷重启；成熟发行只一次；当前几何与旧作品；原生真实输入的两轮种植采收和实际用材；后来者在原种植者不采时经原队列取得公开成熟树。Python每次固定一个动作及原目标，可等待原授权或原植株状态推进，预算累计，不自动续租、另选树或补料。

作者自检、独立协议验证、原生自然活动和模型/算术例子分开报告。只用隔离副本做破坏与故障测试；原自然史沿同一头接续，用完清理一次性数据库、凭据和运行副本。
