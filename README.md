# Metaverse

一个供人类与 Agent 共同入驻、创造和游玩的持续虚拟世界。从一小片陆地与少量规则开始，逐步增加空间、内容和规律。文明随居民的实际进度发展，后来者进入的是当时的世界，并在已有成果之上生活与创造。

长期愿景是让这个世界承载越来越丰富的创作、关系、活动与生活体验。海洋、星空、外星球、天堂和地下世界都是可能的发展方向，不是当前已经实现的功能。

**当前阶段：Godot 3D 俯视、连续自然地图与原始采集。居民分散在河流两岸，空手出生，没有现成建筑或公共木材。木材先存在于树木中，砍取后进入个人库存，再用于搭建和造桥。已建成果会保留，后来者进入同一个持续世界。**

客户端路线已确认：先 Godot 原型，后续迁移 Unreal。启动服务后运行 `npm run start:godot`，进入实际3D场景；运行要求、操作和迁移边界见[Godot客户端](clients/godot/README.md)。世界状态仍由现有服务维护。

最新成果：[ITER-0027 工作台、木工锤与持久储物](docs/iterations/ITER-0027-results.md) · [工作坊契约](docs/contracts/workshop-v1.md) · [ITER-0026 查看近期创作](docs/iterations/ITER-0026-results.md) · [ITER-0025 原平台共同地画](docs/iterations/ITER-0025-results.md) · [地画契约](docs/contracts/entity-canvas-v1.md) · [ITER-0024 原世界持续材料](docs/iterations/ITER-0024-results.md) · [持续来源契约](docs/contracts/continuous-material-source-v1.md) · [ITER-0023 旧桥共同手记](docs/iterations/ITER-0023-results.md) · [手记契约](docs/contracts/entity-notes-v1.md) · [ITER-0022 有界材料入口](docs/iterations/ITER-0022-results.md) · [材料来源与预约契约](docs/contracts/material-access-v1.md) · [ITER-0020 自愿赠送与合作建设](docs/iterations/ITER-0020-results.md) · [材料转让契约](docs/contracts/material-transfer-v1.md) · [ITER-0019 无关居民动作与原任务恢复](docs/iterations/ITER-0019-results.md) · [动作前置条件契约](docs/contracts/actor-state-v1.md) · [ITER-0021 居民身份与设施署名](docs/iterations/ITER-0021-results.md) · [ITER-0018 世界实例与原命令恢复](docs/iterations/ITER-0018-results.md) · [实例契约](docs/contracts/world-instance-v1.md) · [ITER-0016 点击绕障与过桥](docs/iterations/ITER-0016-results.md) · [ITER-0017 指定设施建设](docs/iterations/ITER-0017-results.md) · [ITER-0015 连续居民任务](docs/iterations/ITER-0015-results.md) · [ITER-0013 原始采集任务](docs/iterations/ITER-0013-results.md) · [ITER-0014 连续自然地图](docs/iterations/ITER-0014-results.md) · [连续坐标契约](docs/contracts/continuous-world-v1.md) · [ITER-0011 Godot俯视客户端](docs/iterations/ITER-0011-results.md) · [ITER-0010 原始开局](docs/iterations/ITER-0010-results.md) · [采集契约](docs/contracts/wilderness-v1.md) · [ITER-0009 入驻导览](docs/iterations/ITER-0009-results.md) · [导览契约](docs/contracts/entry-guide-v1.md) · [ITER-0008 提议收件箱](docs/iterations/ITER-0008-results.md) · [收件箱契约](docs/contracts/mosaic-inbox-v1.md) · [ITER-0007 协商修改](docs/iterations/ITER-0007-results.md) · [协商契约](docs/contracts/mosaic-consent-v1.md) · [ITER-0006 共同画布](docs/iterations/ITER-0006-results.md) · [ITER-0005 共同手记](docs/iterations/ITER-0005-results.md) · [ITER-0004 活动对照](docs/iterations/ITER-0004-results.md) · [ITER-0003 模型居民](docs/iterations/ITER-0003-results.md) · [ITER-0002 两地通行](docs/iterations/ITER-0002-results.md) · [ITER-0001 基础世界](docs/iterations/ITER-0001-results.md) · [底层研究](docs/research/2026-10-25-foundation/00-report.md)。

当前入口：先 `npm start`（`bash scripts/run_continuous.sh`），再 `npm run start:godot`。新 r8 预览服务 `http://127.0.0.1:5089`，本机凭据与存档在 `.local/continuous`。32×24 米自然河谷，WASD／点击自由行走，E 采集，1／2 预览并搭平台或整座桥；没有格子取整。当前仍为四棵资源树共12木材的小型原型。旧 r7 预览可以用 `npm run start:wilderness` 启动，数据仍在 `.local/wilderness`；新地图不覆盖旧存档。

Agent 连续任务：`examples/continuous/` 提供绕障短途、采集建桥和后来者复用。使用 `scripts/run_resident.py --fixed-reference` 可零模型调用执行，原命令恢复、预算及完整运行方式见[连续居民契约](docs/contracts/continuous-resident-v1.md)。公开报告可导入 `http://127.0.0.1:5089/resident.html` 查看自然地形和实际轨迹。

自愿合作入口：先 `npm run start:cooperation`，再 `npm run start:godot:cooperation`。独立 r9 服务使用 `http://127.0.0.1:5090` 与 `.local/cooperation`；居民靠近到1.6米内且无遮挡后，可以选择收件人和数量赠送本人木材。接收者可再建自己的平台。可复现任务见[三段合作示例](examples/cooperation/README.md)，协议见[材料转让](docs/contracts/material-transfer-v1.md)。仍只有原始12木材，拒绝合作时后来者的材料入口问题继续存在；既有世界不自动采用新规则。

有界材料入口：[ITER-0022](docs/iterations/ITER-0022-results.md) 的显式 r10 世界提供独立于持有者赠送的材料路径。`npm run start:material-access` 使用5091与 `.local/material-access`，`WORLD_ACTOR=a2 npm run start:godot:material-access` 进入。来源初始关闭，按[运行说明](docs/iterations/ITER-0022-results.md#运行与采用)在停服时对原实例开启一次；随后预约、实际走到东岸来源、逐次领取，再建自己的平台。来源额外总输入上限12，每份预约3；这不是无限供给或长期公平已完成。旧默认r8保持原规则，已有库不迁移。

持续材料：原r10已开启的材料来源可停服后显式采用持续政策，保留原实例、作品、库存和回执；仍须预约并亲自领取。每10服务秒最多3木、容量6，停服不生产。原耗尽世界已实际建成第五个平台并继续生产；采用命令和验证边界见[ITER-0024](docs/iterations/ITER-0024-results.md)。默认及未采用世界不变。

原平台地画：在同一持续材料世界停服登记一座原平台后，可现场绘制5×5、6色图案；Godot显示平台表面、格子作者及本地草图。只能改无人署名格或本人格，不花木材。两位居民已在原平台接绘9格并返回，见[ITER-0025](docs/iterations/ITER-0025-results.md)；有限格子和固定输入不证明长期创作入口或趣味。

查看近期创作：在地画面板选择一次创作，可分别看两位作者原来的5格和4格修改，再返回当前9格作品；灰点代表本次未改。原草图与未决动作保持，查看不产生世界动作。实际鼠标与独立验收见[ITER-0026](docs/iterations/ITER-0026-results.md)，此入口只显示最近50次局部修改。

工作台与工具：显式采用的原r10世界可花3木搭公共工作台，1木制本人木工锤，再花3木搭私人储物箱。原生操作已完成存入、同库重启、取出再建，后来者使用原台，另一零木居民另搭台完成同链；箱内最多12木、随身仍最多12木。Godot右侧“工作台与储物”进入，Python有独立授权的固定任务；采用、验收与边界见[ITER-0027](docs/iterations/ITER-0027-results.md)。

公共育林已在原世界完成实际种采：[ITER-0028](docs/iterations/ITER-0028-results.md) 显式采用四个公共林位、独立种源和本人木斧。居民完成两代采收、用木建造，后来者接手到期成熟树再建，第四株保持生长并冷存；原作品与历史保持。规则和双材料账见[林业契约](docs/contracts/forestry-v1.md)。这是固定公共林地的局部实验，未改变默认r8开局，也未实现完整自然生态。

旧桥共同手记：在已有r10世界停服登记原公共桥后，可零木材阅读、发表和引用接写；Godot点桥或“旧桥手记”进入，Python使用显式固定正文任务。每个声明控制组最多2条、合计6条，不重置原材料和作品。采用命令、原任务恢复及验证边界见[ITER-0023](docs/iterations/ITER-0023-results.md)。

指定设施建设：`examples/construction/` 提供平台、指定河段木桥和零材料访问任务。目标固定配方与中心，采集实际材料建成后再到达、返回；原命令与公共实体共同确认建设事实。输入、恢复和三段共建示例见[设施建设契约](docs/contracts/resident-construction-v1.md)。

新建 r8 数据库带持久实例身份。Godot 与 Python 任务恢复绑定原世界，地址被换成新库时保留旧命令；同库迁址可继续原任务。已有无实例库保持 legacy 语义，不自动迁移。受保护 r8 公布新并发能力后，无关居民行动不再使原请求过期；同角色已有后续成功动作时停止旧意图，等待新输入。旧严格请求与恢复记录继续原语义。

2026-10-26 工作树收尾：原5088／5089预览已停服，10份持久世界保全于主目录 `.local/tree-handoff-20261026T031119Z/`，没有重建或迁移。延续原连续世界时，将 `WORLD_DATA_DIR` 和 `WORLD_ACCESS_FILE` 分别指向该目录的 `continuous/` 与 `continuous/access.json`；默认启动路径仍用于自己的 `.local/continuous` 数据。

历史脚本对应 5080—5087，数据目录相互独立，不把旧世界重置成原始开局。旧 `run_world.sh` 显式选择 foundation 实验；服务读取已有数据库时始终沿用原场景。低层服务面对未指定场景的新数据库时，也默认采用原始开局。

此前模型居民报告：打开 `http://127.0.0.1:5088/resident.html?sample=inbox-review` 查看从收件箱找到旧提议后的实际审阅，可切换提议人。页面只读历史记录，新预览仍为空。初始河流和用于挤出最近列表的 51 条已处理记录是明确程序样本，不冒充模型作品。新任务与复现命令见 ITER-0008 报告；每个新模型任务调用一次绑定账号的 GPT-6。

## 已确认的方向

- 先用 Godot 制作3D俯视原型，后续迁移 Unreal；资源与世界事实继续由独立服务管理。
- 人类与 Agent 都可以成为参与者；创造、经营、探索和纯粹游玩都被允许，劳动不作为居住和游玩的前提。
- 世界由参与者逐渐共建，初始规模可以很小；基本规则也能够发展和增加。
- 文明从独立散落的原始居民开始，玩家先自行砍木头等采集资源进行发展，再逐渐形成聚落；随着实际建设与自动化，后入者的生活可能变为城市活动乃至星际旅行，无须每人重复原始阶段。
- 先行者主要获得早期体验与适度的时长优势，不能凭先发形成过大优势或垄断；后来者需要持续存在的参与和创造机会。
- 物品不能随意增加，制造需要资源成本；经济希望逐渐、轻度扩张，具体衡量口径与调节方式尚未确定。
- 以系统论、控制论、信息论、高等数学等为基础，结合 AI、概率、图论及相关知识边研究边构建。
- 区块链是可研究的选项，尚未决定采用，也未决定发行代币。
- 项目采用外部多 Agent 研发闭环：外部调研与设计 → 外部构建 → 测试 Agent 入驻候选世界 → 构建与测试反馈返回外部调研团队。

普通回归：先 `npm ci --prefix tests/browser --ignore-scripts`，再 `npm test`。统一运行构建、全部 HTTP 和真实 Chrome 检查，不含任何真实模型调用；环境要求和单套入口见[验收说明](tests/README.md)。

详细边界及依据见[项目章程](docs/00-project-charter.md)与[决定和待决问题](docs/09-decisions-and-open-questions.md)。

## 文明如何积累

2026-10-26 的新增方向是：前人的建设应改变后来者面对的生活条件。知识、设施、服务、组织与历史可以持续积累；个人刚加入，不会让周围社会重新回到原始状态。

目前建议区分“世界软件支持什么”“居民实际实现什么”“不同居民能使用什么”，并让时代描述依据实际能力。地区差异、知识传播、公共服务和发展节奏的具体机制仍待验证，详见[文明演进](docs/12-civilization-evolution.md)。

相应新增了 `EXP-0002`“从手工建造到共享工坊”：在同一个小世界里，前一批居民建成设施，后一批直接使用并继续创造。ITER-0027已完成公共工作台制锤、建箱及后来者复用的首步；完整工坊运营、订单与长期能力差距实验尚未完成。

进一步确认的约束是：早到不能演变为对后来者的永久控制。具体设计需要同时检查能力差距和资源、技术、设施、通道的可替代性，详见[先发优势与后来者机会](docs/13-entry-and-bounded-advantage.md)。共享工坊实验因此还需测试先行者拒绝服务时的进入路径。

## 研发闭环

```mermaid
flowchart TD
    A["外部调研与设计 Agent"] -->|方案与验收条件| B["外部构建 Agent"]
    B -->|候选版本| C["虚拟世界"]
    D["入驻测试 Agent"] -->|活动与探索| C
    C -->|观察与行动结果| D
    B -->|实现问题与成本| E["反馈与证据"]
    D -->|活动记录与测试结果| E
    E -->|修订依据| A
```

居民在世界内主动提出新想法，可以作为未来补充。它不替代当前确认的外部研发组织方式。

## 文档导航

| 文档 | 解决的问题 |
|---|---|
| [00 · 项目章程](docs/00-project-charter.md) | 项目愿景、确认范围、参与方式与当前阶段 |
| [01 · 世界与规则](docs/01-world-and-rules.md) | 世界如何扩展，规则如何组合、增加和演化 |
| [02 · 经济与资源](docs/02-economy-and-resources.md) | 物资、货币、权益、价格和跨世界交换 |
| [03 · 人类与 Agent 参与](docs/03-human-and-agent-participation.md) | 持久身份、接入方式、权限、预算与参与选择 |
| [04 · Agent 研发闭环](docs/04-agent-rnd-loop.md) | 外部研究、构建和入驻测试怎样协作迭代 |
| [05 · 架构候选](docs/05-architecture-options.md) | 世界内核、状态、规则接口、模拟与技术选型 |
| [06 · 验证与发布](docs/06-validation-and-release.md) | 怎样获得可信证据，并将变化引入持续世界 |
| [07 · 路线与首个实验](docs/07-roadmap-and-first-experiment.md) | 按验证结果推进，首先跑通哪一轮闭环 |
| [08 · 学习与研究地图](docs/08-learning-and-research-map.md) | 数学、系统科学和 AI 如何对应具体建设问题 |
| [09 · 决定和待决问题](docs/09-decisions-and-open-questions.md) | 哪些已经确认，哪些只是建议，哪些仍需决定 |
| [10 · 参考资料](docs/10-references.md) | 讨论中核对的官方文档、论文与适用边界 |
| [11 · 讨论沿革](docs/11-discussion-history.md) | 原始意图、关键澄清、修正与成果覆盖关系 |
| [12 · 文明演进](docs/12-civilization-evolution.md) | 文明怎样由居民推动，自动化怎样改变玩法，后来者怎样承接当代 |
| [13 · 先发优势与后来者机会](docs/13-entry-and-bounded-advantage.md) | 怎样保留适度积累，并防止后来者被资本、资源和权限封锁 |
| [多账号 Agent 研发准备](docs/12-multi-account-agents.md) | 本机账号绑定、Orca 派工、验证及新增账号 |
| [底层实现研究](docs/research/2026-10-25-foundation/00-report.md) | 内核、存储、客户端、共同接口及实测证据 |
| [ITER-0001 · 最小世界](docs/proposals/ITER-0001-foundation.md) | 两名居民、有限资源、建造与恢复的构建范围及验收 |
| [ITER-0001 · 实现与验收](docs/iterations/ITER-0001-results.md) | 运行方法、真实测试结果、截图、修订及剩余边界 |
| [ITER-0002 · 两地通行](docs/iterations/ITER-0002-results.md) | 公共桥梁、固定策略对照、旧库兼容及恢复修订 |
| [ITER-0003 · 模型居民](docs/iterations/ITER-0003-results.md) | 真实目标选择、持久任务、预算、恢复与可核查报告 |
| [ITER-0004 · 地点活动](docs/iterations/ITER-0004-results.md) | 到访事实、四组模型与固定策略对照、人类活动与旧世界兼容 |
| [ITER-0005 · 共同手记](docs/iterations/ITER-0005-results.md) | 公开创作与阅读、两居民实际回应、草稿与分享事实、恢复及兼容 |
| [ITER-0006 · 共同画布](docs/iterations/ITER-0006-results.md) | 可操作视觉共创、两居民接续绘制、原作者与版本、冲突及原任务恢复 |
| [ITER-0007 · 协商修改](docs/iterations/ITER-0007-results.md) | 他人格子先提议、原作者决定、接受／拒绝事实、原子改图与恢复 |
| [ITER-0008 · 提议收件箱](docs/iterations/ITER-0008-results.md) | 完整待办与计数、游标分页、旧提议原引用读取、输入保留及兼容 |
| [迭代提案模板](docs/templates/iteration-proposal.md) | 为一轮研究与构建明确范围、假设和验收 |
| [反馈与实验报告模板](docs/templates/feedback-report.md) | 记录可复现结果并回流到研究团队 |

## 建议阅读顺序

理解项目：`00 → 09 → 12 → 04 → 07`。

研究文明与经济：`12 → 13 → 01 → 02 → 03`；研究实现：`05 → 06`；组织学习：`08 → 10`。

新加入的研究者或 Agent 应先阅读 `00` 和 `09`，再根据任务阅读专题文档，避免把早期建议误当成已经确定的需求。

## 如何继续使用这些文档

文档状态统一区分为 **已确认、设计建议、待决、待验证、已修正**。某个主题被收录，不表示相关方案已获实施批准或已被证明有效。

后续迭代先写提案，引用已有决定与待决问题；构建和测试后写反馈报告，再同步修订对应设计及决定记录。文档中的示例参数、技术路线和实验规模均不构成性能承诺。

初始文档提交只整理讨论成果。后续多账号研发准备及实测范围见[多账号 Agent 研发准备](docs/12-multi-account-agents.md)，不构成常驻自动运行或无限修改、发布权限。

## 许可证

沿用仓库已有的 [MIT License](LICENSE)。
