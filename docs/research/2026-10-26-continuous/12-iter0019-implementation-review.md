# ITER-0019 构建中审查：恢复预检与验收条件

2026-10-26 11:07 CST。针对正在修改的实现，不改变 ITER-0018 已完成结论。本轮未改产品文件、未运行新模式世界、未宣称整体验收通过。以下事项已发送构建方，修订结果需另行核对。

## 1. 提交前事实只检查字段存在，未检查字段值

读取 Orca checkout 的 `scripts/command_preconditions.py`，SHA-256 为 `db7ad9b67375a9cf4c84183f1199e165bd79db308128c2225fd618db23cd1dad`。`saved_mode` 会确认 walkBefore 内存在 position、maxStepDistance，但不验证它们的值。

本机实际执行了一次纯函数调用：合法的新模式绑定、模式一致的原 walk 请求和匹配步骤，配上：

```json
"walkBefore": {"position": null, "maxStepDistance": null}
```

`saved_mode(state)` 返回 `actor-state-v1`，未报损坏；调用前后源文件散列相同。此调用没有 HTTP、服务进程、任务执行或世界修改。

后续 `valid_walk_receipt` 已会拒绝无效点和步长。风险在检查顺序：任务若在回执不存在后重发原请求，可能先执行一个无法根据保存事实确认的动作，随后才保留为未知。本轮没有实际运行这条网络路径，不能把纯函数结果写成已发生世界变更。

建议在保存状态恢复阶段复用既有的有限坐标、正且有界步长、非负整数库存/余量检查，先报告损坏。原事实丢失时不取当前观察填回旧 before，不改原请求。应覆盖“字段缺失”和“字段存在但值损坏”两个不同情况。

## 2. 同居民冲突后的继续策略已经出现分支

Python peer 的当前未提交 diff 增加了 `STALE_ACTOR_STATE` 到自动重新规划的名单。这与 [11 的默认停止建议](11-same-actor-continuation.md)不同；该建议尚未被确认采用，因此不能把这一差异直接报作实现缺陷。

构建方需选择并说明策略，再同步 Godot 与 Python。若允许重决策，必须始终使用原目标授权和累计预算；若停止，明确原拒绝已结清、任务事实保留。当前服务端 actor 事件只说明有新的本人动作，不提供人类接管或撤销授权的证据。

## 3. 两个 API 验收草稿条件

读取主目录当时的 `tests/actor_state_api.py`：

- 同一建造占地竞争的预期为 `OCCUPIED`，当前 `ValidateContinuous` 实际返回 `AREA_OCCUPIED`。建议保留已有错误码并核对测试，避免为了测试改动既有协议。
- 20 轮无关移动干扰测试没有明确节拍，却要求 B 位移大于 0.8 m。当前服务限速上界为初始 0.6 m 加 3 m/s 的实际补充；若循环少于约 0.067 s，正确限速也不保证这个位移。可以加明确的有限节拍，再验证实际进展与速度上界；不能凭固定循环数假设已经过去足够时间。

这些是草稿的静态核对，没有运行作者正在编辑的测试，不把它们当作正式回归失败。建议正式结果同时记录动作进展、经过时间和实际速度约束。

## 需要回收的证据

恢复预检修订后，确认无效 before 在任何请求前拒绝，原状态文件不被悄悄修补；原合法记录仍能恢复已提交/未提交的原 ID。继续策略确定后，按 11 的真实双客户端场景测试。错误码和节拍调整后，再由对应测试作者运行原 API 套件。

本研究保留单写入者边界：只读检查其他人的实现，将问题和复现条件交给构建方；未接管源码修改或重复启动其服务。

## 11:10 CST 复核更新

- 构建方已选择同居民冲突后停止旧路线与当前有界任务，等待显式新输入；该决定已写入正在构建的 `actor-state-v1.md`。它是契约采用事实，尚不能替代真实 Godot/Python 行为验收。
- Python `saved_mode` 已补 before 值校验。研究方用原 null 样本重查，现返回 `ValueError: Original pending command has invalid before facts`；合法 `[5,7]` 与 0.6 步长仍通过，两份输入均未改变。[纯函数复核 JSON](evidence/before-facts-recheck.json)记录源码散列 `0bb5d62201bf2eba44a973685b9cc1f8f05a771500e523d88c9aae8206167f55`。没有联网或执行 mission。
- 已读取构建者的原始 API 结果：`.local/iter0019/api/20261026T030453Z-ce0650/results.json` 为 9 项通过、1 项占地错误码断言失败；`20261026T030707Z-6f16e3/results.json` 为修正该断言后的定向 1 项通过。当前测试也已增加 0.02 秒节拍。这里只核对已有证据，不写成研究方独立运行或一次完整 10 项重新通过。
- 新的静态发现已反馈：Godot `command_evidence.execution` 的 rejected 分支当时只比较 `stateVersion == appliedOnStateVersion`。若原 E=42，却给出 S=0 和 `RESOURCE_DEPLETED`，它仍可通过该 helper；Python 和报告 JS 则只允许 `STATE_VERSION_AHEAD` 拒绝出现 S<E。建议对齐条件，避免确认不可能属于原请求的拒绝。尚未执行原生探针，也未确认该项修订完成。

## 11:13 CST 原生校验模块复核

构建者已补 Godot 的未来锚点条件。研究方复制该模块到独立的最小 Godot 项目，经 import 后用实际 Godot 4.7.2 无头进程执行 [GDScript 探针](probes/godot-execution-evidence.gd)，[Python 入口](probes/godot-execution-evidence.py)记录退出码和源文件散列。6 项全部通过，原生进程退出码 0。

检查覆盖：普通合法拒绝、`STATE_VERSION_AHEAD` 的未来锚点拒绝、未来锚点伪装成 `RESOURCE_DEPLETED` 必须拒绝、有效并发成功、错误提交版本、错误原观察回显。全部输入经过 Godot JSON 序列化与解析，使用真实数字表示。受测模块 SHA-256 为 `c9af838ed90f05b7870a5da2a6b35986fa5149a2b448794e44b7697f01ffcdd3`，运行期间源文件未变化。

[结果 JSON](evidence/godot-execution-recheck.json)对应 `.local/research/godot-execution-evidence/20261026T031253Z-1d3121/`。这里只执行真实引擎中的纯校验函数，没有启动 World.Server、连接居民、运行完整 world_client 或渲染交互；世界命令与模型调用均为 0。该具体校验缺口已有运行复核，整轮客户端验收仍另行完成。

## 11:15 CST 第四批冻结前证据回收

保留以上原始发现、失败与修订时间。本节更新截至冻结时的事实，不把历史草稿差异当作仍未修复的最终缺陷，也不替协调者宣布整个迭代完成。

| 证据来源 | 已读取的原始结果 | 结果与范围 |
|---|---|---|
| 服务端作者 | `.local/iter0019/api/20261026T031117Z-33babe/results.json` | 完整 10 项通过，包括修正后的占地错误码与带节拍的 20 轮进展测试；结果中的 Protocol、WorldService 和测试脚本散列均与读取时源码一致。服务端提交为 `6e1eb5b`。这次才是完整重跑，不覆盖或删除先前的 9 过 1 失败记录。 |
| 独立测试方 | `.local/qa/20261026-test-agent/actor-state-http-20261026T030722772547Z/results.json` | protocol、recovery、upgrade、materials、occupancy 五组通过；各组记录材料总量 12 且服务进程已停止。包括旧回执原字节、提交前后故障恢复、最后木材与占地竞争。受测 DLL 散列为 `de5364860d1b2b8805f3f6ec836008aa4e09ddbb1f7dfa522a8faf355b1dca08`。 |
| Godot 作者 | `.local/iter0019/godot/20261026T031307Z-a4a278/results.json` | 6 组、43 个断言通过；包含旧路线与持键停止、显式新输入、伪回执保留、损坏 before 预检及旧严格记录。研究方未重新执行该套件；该 JSON 未记录整套源文件散列，不据此宣称所有最终提交已独立验收。 |
| 独立测试方，Python | `.local/qa/20261026-test-agent/actor-client-python-20261026T031259497037Z/resume-policy-results.json` | 3 组通过。gather 的 13 个、walk 的 10 个损坏 before 样本均零网络拒绝，原文件保持不变；各自合法原记录最终只提交一次。同居民冲突停止原任务，累计命令保持 1，历史重读零网络，显式新任务可执行。 |
| 研究方自身 | 本文链接的 before-facts 与 godot-execution 复核 JSON | 原 null 样本与合法对照的 Python 纯函数复核；Godot 实际引擎中的 6 项 execution 校验。没有运行完整 mission 或客户端网络路径，不与上面套件重复计为一次独立整体验收。 |

独立 Python 结果对应 Orca checkout 的 `resident_mission.py` 散列 `96efd9d87c870d5c336213abba7f77edb2a866684d10f8234e0d4ffaa6df404a` 与 `command_preconditions.py` 散列 `0bb5d62201bf2eba44a973685b9cc1f8f05a771500e523d88c9aae8206167f55`；两者均在本次读取时匹配该 checkout。主目录的 Python 集成仍由其拥有者与协调者处理，不把另一个目录的成功报告冒充主目录已完成。

本批只冻结 09–12 与已有配套探针、研究方结果；不新增机制，不修改 00–08 的三批冻结内容，不接管产品源码或 Git 索引。转让仍是草案。协调者可按 `frozen-batch-04.json` 的显式文件清单收取本批，研究方不再改写这些文件。
