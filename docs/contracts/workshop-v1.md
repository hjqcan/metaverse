# 工作台、木工锤与私人储物箱 v1

2026-10-26，ITER-0027 实施契约。采用[研究20](../research/2026-10-26-continuous/20-workbench-and-tools.md)的第一条完整制作链；数值为本轮实验参数，不是用户对完整经济的确认。实现和验收状态见本轮结果，本文不代替结果。

## 采用与兼容

- 原 r10 持续材料世界停服后显式运行 `adopt-workshop --instance <原ID>`。允许原存储11或12；采用后存储13。保留实例、全部居民、木材、生产阶段、建筑、手记、地画、事件与回执；采用只增加能力元数据、配方与一个 `workshopAdopted` 事件，不发放物品。重复采用无变化；未知/部分/不一致存储拒绝启动。原世界不自动采用。
- 观察请求及尚无原回执的命令须带 `World-Capabilities: workshop-v1`。已采用世界缺少该声明返回409 `CLIENT_CAPABILITY_REQUIRED`，包含当前绑定信封和 `requiredCapabilities:["workshop-v1"]`；门禁无业务变更，不保存拒绝回执，新客户端可沿原ID继续查证/原样重试。新客户端可以读取未采用世界。旧客户端保留未决记录，升级后沿原命令查证；原回执/事件查询以及已保存原回执的相同POST重放不要求此头。规则仍为r10，旧动作规范化与旧回执字节不变。
- 新命令必须包含 `capabilityVersion:1`；没有能力时422 `WORKSHOP_UNAVAILABLE`。不认识能力或家具定义的客户端不得把家具当平台、忽略碰撞或自动重发。

## 材料与权限

| 配方 | 定义 | 木材 | 条件与产物 |
|---|---|---:|---|
| `workbench.v1` | `workbench` | 3 | 手工建造，2×1米，公共使用；建造者保留署名 |
| `wooden_mallet.v1` | `wooden_mallet` | 1 | 走到任意已建工作台旁，用本人木材制造本人持久工具 |
| `wooden_chest.v1` | `wooden_chest` | 3 | 明确指定本人木工锤，1×1米，私人箱，容量12木 |

锤不消耗、不增加携带量、不加快来源生产；没有耐久、转让、装备系统。桥和平台仍可手工建造。台主无需在线、批准或提供材料。箱主独享存取；个人携带容量仍为12。存取整数1..12，不能部分完成，不能借别人锤、取别人箱、透支库存或容量。工具中1木与箱内木材分别计入 `toolWood` 和 `storedWood`；`embodiedWood` 仅为包括家具在内的建筑材料。总账为自然+来源+居民+建筑+工具+箱内=发行量=12+实际生产。未增加无限库存、自动化、离线生产或共享输入槽。

## 空间

建造中心距本人≤3.2米，完整占地在陆地且不碰岩石、剩余树、原实体、任一居民半径0.28米或来源保留区 `[27,29]×[9,11]`。工作台半尺寸(1,0.5)，箱(0.5,0.5)，固定方向。家具是实心障碍，正常行走对其AABB加居民圆半径做连续碰撞；不能穿过薄边或中心。

制作/存取要求中心距离≤1.6米，实际居民起点可通行，起点到目标中心的整段须无水面/岩石/剩余树/其他家具障碍。仅本次指定目标家具从交互射段碰撞中排除；正常行走保留它。客户端导航及几何缓存必须纳入家具。创建完成去可达操作侧，不能要求走入家具中心。

## 请求与成功事实

沿用原命令信封、实例头、原ID幂等及 `actor-state-v1`。新增四种严格动作，不修改旧 `build`：

```json
{"type":"build_workshop","capabilityVersion":1,"recipeId":"workbench.v1","at":[26,20],"toolId":null}
{"type":"craft_tool","capabilityVersion":1,"entityId":"e_original_bench","recipeId":"wooden_mallet.v1"}
{"type":"build_workshop","capabilityVersion":1,"recipeId":"wooden_chest.v1","at":[28.5,20],"toolId":"t_own_mallet"}
{"type":"deposit_wood","capabilityVersion":1,"entityId":"e_own_chest","quantity":3}
{"type":"withdraw_wood","capabilityVersion":1,"entityId":"e_own_chest","quantity":3}
```

`toolId` 是建造必填字段：台为null，箱为具体ID；不根据附近工具或库存自动猜选。每次成功为单一事务，扣料、产物/库存、账本、事件、不可变动作明细、回执同时提交。四种动作都使本人的actor-state失效，不影响台主库存或操作状态。失败记录原回执，无部分扣料。

成功回执 `result` 为 `{action:<动作type>,workshopAction:<明细>}`。原事件为 `{seq,stateVersion,actorId,commandId,type:"workshopActionCompleted",workshopAction:<相同明细>}`。事件API对原作者返回完整事件；对其他居民仅返回同一事件的seq/stateVersion/actorId/commandId/type五字段，不返回workshopAction、数量或箱余额，游标保持一致。此规则仅用于新增工作坊事件，不改写旧事件。详情GET `/v1/worlds/foundation-01/workshop/actions/{authorActorId}/{commandId}` 返回绑定信封和 `workshopAction`，只能查询本人记录；他人403 `WORKSHOP_ACCESS_DENIED`，本人未找到404 `WORKSHOP_ACTION_NOT_FOUND`。不接受查询参数。

明细字段全部存在，未适用值为null：

| 字段 | 定义 |
|---|---|
| `capabilityVersion` | 整数1 |
| `authorActorId`, `operatorId`, `commandId` | 原执行身份 |
| `action` | 上述规范化动作对象，包含原目标/配方/数量 |
| `entity` | 原家具完整 `NaturalStructure` 快照；建造为产物，制作/存取为指定目标 |
| `tool` | 制作产物或建箱使用工具完整快照，其余null |
| `quantity` | 实际移动木材数；建造3、制锤1、存取为请求数 |
| `inventoryWoodBefore`, `inventoryWood` | 本人当次前后库存 |
| `storedWoodBefore`, `storedWood` | 存取前后箱内库存；建箱0/0；其余null |
| `position` | 原执行居民位置，两实数 |
| `stateVersion`, `eventCursor`, `completedAtUtc` | 原提交世界版本、事件序号和UTC时间 |

工具快照：`{toolId,definitionId:"wooden_mallet",definitionVersion:1,ownerActorId,embodiedWood:1,workbenchId,commandId,stateVersion,eventCursor}`。实体沿用 `{entityId,definitionId,definitionVersion:1,rulesVersion:"r10",ownerActorId,position,embodiedWood:3}`。后续存取不改变原明细，工具/实体身份不可替换。

语义错误：`WORKSHOP_TARGET_UNAVAILABLE`404、`TOOL_REQUIRED`422、`TOOL_NOT_OWNED`403、`WORKSHOP_ACCESS_DENIED`403、`INSUFFICIENT_RESOURCE`422、`CHEST_CAPACITY_EXCEEDED`422、`INVENTORY_CAPACITY_EXCEEDED`422、`UNREACHABLE`422、`AREA_OCCUPIED`409。无效JSON/字段/配方/版本/数量用原 `INVALID_REQUEST`。已完成原ID必须先返回原回执，再考虑当前距离、库存、权限和阶段。

## 观察

新增 `workshop`：`capability:"workshop-v1"`, `version:1`, `buildReach:3.2`, `interactReach:1.6`, `inventoryCapacity:12`, `chestCapacity:12`, `workbenchAccess:"public"`, `chestAccess:"owner"`，以及 `adoption:{worldInstanceId,stateVersion,eventCursor}`。

`recipes` 为上表三条 `{id,definitionId,woodCost,requiresWorkbench,requiresTool}`（布尔值；台false/false，锤true/false，箱false/true）。`workbenches` 是所有台的实体快照，`tools` 只含本人工具，`chests` 只含本人箱的 `{entity:<实体>,storedWood,capacity:12}`。全局 `entities` 继续公开所有家具位置/形状/署名；接口不提供他人的逐件工具或逐箱余额明细。原顶层两种建造配方不变。资源审计增加工具与箱内汇总，公开汇总仍可能用于推断单箱库存；本轮是访问权限隔离，不承诺完整信息保密。

## Godot与有限任务

Godot提供可见台/箱、选目标、选本人锤、放置预览、实际制锤和数量存取。显示本人库存与工具、箱容量、成本、条件及原结果；交互确认只绑定当前实例和具体目标。未决记录保留动作、原身份、能力与前事实；提交后查原回执、原事件、原明细三者一致才标成功。不能以当前箱库存替代原存取证据。

Python增加 `workshop` 固定任务，按一次明确 `action` 进行前往、执行、查证与可选返程；目标实例、台/工具/箱及建造坐标冻结。四种独立授权：`allowWorkshopBuild`、`allowCraftTool`、`allowDepositWood`、`allowWithdrawWood`；旧 `allowBuild` 不扩大。任务全链可以用上次确认产物ID创建下一次明确任务；不能在重启时换新命令或重选家具。观察、回执、事件、详情和命令均计预算；`task.json`/CLI具体字段以BUILD2接入文档为准。报告分开原动作完成、返程和未知结果，不能把失败存取写成已储存。

## 验收

同一原r10历史显式采用；第一位居民实际花3+1+3木形成台、锤、箱，另测没有本人锤不能建箱。存3离开、同库重启、回来取3并用于建造。另测携带12→存3→携带9/箱3→再实际领3→携带12/箱3，证明用途。后来者用本人采集材料与原台制自己的锤/箱；对照居民另建自己的台完成同链，不把同控制账号称为独立现实主体。

Godot真实交互与Python CLI都完成链路；原命令恢复、断点、并发库存、材料守恒、几何、旧客户端门禁、原pending升级查证分别记录。测试隔离数据/端口，保留小证据后清除一次性副本/构建产物。原台/桥/手记/画面与回执保持，实际生产单列。箱子允许囤积，不能据此关闭C16—C17、容量/空间/长期玩法问题。
