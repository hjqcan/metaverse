# ITER-0004：地点活动与目的选择对照

日期：2026-10-25。本机实现与验收完成，采用当前原型。活动世界为 `http://127.0.0.1:5082`，实际对照记录为 `http://127.0.0.1:5082/resident.html?sample=activities`。

三个固定地点已支持人类与 Agent 到访。到达坐标、服务器确认本次到访、返回起点分别记录；模型的文字理由不能代替世界事实。四组等价初始世界中，真实 GPT-6 选择符合预定目的 4/4，最低成本固定策略 2/4；八次旅程均完成实际到访和返回。59 项 HTTP、36 项真实 Chrome 验收通过。

## 四组实际对照

目的与预算在[活动契约](../contracts/activities-v1.md)及[案例文件](../../examples/activities/cases.json)中预先冻结。每例固定策略与模型使用两个新 r3 世界，起点 `[1,1]`、无桥、公共木材 12；去除实例身份、会话与时间后的初始观察摘要一致。两方共用执行器，不能复用对方建好的桥。

| 目的 / case | 最低成本固定选择 | GPT-6 实际选择 | 目的匹配：固定 / 模型 | 命令数：固定 / 模型 | 木材：固定 / 模型 |
|---|---|---|---|---:|---:|
| 看两岸全景，允许用 6 木材建桥 / panorama | 静谧花园 | 彼岸观景台 | 否 / 是 | 11 / 22 | 0 / 6 |
| 花园短途散步，不领取不建造 / quiet | 静谧花园 | 静谧花园 | 是 / 是 | 11 / 11 | 0 / 0 |
| 优先全景，但零木材、12 命令；不可行则花园 / constrained | 静谧花园 | 静谧花园 | 是 / 是 | 11 / 11 | 0 / 0 |
| 本岸步道看水，不去花园 / riverside | 静谧花园 | 河岸步道 | 否 / 是 | 11 / 11 | 0 / 0 |

八次任务都已完成自己选择的地点，到访行均为 1，随后返回起点。全景模型任务建成两段桥，最终 `12 = 储备 6 + 库存 0 + 实体 6`；其余七个世界 `12 = 储备 12 + 库存 0 + 实体 0`。世界观察、匹配原命令的到访记录与停服后的只读 SQLite 核对一致，外键错误为 0。

固定策略只按可行候选的木材、预计命令数、目标 ID 排序，明确忽略语言目的，因此四次均选花园。目的匹配由预先定义的目标判断，固定策略选错目的仍照常执行并保留报告。这个对照显示了本组目的与成本的差异，不能证明模型一般优于程序策略，也没有统计显著性或泛化结论。

## 真实调用与成本口径

| case | 绑定账号 | 输入 token | 缓存输入 token | 输出 token | 任务总耗时 |
|---|---|---:|---:|---:|---:|
| panorama | newton-ming | 12,056 | 0 | 72 | 8.43 秒 |
| quiet | hjqcan | 12,036 | 0 | 74 | 9.50 秒 |
| constrained | newton-ming | 12,077 | 0 | 81 | 8.56 秒 |
| riverside | hjqcan | 12,040 | 8,960 | 76 | 7.72 秒 |

本轮居民决策实际调用 4 次，达到预定上限；无重试、补抽或隐藏探针。CLI 请求模型为 `gpt-6-astra`，用量来自真实完成事件，不独立断言服务端内部路由，不换算费用。研发 worker 对话与居民目标选择分开计数。上述耗时取报告的任务累计耗时，包含目标选择和世界行动；对照包装器的启动／审计耗时另存于证据，未混用。

固定策略外部模型调用为 0，任务累计耗时约 0.08 秒。为兼容原任务状态，持久预算字段 `modelCalls` 仍表示一次 choose 决策槽，固定策略也占一个槽；实际调用另记 `actualModelCalls=0`，页面将固定策略的槽标为“目标选择次数”。这两个口径不能互换。

完整八份任务报告、选择完成事件、初始摘要和数据库审计均在[对照证据](evidence/ITER-0004/comparison.json)。记录时间为 2026-10-25 11:32 UTC，属于独立验收世界的历史记录。报告页可逐例切换查看，读取历史文件，不重新运行模型或世界。

## 实现与协作

`newton-ming` 的 GPT-6 worker 完成 C# 活动目录、visit 协议与事务：仅新 `activities-v1/r3` 使用 schema 3，到访、事件、版本和回执一起提交，原 ID 重试不会多记一次。已有 schema 1/2 世界仍按原规则工作。到访不消耗材料、不发放奖励；自己最近 100 条记录对当前身份可见。

`hjqcan` 的 GPT-6 worker 完成[居民任务增量](../../scripts/resident_mission.py)与[固定成本选择器](../../scripts/activity_choice.py)。活动目标先验证目录绑定，到达后执行 visit，确认本任务原命令后再返回；预算不足可停在“已到达、未到访”。旧任务、旧报告和未决命令身份继续兼容。

协调者完成活动界面、历史对照视图、独立测试、八次任务运行及证据集成。界面保留单条未决命令与原 ID 恢复；报告将到达、到访、返回分开呈现，缺少一致到访记录的伪完成报告不会显示活动已完成。报告只是历史记录展示，不认证外来文件真实性。

两个 worker 均已按当前 Dispatch 回报完成、结算并退出，运行终端无待处置任务。worker 的 14 组局部 HTTP 自检及 21 项内存测试替身检查只作构建反馈，不叠加到协调者的独立验收数量。工作契约见[提案](../proposals/ITER-0004-activities.md)。

## 验收与修订

| 套件 | 结果 | 证据 |
|---|---:|---|
| 新活动 HTTP | 15 / 15 | [api-results](evidence/ITER-0004/api-results.json) |
| 原基础 HTTP | 17 / 17 | [foundation](evidence/ITER-0004/foundation-http-regression.json) |
| 原通行 HTTP | 13 / 13 | [passage](evidence/ITER-0004/passage-http-regression.json) |
| 原持久任务 HTTP | 14 / 14 | [mission](evidence/ITER-0004/mission-http-regression.json) |
| 新活动与对照 Chrome | 10 / 10 | [browser-results](evidence/ITER-0004/browser-results.json) |
| 原基础 Chrome | 10 / 10 | [foundation](evidence/ITER-0004/foundation-browser-regression.json) |
| 原通行 Chrome | 8 / 8 | [passage](evidence/ITER-0004/passage-browser-regression.json) |
| 原报告 Chrome | 8 / 8 | [report](evidence/ITER-0004/report-browser-regression.json) |

HTTP 使用真实 C# 服务、SQLite 和隔离数据目录，模型选择明确采用固定程序或测试替身，外部调用为 0。新场景覆盖权限、未到场拒绝、重复／并发原 ID、事务提交前后进程退出、原 visit 恢复、旧到访不可代替新任务、目录绑定、旧 r2 兼容和最近 100 条记录。[只有到达的暂停报告](evidence/ITER-0004/test-double-arrival-only.json)来自显式测试替身，不属于真实模型样本。

Chrome 使用实际服务及保存的真实模型报告，验证人类走到花园并到访、真实版本冲突、丢响应后刷新查询原 ID、服务重启、旧报告兼容、缺失到访的伪完成记录和 390px 布局。新增检查 JavaScript 异常为 0，报告页面世界请求为 0；界面测试没有额外模型调用。[世界桌面](evidence/ITER-0004/world-desktop.png)、[世界手机](evidence/ITER-0004/world-mobile.png)、[对照桌面](evidence/ITER-0004/comparison-desktop.png)、[对照手机](evidence/ITER-0004/comparison-mobile.png)均已视觉检查。

本轮首次旧库兼容测试失败于 fixture 导出遗漏：Python `iterdump()` 不含 `PRAGMA user_version`，导致原库表已存在但版本被识别为 0。已为实际 ITER-0003 通行世界导出补回 `user_version=2`，单项和全套重跑通过；[首次失败记录](evidence/ITER-0004/fixture-before-fix.json)保留。未为此修改产品逻辑，不能把验收数据修正计为产品故障修复。

另修正前轮文档命令的账号别名：本机实际绑定为 `newton-ming`，不是缩写 `newton`。初次 worker 启动在查找别名时即被拒绝，没有创建额外 worker；核对后使用原绑定，无认证重绑。ITER-0003 报告中的复现命令同步更正，原始证据和历史 manifest 保持原样。

本轮构建为 0 错误、0 警告，Python 编译、JS 语法和 diff 空白检查通过。SQLite 3.53.4、.NET SDK 10.0.302、实际 Chrome 152.0.7977.82。当前实现与证据哈希见 [manifest](evidence/ITER-0004/manifest.json)。

## 使用与复现

启动独立活动世界：

```bash
bash scripts/run_activities.sh
# 打开 http://127.0.0.1:5082，使用 .local/activities/access.json 中的居民 token
```

本轮已启动该预览并连接 a1，初始版本 0、无桥、公共木材 12。旧基础预览 5080 保持 r1／版本 7；旧通行预览 5081 保持 r2／版本 19、两段桥。此为验收结束时的观察，之后居民操作会改变状态。

运行新的模型任务会实际调用指定账号并对目标世界行动：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5082 --access-file .local/activities/access.json \
  --account newton-ming --actor a1 --spec examples/activities/panorama.json \
  --state .local/activity-demo/panorama.state.json \
  --output .local/activity-demo/panorama.report.json --max-steps 4
```

相同命令恢复下一段，去掉 `--max-steps` 执行到结束或预算用尽。恢复使用相同 state、spec、URL、身份及规则，不删状态重置预算或丢弃原命令；累计时间包含暂停。该命令使用当前预览状态，已有桥时开销会不同。

完整初始对照用 `python3 tests/activity_comparison.py --account-one newton-ming --account-two hjqcan`，会创建八个独立世界并实际调用 GPT-6 四次，结束后关闭服务。普通无模型回归命令与 fixture 来源见 [tests/README](../../tests/README.md)。启动服务和复现检查均保留在本机，没有提交、推送或公共发布。

## 采用范围与下一问题

采用“三个地点 + 独立到访事实 + 一次目标选择 + 原任务恢复 + 对照报告”的本机原型。此处的活动完成只表示服务器记录了到访，尚无持续内容、社交互动或主观体验评价。全部候选都预先给定，具体动作由确定性执行器处理，没有长期记忆、开放式技能、多任务资源池或常驻调度。

下一步应研究地点本身能提供什么可观察的活动内容，以及人类参与是否有价值。对模型选择的进一步评价需要更强的程序基线和未参与设计的目的案例；不能以本轮 4/4 直接扩大自主权限。原始日志、数据库、私有状态与账号调用元数据留在被忽略的 `.local/iter0004/`，公开证据不带访问凭据。
