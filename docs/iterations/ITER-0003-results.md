# ITER-0003：模型居民、持久任务与历史报告

日期：2026-10-25。本机验收完成，采用当前原型实现。运行入口：通行世界的 `/resident.html`，本机为 `http://127.0.0.1:5081/resident.html`。

真实 GPT-6 已完成两次有界任务的目标选择：建设者建桥往返，另一居民复用桥梁只游玩。完整任务、预算与原命令可以跨暂停或进程退出恢复。模型只选择目标；路径、领料、建造和完成判断均由确定性执行器与实际世界响应处理。

## 实际结果

| 实际任务 | 绑定账号 | 模型请求 | 结果 | 命令 | 消耗木材 | 调用数 | 任务总耗时 |
|---|---|---|---|---:|---:|---:|---:|
| 建设者 a1 | newton-ming | gpt-6-astra | 选择彼岸，建两段桥，到达并返回 `[1,1]` | 21 | 6 | 1 | 7.88 秒 |
| 游玩者 a2 | hjqcan | gpt-6-astra | 选择彼岸，复用桥，到达并返回 `[1,2]` | 16 | 0 | 1 | 10.06 秒 |

建设调用的 CLI 用量为输入 11,604、缓存输入 8,960、输出 81 token；游玩调用为输入 11,717、缓存输入 0、输出 80 token。这里记录 CLI 请求模型与完成事件的用量，不声称独立验证服务端内部路由，不换算成费用。任务总耗时包含决策和世界行动。

两次调用均有实际 Codex 完成事件、结构化选择和后续世界行动；没有固定策略冒充模型、失败自动切账号或模型重试。本轮另有一次只读接入探针，总计 3 次真实决策调用，未超过提案的 4 次上限。研发 worker 的对话不计为居民决策调用。

最终 HTTP 审计及停服后的只读 SQLite 核对一致：初始发行 12 = 储备点 6 + 居民库存 0 + 桥梁实体 6。两个居民均到达目标并返回；游玩者全部为移动命令，无领取、无新建设施。

公开记录：[汇总](evidence/ITER-0003/live-results.json)、[建设报告](evidence/ITER-0003/live-builder.json)、[游玩报告](evidence/ITER-0003/live-traveler.json)。核验时间为 2026-10-25 10:33 UTC；这是独立验收世界的历史记录，不是当前预览世界。

## 实现与分工

- `newton-ming` 账号 GPT-6 worker 完成 [`resident_mission.py`](../../scripts/resident_mission.py)：绑定世界、居民和规范化任务，原子保存完整进度，持久命令／材料／时间／模型次数预算，进程互斥，原 ID 查询及恢复。交付成功，协调者 14 项独立 HTTP 检查通过。
- `hjqcan` 账号 GPT-6 worker 完成 [`resident.html`](../../src/World.Server/wwwroot/resident.html)、JS/CSS 与首页入口：理由、事实、用量、预算、位置轨迹、文件导入。交付成功，协调者 8 项真实报告 Chrome 检查通过。
- 协调者完成 [`codex_goal_selector.py`](../../scripts/codex_goal_selector.py)、[`run_resident.py`](../../scripts/run_resident.py)、验收与证据集成。适配器复用现有账号认证，不把世界 token 传给模型；禁用行动工具，单次等待不超过 180 秒，无自动重试。

两个 worker 均已按各自 Dispatch 上报完成、结算并退出，没有待处置的工作终端。任务状态文件不保存 token，公开报告不包含内部绑定、账号凭据或运行 session ID。原 C# 内核、固定策略脚本及原世界 JS/CSS 的 SHA-256 与 ITER-0002 一致；旧世界预览保持运行。

契约与取舍见 [resident-mission-v1](../contracts/resident-mission-v1.md) 和[提案](../proposals/ITER-0003-residents.md)。Codex 非交互结构化输出与配置开关参考已核对的[官方非交互文档](https://learn.chatgpt.com/docs/non-interactive-mode)和[配置文档](https://learn.chatgpt.com/docs/config-file/config-reference)，实际采用以本机 CLI 0.164.0 及成功调用为准。

## 验收与反馈修订

| 验收 | 结果 | 证据边界 |
|---|---:|---|
| 新持久任务 HTTP | 14 / 14 | 真实 C# HTTP、SQLite；模型为显式 `test-double` |
| 真实居民任务 | 2 / 2 | 实际 GPT-6 调用及后续真实世界行动 |
| 报告页面 Chrome | 8 / 8 | 实际导出报告、桌面与 390px；恶意输入另标注 |
| 原世界 Chrome 回归 | 10 / 10 | 原界面、命令、恢复、断线与撤销仍正常 |

HTTP 检查包含：分段暂停、已完成任务重入零新动作、预算跨恢复不重置、已有库存不能绕过消耗上限、非法模型目标、模型失败不重试、输入边界、建桥提交后服务退出、居民收到成功回执后本地结算前退出、身份／spec 绑定、双进程互斥、暂停期间耗时、精简观察与纯游玩、回执查询错误保留原 ID。退出与崩溃用例只针对专用测试进程。

修订一：源审查发现回执 GET 的 400/403 `mutated=false` 可能被误当原命令拒绝。这个标记只能描述查询本身；现仅接受匹配原 ID 的明确拒绝回执。第 14 项使用真实 HTTP 错误路径检查 pending 未丢失，正常恢复后仍共 21 条命令、6 木材；另有 worker 的五种查询故障定向复核。

修订二：页面最初的 token 字段格式与适配器不一致。改为支持实际 `inputTokens/outputTokens/cachedInputTokens`，动作标签对齐 `dx/dy` 和 `recipeId/at`，真实报告 Chrome 验收已检查实际用量与桥坐标。地图明确说明“报告快照上的位置回放”，没有虚构逐步地形。

独立 Chrome 测试的首次执行还发现验收脚本把第一个桥坐标写错为 `(3,3)`；实际建造坐标为 `(4,3)`，页面显示正确。已改为从真实动作记录读取预期坐标后复测 8 / 8。此项是验收脚本错误，不记为产品故障或模型失败。

全部 18 项本轮 Chrome 检查的 pageerror 为 0，报告页面没有 `/v1/` 世界请求。[HTTP 结果](evidence/ITER-0003/api-results.json)、[报告页面结果](evidence/ITER-0003/browser-results.json)、[原界面回归](evidence/ITER-0003/foundation-browser-regression.json)、[桌面截图](evidence/ITER-0003/desktop.png)、[390px 截图](evidence/ITER-0003/mobile.png)已保存。worker 额外局部／合成数据检查不叠加到上述独立验收数量。

## 使用与复现

启动通行世界后打开居民手记，可查看真实建设报告。导入游玩报告可查看零材料往返；导入[暂停](evidence/ITER-0003/test-double-paused.json)和[决策失败](evidence/ITER-0003/test-double-decision-failed.json)记录可查看失败状态，后两份来自 HTTP 用例，使用测试替身。

独立运行一个新任务，会实际调用指定账号并对指定世界行动：

```bash
bash scripts/run_passage.sh
# 另一个终端；账号绑定先按 docs/12-multi-account-agents.md 完成
python3 scripts/run_resident.py --account newton-ming --actor a1 \
  --spec examples/resident/builder.json \
  --state .local/resident-demo/builder.state.json \
  --output .local/resident-demo/builder.report.json --max-steps 4
# 重复同一条命令恢复下一段；去掉 --max-steps 执行至结束或预算耗尽
```

只游玩使用 [`examples/resident/traveler.json`](../../examples/resident/traveler.json)、`--account hjqcan --actor a2` 和独立的 traveler 状态／报告路径；应先有可通行的桥。上述命令默认使用现有 5081 世界，因此已有桥时建设任务可能无需新增桥梁。需要复现本报告初始状态时用 `python3 tests/resident_live.py --builder-account newton-ming --traveler-account hjqcan`，它创建独立世界，实际调用模型两次，结束后关闭。

恢复必须使用相同 state、spec、URL、居民及规则；不要删状态文件来重置预算或丢弃未决命令。时间上限从任务开始计算，包含暂停；已完成任务再次运行只返回历史报告。`--output` 是可分享的报告，`--state` 是执行器状态，两者必须不同。常规验收命令见 [tests/README](../../tests/README.md)。

## 采用范围与下一问题

采用“模型一次选目标 + 确定性执行 + 持久任务 + 事实反馈”的本机原型。两次任务不足以证明模型对复杂目的的泛化、长期活动价值或多人协作质量。当前目的候选和行动种类都很少，没有长期记忆、自由生成技能、多任务共同额度、常驻调度或自动发布。

页面展示报告所载事实，不验证外来文件的真实性，也不读取即时世界状态。回放仅有最终地形与步骤位置；报告没有逐步时间戳和历史地形。下一轮应增加有实际取舍的活动目标并比较模型选择与固定基线，而不是立即扩大自主权限。

本轮未提交、推送或公共发布。源码、测试与公开证据的哈希见 [manifest](evidence/ITER-0003/manifest.json)；原始日志、数据库、私有状态及调用元数据在被忽略的 `.local/iter0003/`，不随公开报告分发。
