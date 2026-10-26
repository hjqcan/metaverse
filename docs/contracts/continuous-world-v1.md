# 连续自然地图 v1（r8，ITER-0014）

实现位置：`src/World.Server/ContinuousWorld.cs`、`WorldService.cs`、`Protocol.cs`；Godot 客户端在 `clients/godot/`。Python Agent 的导航、采集建桥、原命令恢复与报告见[连续居民契约](continuous-resident-v1.md)。

场景 `wilderness-continuous-v1`，规则 `r8`，存储版本 8；独立预览 `http://127.0.0.1:5089`，数据 `.local/continuous`。旧 r1—r7 数据和接口保留。接口前缀仍为 `/v1/worlds/foundation-01`，身份、命令原 ID、事务回执、资源账本规则沿用原契约。

ITER-0020 的独立 `wilderness-cooperation-v1 / r9 / schema 9` 沿用本文连续地形、初始12木材、移动、采集与建造规则，另增加[材料转让](material-transfer-v1.md)。新世界必须有持久实例身份；旧 r8 不迁移或增加转让能力。客户端按原请求精确匹配 r8/r9 规则，不以支持两个版本代替回执匹配。

## 坐标与观察

- 所有 `position`、建造 `at`、行走 `to` 为有限实数 `[x,z]`，单位米；Godot 对应 `Vector3(x, height, z)`。无格子、无取整、无曼哈顿距离。
- `world`: `{id,scenarioId,width:32,height:24,coordinateSystem:"continuous-xz",bounds:[0,0,32,24]}`。
- `movement`: `{version:1,kind:"continuous",speed:3,radius:0.28,maxStepDistance:0.6,gatherReach:1.6,buildReach:3.2}`。
- `terrain`: `{version:1,river:{polygon:[[x,z],...],centerline:[[x,z],...],halfWidth:1.4},obstacles:[{id,kind:"rock",position:[x,z],radius}]}`。
- `resourceNodes` 保留原 `nodeId/kind/position/initialWood/remainingWood`；存活树的碰撞半径 0.45。四棵资源树共 12 木材，采空后树干碰撞移除。
- `entities` 保留原字段；平台占地 2×2，桥占地 4.8×1.6（沿 X 跨河），中心是 `position`。居民互不阻挡。平台可走。
- r8 不发布旧 `blocked` 格子和 `entryGuide.route`；Agent 从地形和实体规划连续路线。

## 命令

沿用 POST `/commands` 的 `{schemaVersion:1,rulesVersion:"r8",commandId,expectedStateVersion,action}`。

1. `walk`: `{type:"walk",to:[x,z]}`。`to` 是方向目标，服务端从当前位置向它前进；每次最多 0.6 m，按服务端时间补充 3 m/s 的移动额度（上限 0.6 m），不能靠高频请求瞬移。沿途扫掠圆形角色，碰到树木、岩石、河岸或边界便截停。回执 `result:{action:"walk",position:[x,z],blocked:boolean}`；目标超过本次速度额度只截短，不算碰撞。重复原命令只返回原回执、不再移动。过期 `expectedStateVersion` 仍返回 `STALE_STATE`；确认拒绝并重新观察后，可根据当前意图发新命令。
2. `gather`: `{type:"gather",nodeId}`。角色到树中心欧氏距离 ≤1.6 m，每次采 1 木材；保留事务与原命令恢复。
3. `build`: `{type:"build",recipeId,at:[x,z]}`。平台 `platform.v1` 花 3 木材；中心距离 ≤3.2 m，占地须完整处于陆地且不碰树、岩石、既有建筑。桥 `bridge.v1` 花 6 木材，中心 X 须落在 `centerline` 按 Z 线性插值位置（误差 ≤0.08 m）；中心距离 ≤3.2 m，桥面完整跨过河道，无既有建筑重叠。建成后双方可走桥。水面不允许直接行走。
4. r8 的 `move` 被拒绝；不存在隐藏的格子回退。`claim` 仍不可用。

`resourceAudit`、已确认事件与回执仍为事实依据。新建 r8 库采用[世界实例绑定 v1](world-instance-v1.md)：命令及回执查询必须携带原 `World-Instance-Id`，已有库维持明确的 legacy 分支。断线/不明结果保留原 ID 与原请求；只有实例匹配的 `COMMAND_NOT_FOUND` 才允许原样重发。

实现状态与验收结果见 [ITER-0014](../iterations/ITER-0014-results.md)。[ITER-0016](../iterations/ITER-0016-results.md) 为 Godot 增加本地点击绕障建议与桥面通路；服务端仍逐次确认移动，碰撞与未知结果停止原路线。
