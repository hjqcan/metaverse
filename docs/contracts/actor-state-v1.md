# 动作前置条件 actor-state-v1（ITER-0019）

契约已固定供本轮构建；实现和运行验收尚待本轮结果确认。仅用于有持久实例身份的 r8 的 walk/gather/build，原 r8 物理规则、全局版本、实例身份、材料总量及旧请求语义不变。

## 能力与请求

受保护 r8 的 observation 增加：

```json
"commandConcurrency": {"version": 1, "supportedModes": ["actor-state-v1"]}
```

客户端只在识别到上述版本及模式、且原实例已经验证时选择新模式。没有可识别能力的新任务使用严格模式；已有任务按保存的选择继续，不重新协商。

请求可增加一个字段 `"preconditionMode":"actor-state-v1"`，其他字段不变。字段缺失表示原严格模式；显式 null、未知值、重复字段按400 `INVALID_REQUEST` 拒绝。缺字段的规范化哈希保持原字节构造；新字段进入新模式的语义哈希。同 ID 改模式、锚点或动作返回 `IDEMPOTENCY_CONFLICT`。客户端不能为兼容旧服务而删字段重发原 ID。

## 事务裁决

执行原有 `BEGIN IMMEDIATE` → 认证 → 实例前置条件 → 原回执查询。匹配原回执先返回其原始 JSON，不能因后续版本或本人动作再变化而重判。

读取当前世界版本 S。严格请求仍要求原观察锚点 E 等于 S。新模式依次要求：

1. 当前是受保护 r8，且动作属于 walk/gather/build；否则持久拒绝422 `PRECONDITION_MODE_UNAVAILABLE`。
2. E 不超过 S；未来锚点持久拒绝409 `STATE_VERSION_AHEAD`。
3. 不存在 `events.world_id=当前世界 AND state_version>E AND event_json.actorId=本人` 的成功事件；否则持久拒绝409 `STALE_ACTOR_STATE`。拒绝回执本身不消耗居民状态。
4. 在同一事务中，按当前本人位置/库存、节点、速度、河道、树岩、桥和实体重新执行现有距离、完整 sweep、材料和占地校验。只有通过才扣料或移动，并提交全局版本 S+1、事件、账本和回执。

锚点为非负整数的要求、规则版本校验和所有实例错误继续原契约。材料最后一份仍只能交付一次；抢先占地后另一个建造必须拒绝且不扣木材。本人走开再回原坐标仍有新事件，旧请求不得重新变为有效。服务不声称按客户端生成时间排序或提供写事务公平调度。

## 新模式回执

仅新模式的持久业务回执增加：

```json
"execution": {
  "preconditionMode": "actor-state-v1",
  "observedStateVersion": 74,
  "appliedOnStateVersion": 75
}
```

`observedStateVersion` 等于原请求 E；`appliedOnStateVersion` 为这次事务实际读取的 S。提交必须满足 S>=E 且回执 `stateVersion=S+1`；拒绝为 `stateVersion=S`，未来锚点拒绝可有 S<E。模式、整数类型、原 ID、actor、rules、实例绑定及明确提交/拒绝状态都必须匹配。查询与重放不得重算 execution。旧严格模式回执不增加这个字段，原始 JSON 和会话身份不变。

新模式 gather 的 result 另加 `remainingWoodBefore`，为事务扣减前节点数量。客户端核对原节点、quantity=1、节点位置、本人原库存+1，以及 `remainingWood=remainingWoodBefore-1>=0`。当前 r8 无再生，故还要求 `remainingWoodBefore<=原观察的节点剩余`。不能把更高版本或任意库存变化当成成功证据。

walk 继续核对冻结起点、原目标线段、最大单步和 blocked 类型。build 继续核对原目标、配方成本、扣后库存、实体 ID 和实际公开实体。execution 缺失、模式不符、锚点不符、应用版本错误或业务事实不符，都保留原 pending。

## 持久客户端

Godot 新模式记录使用 `recordVersion=3`，在原实例/居民/原 body 之外保存提交前事实；旧 v2 和旧 legacy 记录保持严格语义。v3 缺模式或提交前事实按损坏拒绝，不降级。逐命令共享目录、结清标记和跨世界保留继续 ITER-0018 规则。

Python 新任务在 `_state.binding` 保存 `preconditionBindingVersion=1` 和 `preconditionMode`（新模式字符串或严格模式的 null），公开 mission 同步保存 `preconditionMode`。旧任务没有这些字段则保持严格模式。新版标记存在时缺少模式、未知模式或公开/私有模式不一致都拒绝，不能降级。恢复不重置原起点、决定、请求或累计预算；已完成任务继续零网络历史读取。

新模式每条 pending 保留原 body、E、模式和 before 事实；未知结果只能查询或原样重试。原持久拒绝确认后，才可重新观察并用新 ID 提出仍有效的意图，累计命令预算照常计入。新模式公开步骤保存原 `expectedStateVersion` 和已验证的 `execution` 供审计，报告页面不据此发世界请求或暴露协议操作入口。

`STALE_ACTOR_STATE` 采用停止策略：确认原拒绝后结清 pending，Godot 停止原点击路线与当前持键连续意图，Python 停止当前有界任务；保留原预算、起点和已完成事实。只有显式新输入或新任务才继续，不自动以新 ID 重提旧目标。这只说明同居民已有后续成功动作，不等于人类接管或权限撤销。普通严格模式 `STALE_STATE` 的原有策略不变。新版记录的 before 字段须在恢复请求发出前验证类型和值，不从当前观察补旧事实。

## 兼容与验证边界

已有受保护 r8 可由升级服务公布新能力；已有无实例的 r8 及 r1—r7 不公布，不迁移。旧严格请求继续原行为，因此旧客户端的竞争问题没有被隐式修复。

事件查询只扫描锚点后的区间；非常旧且本人未行动的请求可能读较长历史。本轮不自动加索引、不裁剪事件/回执、不改旧 pending 锚点。若未来其他居民能改变本人库存或位置，必须先扩大失效判据或保存受影响居民版本，再允许新动作使用此模式。

必须同时验证真实 HTTP/SQLite、Godot 与 Python 任务的成功和保留原请求行为；研究的只读候选判据、源码构建或单个200响应不代表整轮验收。
