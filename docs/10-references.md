# 参考资料与证据边界

首轮资料 R01—R13 核对：2026-10-25；新增 R14—R18 核对：2026-10-26（Asia/Shanghai）。

本表汇集本次讨论实际查阅的官方文档、作者项目页与论文。资料支持其中明确描述的机制或实验结果；项目架构、经济规则和路线图仍是本仓库的设计建议。

文档使用 `[R编号](10-references.md#r编号)` 指向这里。未来实现某项能力时，应重新检查对应文档版本、适用产品和接口，不把本表当成依赖锁文件。

## R01

**Minecraft Creator Learning Journey**

来源：Microsoft Learn，Minecraft: Bedrock Edition 创作资料。

链接：<https://learn.microsoft.com/en-us/minecraft/creator/documents/learningjourneyguide?view=minecraft-bedrock-stable>

可支持：资源包、行为包、自定义方块与实体，以及增加玩法的分层创作方式。

不应据此推导：所有自然规律都能任意修改，或平台已经提供本项目需要的统一经济与跨世界治理。

## R02

**Create and publish games and places**

来源：Roblox Creator Hub。

链接：<https://create.roblox.com/docs/production/publishing/publish-games-and-places>

可支持：一个游戏可包含多个地点，每个地点包含环境、对象和脚本；地点之间可以建立转移关系。

不应据此推导：任意创作者世界的物品、规则与经济天然互通。

## R03

**Object permissions**

来源：Second Life 官方知识库。

链接：<https://community.secondlife.com/knowledgebase/english/object-permissions-r57/>

可支持：对象的复制、修改与转让权限可以分别管理。

适用边界：软件权限与完整法律产权并非同一概念；本项目的许可、共同作品和治理制度仍未确定。

## R04

**Securing the client-server boundary**

来源：Roblox Creator Hub。

链接：<https://create.roblox.com/docs/scripting/security/client-server-boundary>

可支持：客户端触发的状态变化，需要服务端校验上下文、权限和输入；共享状态与奖励相关操作尤其需要明确验证。

适用边界：本项目可借鉴验证原则，具体接口与实现并未因此选定 Roblox。

## R05

**MUD — World Introduction**

来源：MUD 官方文档。

链接：<https://mud.dev/world/introduction>

可支持：在存储层上增加世界逻辑与访问控制，通过统一入口检查权限并调用具体系统的架构例子。

适用边界：MUD 是链上应用框架；参考其结构不等于选择全链世界，也不证明公共经济会自然稳定。

## R06

**Monthly Economic Report — April 2025**

来源：EVE Online，2025-05-09 发布。

链接：<https://www.eveonline.com/news/view/monthly-economic-report-april-2025>

可支持：持久游戏经济会分别观察采矿、货币来源、货币周转以及矿物、模块和船只等价格指标。

适用边界：这是特定时期、特定游戏的报告。这里借鉴观测维度，不复制其参数，不把某月变化当成普遍经济规律。

## R07

**Money and Inflation Explained: Feducation Video Series**

来源：Federal Reserve Bank of St. Louis。

链接：<https://www.stlouisfed.org/education/feducation-video-series/money-and-inflation-explained>

可支持：交换方程中货币量、流通速度、价格水平和产出的关系，以及固定其他变量时的教学推演。

适用边界：统计口径必须一致；交换方程本身不足以给出自动发行政策或可靠的短期价格预测。仓库中的单商品数值例是自行设定的教学例子。

## R08

**Oracles**

来源：ethereum.org 开发文档。

链接：<https://ethereum.org/developers/docs/oracles/>

可支持：智能合约使用链外信息需要相应数据机制，并额外面对正确性、可用性和信任问题。

适用边界：把服务器声明写入链，不自动证明链外游戏过程正确。链上验证哪些事实仍需专门设计。

## R09

**ERC-721: Non-Fungible Token Standard**

来源：Ethereum Improvement Proposals。

链接：<https://eips.ethereum.org/EIPS/eip-721>

可支持：非同质化代币的记录、授权与转移接口；可选元数据扩展可以关联 URI。

适用边界：代币标准不保证游戏服务持续、内容文件永久可用、跨世界功能兼容或兑换价格。

## R10

**Generative Agents: Interactive Simulacra of Human Behavior**

作者：Joon Sung Park 等，2023。

论文：<https://arxiv.org/abs/2304.03442>

可支持：在一个小型模拟环境中，将观察、记忆、反思和规划组合，用于居民活动与交互的研究实例。

适用边界：特定规模和设置中的行为实验，不证明完整社会、长期经济或所有参与者偏好都已得到可靠模拟。

## R11

**Voyager: An Open-Ended Embodied Agent with Large Language Models**

作者：Guanzhi Wang 等，2023。

作者项目页：<https://voyager.minedojo.org/>

论文：<https://arxiv.org/abs/2305.16291>

可支持：在 Minecraft 中结合任务生成、可执行技能库与环境反馈积累能力；其方法使用模型调用和程序技能，并不要求基础模型参数微调。

适用边界：现有环境中的 Agent 技能增长，不等于自动生成完整世界引擎或证明无限期自我改进。

## R12

**SIMA 2: A Generalist Embodied Agent for Virtual Worlds**

作者：SIMA team 等，2025。

论文：<https://arxiv.org/abs/2512.04797>

官方介绍：<https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/>

可支持：三维虚拟环境中的目标执行、跨环境泛化，以及通过生成任务和反馈学习技能的研究方向。

适用边界：研究结果不等于可直接接入本项目的稳定公开服务；模型、工具与训练条件需要另行评估。

## R13

**Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents**

作者：Jenny Zhang 等，2025。

论文：<https://arxiv.org/abs/2505.22954>

作者介绍：<https://sakana.ai/dgm/>

可支持：编程 Agent 修改自身应用代码，使用编程评测筛选变化，并保留多个候选演化分支。

适用边界：特定评测中的改进不等于完整元宇宙研发已被解决；应用程序修改也不等于基础模型自行更新权重。

## R14

**One Hour One Life — 官方项目介绍**

来源：作者 Jason Rohrer 的游戏官网；核对日期：2026-10-26。

链接：<https://onehouronelife.com/>

可支持：玩家使用和传承前代工具、建筑，后来角色在不同处境中生活；个人活动成为更长历史的一部分。

适用边界：只使用作者对游戏的介绍，不采用主页玩家评论作为证据。不据此推导永久不清档、无限科技或本项目应采用一小时寿命与育儿机制。

## R15

**Eco — Developer Blog: Upgrade Modules**

来源：Strange Loop Games 官方 Steam 公告，2020-04-28；核对日期：2026-10-26。

文章：<https://store.steampowered.com/news/app/382310/view/2202766622556744200>

可读取正文的官方公告归档：<https://store.steampowered.com/news/posts/?appids=382310&enddate=1588615714&feed=steam_community_announcements>

可支持：该开发博客把效率加成放在工作台升级模块上，使用同一升级设备的不同居民可获得对应改善，包括新玩家。

适用边界：历史开发说明，未核对现行版本全部数值。这里只借鉴收益沉淀在设备中的方式，不采纳其劳动制度，也不把文章列出的后续计划当作已实现能力。

## R16

**Factorio — Research、Blueprint 与 Friday Facts #376: Research and Technology**

来源：Factorio 官方 Wiki 与开发者博客；博客发表于 2023-09-15，本轮核对日期：2026-10-26。

研究：<https://wiki.factorio.com/Research>

蓝图：<https://wiki.factorio.com/Blueprint>

开发者说明：<https://factorio.com/blog/post/fff-376>

可支持：团队具有共享研究状态；实验室研究消耗科技包；蓝图先表示布局，实际建设仍需物品；开发者介绍过基于采集、制造等行为触发技术的设计。

适用边界：并非所有解锁都必须消耗科技包。可借鉴知识、投入和实践分离，不据此采用固定科技树、无限生产率提升或强制所有新人重演前期流程。博客是当时的设计说明，不把其中全部计划当成本项目已验证机制。

## R17

**Screeps — Understanding game loop, time and ticks；How does CPU limit work**

来源：Screeps 官方文档；核对日期：2026-10-26。

世界循环：<https://docs.screeps.com/game-loop.html>

计算预算：<https://docs.screeps.com/cpu-limit.html>

可支持：脚本在持续运行的世界中按 tick 观察、提交动作；规则处理冲突；服务器端执行受 CPU 额度约束，积累额度和单次使用都有上限。

适用边界：借鉴世界执行和现实计算预算分开管理，不直接采用其调度架构、付费制度或具体数值，也不把计算量视为游戏资源和文明进度。

## R18

**Factorio Learning Environment**

作者：Jack Hopkins、Mart Bakler、Akbir Khan；2025-03-06 提交；核对日期：2026-10-26。

论文：<https://arxiv.org/abs/2503.09617v1>

可支持：用 Factorio 中的任务研究长程规划、程序生成与资源优化，区分有限资源任务和开放工厂建设，并报告当时受测模型在复杂自动化上的局限。

适用边界：结论受论文版本、模型与任务条件限制，不外推为 2026 年所有 Agent 的能力上限；也不证明本项目的共享文明、经济或新人体验已经成立。

## 维护方式

后续新增资料应记录原始链接、发表或版本信息、核对日期、支持的具体结论与不支持的推断。重要决定应链接实际依据，不仅列出一个宽泛的产品主页。

研究结论、项目设计建议和实验观察分别记录。外部论文中的数值不能冒充本项目测试结果；资料发生变化时，保留影响分析及修订记录。
