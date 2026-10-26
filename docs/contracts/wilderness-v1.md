# 原始开局与树木采集：ITER-0010

2026-10-26，实施前冻结。用户明确“初始是独立散落的野人，玩家自己砍木头等采集资源进行发展”。这是初始文明的确定方向，不再只是可能的题材；后来者仍进入持续世界当前状态，不重置前人的发展。

本次最小实现采用 `wilderness-v1` / `r7` / schema 7。未指定场景的新数据库默认采用它，`npm start` 使用独立的 `.local/wilderness/` 目录；历史 `run_world.sh` 显式选择原 foundation 实验。它是新开世界的当前产品入口，旧 r1—r6 实验世界保持原规则、状态与证据。参数为本轮原型设计，不冒充用户指定：8×8 地图，a1 在 (1,1)、a2 在 (6,6)，均零库存、无现成建筑、无公共木材储备；四处树木位于 (0,1)、(2,5)、(6,2)、(7,6)，各含 3 单位木材，总量12。天然树木与材料库存分开核算。现有河流与岩壁保留为自然障碍，地点仅是林间空地、河岸和对岸林地，不预置花园设施、观景台或创作服务。

动作 `gather`：严格 `{type:"gather",nodeId:string}`，每个已提交动作从指定树木减1、给本人库存加1；必须在上下左右相邻一格，树木尚有余量。由已认证身份决定收获者。活树阻挡通行和建造；采空留下可观察的零余量节点，土地可通行、可搭建。无自动补满或刷新木材，重启不复活。`claim` 在本场景返回 `422 NO_PUBLIC_DEPOT`；旧场景 gather 返回 `422 GATHERING_UNAVAILABLE`。未知节点为 `RESOURCE_NOT_FOUND`，采空为 `RESOURCE_DEPLETED`，距离不符为 `UNREACHABLE`。

采集沿用原事务、规则／世界版本、命令身份、幂等和回执机制。原命令重试只返回原事实；改节点复用 ID 冲突；库存、树木、事件、材料账、世界版本和回执一次提交。来源账户 `wild-wood` 的种子额度12转入库存，再由原建造消耗进入实体；`wildWood + depotWood + inventoryWood + embodiedWood = issuedWood`。失败不扣料，不把未知结果当未提交。

观察仅在 r7 增加 `gathering:{version:1,quantityPerAction:1}` 与 `resourceNodes:[{nodeId,kind:"tree",position,initialWood,remainingWood}]`，depot 保留兼容字段且 `available:false,wood:0`。entryGuide 材料追加 `depotAvailable:false,wildWood`，路径纳入活树阻挡。公开任务上下文只复制允许字段；现有有界任务执行器不会自动采集，缺材料须明确报 `natural_material_collection_required`，不能假称存在公共领料点。人类和固定程序 Agent 使用同一个 gather 接口。

浏览器展示分散出生、树木余量、树旁砍取按钮、收获库存与材料来源，隐藏公共领料及储备标记；地图可选树木，零余量显示树桩。保留原未决命令恢复、身份切换、断线停止、版本冲突与移动端操作。现有平台／桥梁需真实收集材料后建造；本轮闭环是砍树→木材→搭建／造桥，并验证另一居民可使用已建通路。

独立验收包括真实 HTTP／SQLite 与 Chrome：初态、非法领料、距离、余量耗尽、整批事务与进程退出、原 ID 恢复、竞争最后一份、采集后建造、跨岸复用、重启及旧库不变。模型调用预算0。饥饿、工具制造、生态再生、部落制度、动态注册、长期先发差距和完整经济均未在此实现。

后续扩展：2026-10-26 的 [ITER-0013 居民任务](wilderness-resident-v1.md) 在不改变本世界契约的前提下，允许新任务显式设置 `allowGather: true`，由确定性执行器补足建桥材料。旧任务默认仍不自动采集；原先的 `natural_material_collection_required` 行为保留。
