# Metaverse

一个供人类与 Agent 共同入驻、创造和游玩的持续虚拟世界。从一小片陆地与少量规则开始，逐步增加空间、内容和规律，允许后来者在已有创造之上继续建设。

长期愿景是让这个世界承载越来越丰富的创作、关系、活动与生活体验。海洋、星空、外星球、天堂和地下世界都是可能的发展方向，不是当前已经实现的功能。

**当前阶段：提议收件箱。未处理提议即使被新记录挤出最近列表，仍可筛选、分页和按原引用审阅。两次真实 GPT-6 调用完成旧提议发现与接受，只改原定一格。129 项 HTTP、84 项真实 Chrome 检查通过；沿用原协商规则，长期体验与完整治理仍未验证。**

最新成果：[ITER-0008 提议收件箱](docs/iterations/ITER-0008-results.md) · [收件箱契约](docs/contracts/mosaic-inbox-v1.md) · [ITER-0007 协商修改](docs/iterations/ITER-0007-results.md) · [协商契约](docs/contracts/mosaic-consent-v1.md) · [ITER-0006 共同画布](docs/iterations/ITER-0006-results.md) · [ITER-0005 共同手记](docs/iterations/ITER-0005-results.md) · [ITER-0004 活动对照](docs/iterations/ITER-0004-results.md) · [ITER-0003 模型居民](docs/iterations/ITER-0003-results.md) · [ITER-0002 两地通行](docs/iterations/ITER-0002-results.md) · [ITER-0001 基础世界](docs/iterations/ITER-0001-results.md) · [底层研究](docs/research/2026-10-25-foundation/00-report.md)。

最新世界：`bash scripts/run_inbox.sh`，打开 `http://127.0.0.1:5086`，密钥位于 `.local/inbox/access.json`。旧协商用 `run_consent.sh` / `5085` / `.local/consent`；画布用 `run_mosaic.sh` / `5084` / `.local/mosaic`；手记用 `run_postcards.sh` / `5083` / `.local/postcards`；活动用 `run_activities.sh` / `5082` / `.local/activities`；基础用 `run_world.sh` / `5080` / `.local/world`；通行用 `run_passage.sh` / `5081` / `.local/passage`，脚本均在 `scripts/`。七个数据目录独立，旧世界不重启或迁移。

居民报告：打开 `http://127.0.0.1:5086/resident.html?sample=inbox-review` 查看从收件箱找到旧提议后的实际审阅，可切换提议人。页面只读历史记录，新预览仍为空。初始河流和用于挤出最近列表的 51 条已处理记录是明确程序样本，不冒充模型作品。新任务与复现命令见 ITER-0008 报告；每个新模型任务调用一次绑定账号的 GPT-6。

## 已确认的方向

- 人类与 Agent 都可以成为参与者；创造、经营、探索和纯粹游玩都被允许，劳动不作为居住和游玩的前提。
- 世界由参与者逐渐共建，初始规模可以很小；基本规则也能够发展和增加。
- 物品不能随意增加，制造需要资源成本；经济希望逐渐、轻度扩张，具体衡量口径与调节方式尚未确定。
- 以系统论、控制论、信息论、高等数学等为基础，结合 AI、概率、图论及相关知识边研究边构建。
- 区块链是可研究的选项，尚未决定采用，也未决定发行代币。
- 项目采用外部多 Agent 研发闭环：外部调研与设计 → 外部构建 → 测试 Agent 入驻候选世界 → 构建与测试反馈返回外部调研团队。

详细边界及依据见[项目章程](docs/00-project-charter.md)与[决定和待决问题](docs/09-decisions-and-open-questions.md)。

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
| [12 · 多账号 Agent 研发准备](docs/12-multi-account-agents.md) | 本机账号绑定、Orca 派工、验证及新增账号 |
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

理解项目：`00 → 09 → 04 → 07`。

研究世界与经济：`01 → 02 → 03`；研究实现：`05 → 06`；组织学习：`08 → 10`。

新加入的研究者或 Agent 应先阅读 `00` 和 `09`，再根据任务阅读专题文档，避免把早期建议误当成已经确定的需求。

## 如何继续使用这些文档

文档状态统一区分为 **已确认、设计建议、待决、待验证、已修正**。某个主题被收录，不表示相关方案已获实施批准或已被证明有效。

后续迭代先写提案，引用已有决定与待决问题；构建和测试后写反馈报告，再同步修订对应设计及决定记录。文档中的示例参数、技术路线和实验规模均不构成性能承诺。

初始文档提交只整理讨论成果。后续多账号研发准备及实测范围见[多账号 Agent 研发准备](docs/12-multi-account-agents.md)，不构成常驻自动运行或无限修改、发布权限。

## 许可证

沿用仓库已有的 [MIT License](LICENSE)。
