# 居民目标与任务契约：ITER-0003

日期：2026-10-25。开工前约定；世界规则沿用 r1/r2，本轮不改变 C# 内核、资源配方或已有世界数据库。

## 结构与职责

模型只依据精简观察、目标候选、目的和预算，返回一个目标 ID 与简短理由。确定性执行器决定路径、领取与建造，通过既有 HTTP 命令执行；模型没有世界 token，不直接生成命令或修改事实。CLI 适配器复用明确绑定的本机 Codex 账号，限定 GPT-6；每个任务最多一次模型决策，失败不自动改用另一账号或伪称固定策略为模型。

与逐动作自由调用相比，目标选择降低调用数量，也让固定策略成为可比较的执行基线。本轮仍不是无限开放行为或长期自治。

## Python 对接接口

新增 `scripts/resident_mission.py`，对外提供：

```python
run_mission(client, spec, state_path, choose, *, max_steps=None)
```

`client` 沿用 foundation_agent.WorldClient。`choose(context)` 由协调者实现，可调用真实模型或明确标注的测试替身；返回 `{goalId, reason, provider:{kind,model,usage}}`。kind 为 `codex-exec` / `fixed-reference` / `test-double`，usage 可为空对象。`max_steps` 是本次调用主动暂停的命令数，便于逐段演示和恢复测试，不重置整个任务预算。

spec 固定结构：

```json
{
  "missionId":"bridge-visit-001",
  "objective":"优先连通彼岸，让后来者使用桥，完成后返回起点。",
  "goals":[
    {"id":"far-bank","label":"彼岸目标","target":[6,1]},
    {"id":"nearby","label":"本岸探索","target":[1,6]}
  ],
  "allowBuild":true,
  "budgets":{"commands":50,"wood":6,"seconds":600,"modelCalls":1}
}
```

missionId 只允许字母、数字、下划线、短横线，1—64 字符；目的 1—500 字符；候选 1—8 个且 ID 唯一，目标为图内整数坐标。commands 1—100、wood 0—12、seconds 1—600、modelCalls 为 1，布尔不得当整数接受。目标 ID、权限和预算不能由模型扩大。每个任务访问目标后返回启动时位置。

context 包含 purpose/spec、初始自己和公共地图、每个候选所需新增桥段、预计材料与是否在当前预算下可行；禁止 token、认证文件、账号邮箱、用户目录、其他居民私有库存或完整研发上下文。模型可选择不可行候选，执行器应给出 blocked/budget_exhausted 事实反馈，不擅自更换任务目标。

## 持久执行与恢复

- state_path 是该任务持久状态文件；绑定 URL、worldId、actorId、rulesVersion 与规范化 spec。相同路径重入只恢复原任务，spec 或身份不同则拒绝。状态文件不保存 token。
- 全程持久保存原起点、目标、是否到达、已用预算、步骤与未决原命令；不仅在请求失败时保存。原子替换，进程互斥锁避免两个执行器同时使用同一状态文件。
- 首次调用模型前持久计数；结果成功后保存选择。模型中断／超时不自动再调用，不把次数重置为 0；状态为 decision_failed 并输出反馈。
- 每个新命令在发送前持久化并计入 commands。重试原命令不再次计数；回执只结算一次。400/401/503、网络未知与明确业务拒绝区分，结果未知时保留原 ID 并停止新动作；重入先查回执，404 才可原样重发。
- 材料预算指本任务建造实际消耗的木材，累计不超过 wood；领取量只为剩余建造成本补足自身库存，不能靠恢复重置支出。每个新动作前重观察和检查预算。
- `max_steps` 达到时保存 paused。再次调用不再选目标、不重置原起点或累计预算。completed 重入只返回原记录，不再次行动。
- 任务最终成功依赖实际观察曾到目标且回到原起点；模型说法不能把失败或未知改成成功。目标选择和执行期间不自动升级规则或改写世界。

## 报告与浏览器视图

run_mission 返回下面结构；状态实现内部可有额外字段。所有字段可输出成独立 JSON，供 `resident.html` 文件导入查看：

```json
{
  "schemaVersion":1,
  "kind":"resident-mission-report",
  "mission":{"id":"bridge-visit-001","objective":"...","actorId":"a1","worldId":"foundation-01","rulesVersion":"r2","origin":[1,1],"goal":{"id":"far-bank","label":"彼岸目标","target":[6,1]},"status":"completed","reason":"round_trip_verified"},
  "decision":{"goalId":"far-bank","reason":"...","provider":{"kind":"codex-exec","model":"gpt-6-astra","usage":{}}},
  "budget":{"limits":{"commands":50,"wood":6,"seconds":600,"modelCalls":1},"used":{"commands":21,"wood":6,"modelCalls":1,"seconds":1.0}},
  "facts":{"goalReached":true,"returned":true,"startStateVersion":0,"endStateVersion":21,"woodClaimed":6,"createdEntityIds":["e1","e2"],"verifiedAtUtc":"..."},
  "steps":[{"index":1,"commandId":"...","action":{"type":"claim","quantity":6},"reason":"为桥梁补足材料","status":"committed","stateVersion":1,"position":[1,1],"inventoryWood":6}],
  "feedback":{"summary":"已核验到达与返回","issues":[],"suggestions":[]},
  "world":{"width":8,"height":8,"water":[],"blocked":[],"entities":[]}
}
```

未作选择时 goal/decision 为 null；返回位置当前不等于 origin 时 returned 为 false，不能由旧 reached 标记替代。status 为 running/paused/blocked/budget_exhausted/unknown/completed/decision_failed。报告是本地记录，不是即时世界状态；界面必须区分模型理由和规则事实，显示时间、预算、状态、轨迹，并可加载本轮真实运行样例。模型或文件文字用 textContent 等安全渲染，不执行 HTML。允许至多 2 MiB JSON、100 条步骤；错误文件有明确提示，390px 无溢出。

## 预先验收

1. 至少两次真实 GPT-6 决策：建设目标完成两桥往返；只游玩目标使用既有桥、不领取不建造。记录真实模型、耗时和可获得的 token 用量，明确高层选目标、低层固定执行。
2. 明确标注测试替身的负例：非法目标、越预算、模型失败均不会绕过执行器；这些不能计作真实模型测试。
3. 主动分段暂停、进程重启、建造提交后丢响应均保持同一 missionId、目标、原起点和累计预算；completed 重入零新动作；同状态双进程互斥。
4. 材料总账与服务器状态复核；新任务使用独立验收世界，不改变旧预览状态。
5. 实际 Chrome 查看真实报告与步骤、导入失败/暂停报告、恶意文本安全显示、390px、0 JS 错误；原世界界面保持兼容。
6. 至少一次具体反馈修订并复核，保存公开证据和失败原因；不以模型自己的自评替代验收。
