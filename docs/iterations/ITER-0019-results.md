# ITER-0019 · 无关居民动作不再阻断当前任务

2026-10-26。受保护 r8 世界新增显式 `actor-state-v1`：别人行走、采集或建造后，只要本人没有后续成功动作，原请求仍可在当前事务重新校验并执行。同一角色已执行其他动作则拒绝旧意图；Godot 停止原路线和持键连续输入，Python 停止当前有界任务，等待显式新输入或新任务。

## 已采用行为

服务保留全局版本、原实例、原命令 ID、原请求锚点及已有物理／材料规则。新模式记录实际应用版本；采集同时返回事务扣减前余量。Godot v3 恢复记录和 Python 任务冻结模式与提交前事实，先核对原回执及业务事实再结清；缺失或不一致时保留原 pending。建造还须查到真实公共实体。

新模式仅在服务公布可识别能力后选择。旧严格请求的哈希、原始回执及版本语义不变，Godot v2 和旧 Python 任务不会因升级悄悄改模式。旧无实例世界及 r1—r7 不公布该能力、不迁移。完整协议见[动作前置条件契约](../contracts/actor-state-v1.md)。

同一角色冲突后停止只说明该角色已有后续成功动作，不代表人类接管或权限撤销。原目标、累计预算、起点与已完成事实保持；已停止的 Python 任务再次读取为零网络历史读取。

## 作者自测

均为隔离 .NET / SQLite、随机回环端口和实际客户端；真实模型调用0。

| 范围 | 结果 | 证据 |
|---|---|---|
| 服务端新协议、20轮干扰、本人 ABA、最后木材、占地竞争、速度、旧库及进程退出恢复 | 10项通过 | [HTTP结果](evidence/ITER-0019/self-api.json) |
| Godot 真实输入、无关动作、伪回执、同角色停止及旧 v2 恢复 | 6组、43断言通过 | [原生结果](evidence/ITER-0019/self-godot.json) |

Python 与报告页面作者结果见[客户端专项记录](ITER-0019-python-results.md)。完整 Godot 组合[6套、36组、595断言通过](evidence/ITER-0019/godot-regression.json)，包括共享记录、实例恢复、连续输入、点击导航、新模式和居民／设施署名；最后一套为集成方重跑的真实渲染验收。

完整普通回归最终覆盖[238项 HTTP／SQLite、143项 Chrome](evidence/ITER-0019/full-regression.json)。[初次完整运行](evidence/ITER-0019/full-regression-initial.json)有两个旧测试夹具失败；修正后只复跑受影响的5项实例任务和11项协商界面检查，均通过，其余31套沿用同次完整运行。此汇总不是把初次执行改写成一次全绿。

## 独立验收

以下由测试 Agent 使用独立源码／DLL副本、实际 HTTP / SQLite 和 Godot 进程执行，独立于上表作者自测。

- [服务端5组](evidence/ITER-0019/independent-api.json)：20次无关干扰均成功提交；本人 ABA 被拒绝；拒绝本身不消耗角色状态。实际采木建桥后跨岸争抢最后1木，只成功1次；两位居民各持3木争同一占地，只建成1座平台，败方3木保留。各库均核对12木材、账本、事件、回执和外键。
- [旧严格对照](evidence/ITER-0019/independent-contention-strict.json)与[新模式同任务](evidence/ITER-0019/independent-contention-actor.json)：前20次干扰中，旧任务0次提交／20次拒绝，新任务20次提交／0次拒绝；完成相同目标往返分别使用48和28条命令。原目标、起点、累计预算及唯一一次固定选择保留。这是受控干扰对照，不是无限并发吞吐或调度公平性证明。
- [Godot原回执9例](evidence/ITER-0019/independent-godot-receipts.json)与[Python原回执9例](evidence/ITER-0019/independent-python-receipts.json)：合法新模式确认；缺 execution、错模式／锚点／应用版本、分数／布尔版本、错误采前余量和库存均保留原 pending。恢复真实原回执后，每例只有1次 POST、1木材效果。
- [Python最终停止和恢复预检](evidence/ITER-0019/independent-python-stop.json)：23份损坏采集／行走 before 在零网络请求下拒绝，原状态文件不变；合法未提交请求按原 ID／body 恢复。同角色另一控制器先行成功后，当前任务只提交原1条命令即 blocked；再次读取零网络，显式新任务才能继续。
- [Godot最终控制和恢复预检](evidence/ITER-0019/independent-godot-controls.json)：两个实际渲染进程分别点击路线、持续按方向键；同角色冲突确认后等待0.8秒无新动作，明确新输入才继续。14份损坏 before 在0命令查询／提交下保留原文件；有效 v3 原请求只交付1木。把实际 E=1／S=2 的拒绝伪造为 S=0 时保留 pending，真实原拒绝恢复后才结清。

Godot／Python最初的9例回执验收早于最终停止策略修订，不能单独证明停止行为；最终专项补验与源码哈希另行保留。研究方的[6项原生 execution helper 复核](../research/2026-10-26-continuous/evidence/godot-execution-recheck.json)只覆盖纯校验函数，不计作完整 UI／世界验收。

[独立建设闭环](evidence/ITER-0019/independent-construction.json)进一步验证每条命令前均有另一居民真实移动：21条命令全部提交，采3木建成指定平台、到达后返回。丢弃建造回复并轮换会话后，只查询恢复原ID，建造POST和实体均为1；完成后重读零网络。该独立报告通过[9项真实Chrome检查](evidence/ITER-0019/independent-browser.json)，包含伪执行依据拒绝、未知建设、旧报告兼容及390px；JS错误与页面世界请求均为0。

## 保留的初次失败与修订

[API初次结果](evidence/ITER-0019/self-api-initial.json)为9项通过、1项失败：测试将既有占地错误码写成 `OCCUPIED`，产品返回正确的 `AREA_OCCUPIED`；修正断言后完整10项通过。20轮干扰增加明确节拍，避免把循环次数当作经过时间。

Godot 首版 v3 版本检查使用数组成员匹配，JSON 读出的 `3.0` 与整数数组项类型不一致，导致合法记录被误判损坏。改为显式数值比较后，原实例恢复9组全部通过。新增原生套件[初次结果](evidence/ITER-0019/self-godot-initial.json)另有两项 Python 审计脚本错误：对请求字符串再取首字符以及错误的 SQLite 列名；实际 GDScript 停止检查已通过，修复审计后全6组通过。

旧协商界面测试[另一次失败](evidence/ITER-0019/consent-regression-initial.json)停在等待手动查询按钮启用；源码中的重载自动恢复可先结清原 pending，使按钮正确禁用。夹具改为等待原ID的实际 GET200和 committed 回执，再核对仅1次POST、1条review、1次画布变化；[整套11项通过](evidence/ITER-0019/consent-regression.json)，产品 app.js 未修改。

研究审查另发现 before 只检查键存在以及 Godot 对不可能的过去事务拒绝接受过宽；已增加值预检，并限制 S<E 仅允许 `STATE_VERSION_AHEAD`。原发现、修订时间和纯函数证据保留在[构建中审查](../research/2026-10-26-continuous/12-iter0019-implementation-review.md)。

完整 HTTP 回归的[旧实例任务初次失败](evidence/ITER-0019/instance-regression-initial.json)来自旧格式夹具：它在新模式任务上只删实例字段，留下新模式标记，因此在更早的恢复预检被正确拒绝。现改为先生成实际严格模式请求，再去除旧格式没有的字段；不改原请求／原回执，整套[5项复验通过](evidence/ITER-0019/instance-regression.json)，产品代码未改。

[独立来源核对](evidence/ITER-0019/independent-source-audit.json)确认最终 C#、Python、报告脚本及 Godot 产品源码对应已验收快照，测试者自启服务为0。独立实际运行的服务 DLL 是 `de536486...b1dca08`；主目录最后构建为 `a38e8baf...60da5cb`，程序集版本带集成提交 `2d9bbf2`。二进制不同分别记录，不把源码对应写成另一次独立二进制验收。

最终源码、运行二进制、公开证据散列及自启服务清零见[交付清单](evidence/ITER-0019/manifest.json)。私有原始测试库和账号／会话配置不进入 Git。

## 边界

本轮不增加资源、再生、公平排队或材料转让，不解决采空后后来者无法独立建设的问题。事件判据只适用于当前动作；未来若其他居民能改变本人材料或位置，必须先扩大失效范围。非常旧的锚点仍可能扫描长事件区间，本轮没有增加索引或删除历史。

完整居民身份及设施署名另见[ITER-0021](ITER-0021-results.md)。原有持久预览已由负责迁出的协调者停服并保存到主目录私有 `.local/tree-handoff-20261026T031119Z/`，没有重建、重启或迁移世界；这里的功能验收均来自隔离候选世界。
