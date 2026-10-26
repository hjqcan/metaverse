# 原平台地画采用契约复核

2026-10-26。只读审阅[entity-canvas-v1](../../contracts/entity-canvas-v1.md)，SHA-256 `9c1b35a80aabefbde3e9dae0381275b4ca1335a43ce67a35097e1f2dae6b6083`；对照提交`41aa448`的现有实现与[ITER-0025提案](../../iterations/ITER-0025-proposal.md)。未启动世界、服务、模型或测试，未复制运行库；只新增本文，00—17保持。

**结论：契约通过，可据此实现。未发现需要另加机制的规则矛盾。** 新地画与存储12尚未接入，以下是落实既定契约时必须保持的边界，不是已发现的运行缺陷或验收通过结论。

| 复核点 | 结论与实现边界 |
|---|---|
| 权限与先占 | 规则明确按最后作者actorId判断，同operator、平台建造者、blank颜色均不提供覆盖权；明确采用单个平台，不推断完整产权。25格可先占及Q05未决已写明，无需新增配额、审批或强制腾格。 |
| 原修改与当前图 | 原请求／回执、精确edit接口、原事件三方确认，原edit离开最近50条仍可读取；本人后续改画不否定先前成功。成功恢复不能要求当前revision仍等于原base，404重试则仍使用原base／patch。`actor-state-v1`结算须使用原execution的appliedOnStateVersion，不能套旧garden的observed版本＋1。 |
| 材料归因 | 绘制自身不改库存和材料账；`WorldService.Execute`在裁决前正常Advance，生产可另增世界版本、事件及生态账。因此不要求整个操作区间issuedWood静止，也不把正常生产算成画图增发。采用离线且不推进时钟，与运行时正常生产不矛盾。 |
| 存储组合 | r10的合法组合应精确为：10＝无持续政策、无地画；11＝合法持续政策、无地画；12＝合法持续政策＋完整地画。旧桥手记存在时保持，不把它额外设为所有可采用实例的前置条件。半套地画表／缺失采用事实不能当未采用；不以“版本≥11”放行未知组合。 |
| 参数与客户端 | 5×5、6色、1—8格、1.6米、version1及revision＋1前后一致。精确历史接口足以支持本轮，无需再加分页。Godot新pending version5与原记录兼容、同实体图面刷新，Python固定patch／一次明确任务与查询预扣要求一致；r5/r6原canonical与visit规则继续独立。 |

存储接入有四处现成约束须一起处理：`WorldDatabase.ReadScenario`的白名单与场景映射、`Initialize`、计时锁内`ReloadMaterialPolicy`，以及`AdoptContinuousMaterialSource`的“11 iff政策存在”。最后一处在合法12上应识别原政策已采用，不能重建表、重发材料或错误拒绝既有采用。`ContinuousMaterialRules.ReadPolicy`的原结构、字段实际类型及原采用事件校验继续有效，不为支持12放宽这些检查。

目标已按原事实核实：a2命令`8868adbb65484cd2aa34613d90ff7e91`在state680／event681建成`e926486325c2c4e3e924610139ee26711`；原ledger39转入3木。ITER-0024最终快照仍保留同回执、事件、实体。该快照a1_alias＝0木、a2＝9木，故契约选alias先画、a2续画可分别验证零库存与零支出；alias与a1同组，不能称现实独立主体。执行前仍须观察复核，静态可达不是实走。

来源：`WorldDatabase.cs:40/55/146`、`ContinuousMaterials.cs:43/129`、`WorldService.cs:225/453`，现有r5/r6画布与r10手记实现；原快照`.local/qa/20261026-test-agent/continuous-http-20261026T061604041742Z/continued-natural-v2/final-snapshot.json`，SHA-256 `9ab2a9c180995c7ba88e4b0692158a2300d4783acb07a1069d1a1654c1fe0c69`。后续应以实际代码、原世界轨迹和独立验收回看这些边界；本页不要求新增实验主题。
