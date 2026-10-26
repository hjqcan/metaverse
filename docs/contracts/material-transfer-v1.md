# material-transfer-v1 · 自愿当面交付木材

2026-10-26。ITER-0020 已采用的候选实现契约；验证结果另列，不把本文件当作验收证据。

## 世界与能力

显式新建 `wilderness-cooperation-v1` / `r9` / SQLite schema 9。出生、连续几何、四棵树共12木材、桥6／平台3及速度沿用 [continuous-world-v1](continuous-world-v1.md)。必须有持久 `worldInstanceId`。旧 r1—r8 不自动迁移，旧回执、世界和 pending 不改写。`npm run start:cooperation` 使用 `.local/cooperation` / 5090；默认入口继续 r8。此候选提供自愿合作能力；拒绝合作时的独立材料入口仍未解决。

观察在 r9 增加：

```json
{"materialTransfer":{"version":1,"resource":"wood","maxQuantity":12,"reach":1.6,"recipientConfirmation":false},"recentTransfers":{"items":[],"limit":20,"truncated":false}}
```

`recentTransfers.items` 是涉及本人的最后20条持久 `woodTransferred` 公开事件，按 seq 升序；`truncated` 表示还有更早记录。完整历史仍从既有 `GET /events?after=0` 分页读取。列表不是全部历史，余额增加本身不证明某笔交付。观察的实例身份与事件的 `(actorId, commandId, seq, stateVersion)` 一起定位原事实。其他居民的完整余额仍不公开。

## 请求、交付与账本

命令保持 schema 1，必须绑定当前实例：

```json
{"schemaVersion":1,"rulesVersion":"r9","commandId":"gift-01","expectedStateVersion":12,"preconditionMode":"actor-state-v1","action":{"type":"transfer","recipientActorId":"a2","resource":"wood","quantity":3}}
```

来源身份只取认证 token；请求不允许指定来源。`recipientActorId` 使用现有 ID 格式，必须存在于同一世界且不是本人。资源只能是 `wood`；q 为1—12整数，不接受 bool、小数、零、负数或未知字段。转出本人现有库存，没有欠款、手续费、交换条件或接收者确认步骤。赠送者主动提交不代表双方同意。

同一 `BEGIN IMMEDIATE` 中读取双方当前位置、库存及当前几何。距离不超过1.6米，双方站点和按既有0.28米角色半径扫掠的完整直线路径均可通行。接收者可在发起人观察后移动／花费；只要交付时条件成立且发起人状态没变，允许交付。服务不自动移动任何居民。

事务同时完成 `sender -= q`、`recipient += q`、一条事件、一条 `inventory:<sender>` → `inventory:<recipient>` 的账和一份发起人回执；版本和游标各增一次，发行量不变。扣款与入账都有条件更新守卫。失败不部分成交。

成功回执 `result` 为 `action=transfer, resource=wood, quantity=q, senderActorId, recipientActorId, inventoryWood`；最后一项为发起人在这次提交后的余额。事件为 `type=woodTransferred, actorId=<sender>, recipientActorId, resource=wood, quantity=q, commandId, seq, stateVersion`。不为接收者伪造命令或私有回执。接收者后来花掉材料不改变这次赠送成功的事实。

## 前置条件与错误

沿用 [actor-state-v1](actor-state-v1.md)。模式缺失仍为严格全局版本比较；新模式只在受保护 r8/r9 显式能力下采用，r9 新增 transfer。已有 pending 不改模式。原样重放先返回持久原回执；同 ID 改收件人、数量、锚点或模式得到 `IDEMPOTENCY_CONFLICT`。

所有本人状态模式动作（walk/gather/build/transfer）在 E 之后遇到以下任一成功事件即 `STALE_ACTOR_STATE`：`actorId == self`，或者 `type == woodTransferred && recipientActorId == self`。之后余额／位置恢复原值也不会取消失效。转入不是接收者的新命令，但会使其旧意图过期；原任务或按住／路线输入按 ITER-0019 停止，不自动换锚点、续跑或清空预算。用户显式新任务／新输入才可继续。

| 条件 | HTTP / code | 持久回执 |
|---|---|---|
| 非法字段、ID、数量或资源 | 400 / INVALID_REQUEST | 否 |
| 请求伪造 actorId 等身份字段 | 403 / IDENTITY_OVERRIDE | 否 |
| 旧世界 transfer 严格模式 | 422 / ACTION_UNAVAILABLE | 是 |
| 旧世界不支持的 transfer 新模式 | 422 / PRECONDITION_MODE_UNAVAILABLE | 是 |
| 自赠 | 422 / SELF_TRANSFER | 是 |
| 收件人不存在 | 404 / RESIDENT_NOT_FOUND | 是 |
| 过远、站点或直线路径有障碍 | 422 / TRANSFER_UNREACHABLE | 是 |
| 发起人库存不足 | 422 / INSUFFICIENT_RESOURCE | 是 |
| 接收库存将超过12 | 422 / RECIPIENT_CAPACITY_EXCEEDED | 是 |

规则、实例、认证、全局／本人版本错误沿用原契约，先于业务条件。合法12木材世界中接收容量拒绝不会由守恒转让自然触发，但服务仍显式检查。接收者拒绝主观合作不是服务端错误码。

## 客户端和恢复

人类入口明确选择收件人、数量后提交。Agent 任务另有 `allowTransfer=true` 和不可由模型改写的目标 `transfer:{recipientActorId,resource,quantity}`；allowBuild／allowGather 不授权赠送。赠送纳入累计木材支出，同时单列 `woodTransferred`，不算建造消耗。收到材料不扩大任务支出预算，不授权替对方消费。

赠送目标的 `target` 是任务冻结的会面点。先规划到该点并返回；每次行动前检查收件人当时仍在该点1.6米内且直线可通行，对方离开则以 `transfer_recipient_not_at_meeting` 停止有界尝试，不自动追逐或修改会面点。任务显式允许采集／建桥时才可为本次赠送及通路补料，所有建造和赠送支出合计受原 wood 上限约束。转让目标不同时带 activityId 或 buildRecipeId。真实转让失败仍由服务器事务裁决；本地规划失败不冒充持久业务拒绝。

报告新增 `mission.allowTransfer`、`facts.transferCompleted`、`facts.woodTransferred` 及 `facts.transfer`。完成记录含原实例、命令、双方 ID、资源、数量、提交版本和动作前后发起人库存；`world.recentTransfers` 保留同一观察的最近事件及截断标记。赠送与后续建造是不同任务、命令和事实。收款本身不提交接收者命令，但先前已产生的 pending 若因此过期，原命令预算不退。

显式 `npm run start:godot:cooperation` 默认使用 `user://cooperation-pending.json`，与原客户端的 `continuous-pending.json` 分开。升级后的客户端识别 r8/r9 原记录；旧二进制与新版共用含 r9 记录的恢复根不在兼容承诺内。已有文件不搬移、清空或降级。自定义 WORLD_CLIENT_STATE 时由调用方保持需要的隔离。

待定命令冻结原实例、发起人、请求及动作前库存／位置。客户端结算必须核对身份、实例、原 ID、规则、执行版本、资源／收件人／q，以及发起人库存精确减 q。缺失或矛盾证据保留 pending。超时、401、5xx 或实例不符不结算；只在原实例查询明确 `COMMAND_NOT_FOUND` 后原样重发。查询／重放不重复计材料或预算。持久业务拒绝经核对后结束尝试；没有材料或可达路径时停止有界任务，不无限等待收件人。

## 验收范围

1. 实际自然采西岸6 → 建桥6 → 采东岸6 → 当面转让3 → a2建平台3；最终自然0、a1库存3、a2库存0、桥6、平台3，总12。实际命令、作品所有者、账本与回执一致。
2. 等价世界拒绝合作对照：a1持6不发送赠送，a2能过桥但无材料建平台；明确保留 C16—C17 缺口。
3. 数量／身份／空间／不足拒绝；原 ID 重放、改参冲突、赠送和建造竞争、跨居民同 ID 不串账。
4. 接收者四类旧意图全部失效；新观察新意图可继续。接收者在交付前移动或消费按当前条件裁决。
5. 扣款中途异常、提交前进程退出、提交后丢响应、同库重启、同 URL 换库；只出现完整转账或完全未变。
6. Godot／Python 实际交付与原 ID 恢复；接收者可看到可追溯入账，再独立建造。损坏证据不结算，输入／任务过期后停止。

每项以隔离 HTTP／SQLite、真实客户端及独立验收记录证明。真实模型调用不是验收前提；不据固定任务测试声称开放式自治或公平经济已经成立。
