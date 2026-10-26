# 活动地点与选择对照契约：ITER-0004

日期：2026-10-25。开工前冻结。延续前轮共同命令、资源、持久任务与原 ID 恢复；只在新隔离场景增加活动，不迁移旧预览世界。

## 世界与活动

新增 `WORLD_SCENARIO=activities-v1`、`rulesVersion=r3`。地形、初始两居民、12 木材、平台与桥配方沿用 passage-v1。新场景使用 schema 3；已有 schema 1/2 数据库继续按原场景运行，不修改其表、历史记录或规则。启动请求场景与持久场景冲突仍失败。新建 foundation/passsage 可继续使用 schema 2。

活动目录只读，服务器提供，数据为：

| id | label | position | description |
|---|---|---|---|
| garden | 静谧花园 | `[1,6]` | 在本岸花园安静散步，适合短途放松，不需过河。 |
| riverwalk | 河岸步道 | `[2,5]` | 沿本岸步道观察河流，适合看水与散步，不需过河。 |
| lookout | 彼岸观景台 | `[6,1]` | 从彼岸看两岸全景，需要跨河；初始须建设两段桥。 |

r3 observation 顶层新增 `activities:[{id,label,position,description}]`，`self.visits:[{activityId,commandId,stateVersion,visitedAtUtc,position}]`，仅自己最近 100 次，按 stateVersion 升序返回。旧场景可返回空目录与空 visits，不要求对旧库读取不存在的表。目录冻结于 r3 定义，不由模型文字决定。

新增公开命令 `action:{type:"visit",activityId:"garden"}`，只在 r3 支持。activityId 严格字符串；拒绝额外字段。只有自己当前坐标恰等于活动位置才能成功，距离不足 `NOT_AT_ACTIVITY`，未知活动 `ACTIVITY_NOT_FOUND`，旧场景 `ACTIVITY_UNAVAILABLE`（422）；无效 JSON 类型仍 400。仍要求 rulesVersion、expectedStateVersion、已认证身份。

成功与 visit 表、事件、版本递增、回执同一事务提交，资源不变。`result:{action:"visit",activityId,position,visitedAtUtc}`；事件 `type:"visited"`，含 activityId 与 position。自己 `visits` 的 commandId 必须与原命令一致。原 ID 重试仅复用回执，不多生成到访。使用新 ID 可以再次到访，但没有奖励、增发或虚拟经济收益。after-commit 等既有故障注入也覆盖 visit。

## 居民任务增量（兼容 ITER-0003）

`run_mission` 的目标可额外带 `activityId`，旧三字段目标照常有效。若带 activityId，必须在当前 observation.activities 中存在且 position==target；首次任何模型选择或行动前校验。精简模型 context 包含公共 activities、候选 description 与 `activityId`；候选 `estimatedCommands` 增加一次 visit。不可行目标仍如实标注，不能改预算。

`facts` 增加 `activityCompleted:false`、`activityVisit:null`；成功后 activityVisit 为 `{activityId,commandId,stateVersion,visitedAtUtc,position}`。绑定任务 spec 含 activityId。旧 state 没有这些字段时兼容补缺，不能重选目标、重置预算或改动旧 completed 事实。旧不带活动目标仍按原规则完成，activityCompleted=false 不影响它。

活动任务：到达目标后先提交 visit，确认后再回原起点；`facts.goalReached` 仍表示曾到坐标。只有本任务自身 visit 的匹配回执或匹配 commandId 的自己 visits 才能结算 activityCompleted；旧到访记录、模型返回 facts 或只站在目标都不能冒充当前任务完成。visit 计一条 commands，不消耗 wood；未决 visit 沿用同一请求与预算，查询错误不丢 pending。completed 必须 goalReached && activityCompleted && returned。允许到达后因预算用尽停在现场且 activityCompleted=false。

固定参考策略 `choose_lowest_cost(context)`：仅从 feasible 候选中按 `(woodRequired,estimatedCommands,id)` 升序选一个，provider.kind=fixed-reference、model=least-cost-v1、usage={}。无可行候选抛出明确异常，不扩大预算。它是忽略语义目的的成本基线，不是通用最优策略，不能据此宣称模型普遍更强。放在 `scripts/activity_choice.py`，不调用外部模型。

兼容说明：持久预算中的 `modelCalls` 沿用前轮一次 choose 的决策槽计数，固定／测试替身同样占一个槽，防止重选。实际外部模型调用在对照中另列 `actualModelCalls`：固定基线为0。页面对固定策略显示“目标选择次数”，不能把此槽误报为外部推理消耗。

报告仍 schemaVersion 1，增量字段兼容旧 viewer；本轮 viewer 显示已核实到访与位置到达的区别，visit 动作中文化。world 报告地图可增 `activities`。旧真实样例继续可导入。人类世界界面展示活动地点与描述，可在当前位置提交 visit，仍经单个 pending 和原 ID 恢复机制。

## 预先冻结的对照

每例各创建两个相同初始 r3 世界，居民 a1 起点 `[1,1]`、无桥、公共木材12。固定基线与 GPT-6 分别运行，不能共享另一方建成的桥；排除新 UUID、会话和时间后比较初始逻辑观察一致。目标顺序固定 garden、riverwalk、lookout。单任务 modelCalls=1、seconds=600；本轮最多4次真实居民模型调用，每例一次，失败不重试也不换账号。

| caseId | objective | commands / wood / allowBuild | 预先期望目标 |
|---|---|---|---|
| panorama | 我想去彼岸观景台看两岸全景，愿意用最多6木材建桥，体验后返回。 | 30 / 6 / true | lookout |
| quiet | 我只想在静谧花园短途安静散步，体验后返回，不领取也不建造。 | 12 / 0 / false | garden |
| constrained | 我优先想看彼岸全景，但不能花木材且最多12条命令；如果不可行，改去静谧花园放松后返回。 | 12 / 0 / false | garden |
| riverside | 我想沿本岸河岸步道看水散步，体验后返回，不去花园也不建造。 | 12 / 0 / false | riverwalk |

结果分别记录：模型／固定类型、所选目标、expectedGoalMatch、实际 activityCompleted 和 returned、任务状态、命令、木材、调用及 token 用量。预期目标匹配是场景定义，不是模型自评；任何失败完整保留。4例只用于有界演示，不能统计显著性或声称广泛泛化。模型若选合法不同目标，执行器应完成实际选择，比较报告标为目的未匹配，不篡改结果。

对照导出：`{schemaVersion:1,kind:"activity-choice-comparison",recordedAtUtc,actualModelCalls,cases:[{id,objective,expectedGoalId,initialEquivalent,runs:[{kind,report,actualModelCalls,error}]}]}`。每例按 fixed-reference、codex-exec 顺序存两次运行，report 为完整居民报告或 null，error 为简明失败原因或 null。历史报告页读取公开 `/reports/activity-comparison.json` 并可切换显示每份任务，不为查看结果调用世界 API 或模型。

## 预先验收

1. 三地点可观察，人类和居民通过同一 visit 命令记录事实；未到场、未知活动、旧规则、越权均不能写入。
2. 重试、并发同 ID、提交后进程退出后只一份到访；世界版本、事件、回执与 visit 行一致，木材账不变。
3. 居民到达不等于体验完成；原 visit pending 恢复、预算不足、spec绑定、旧任务兼容均检查。
4. 4组固定／实际GPT-6对照在等价初始世界运行，结果不挑样本、不隐去失败；公开证据不带凭据。
5. 实际 Chrome 人类到访、错误反馈、丢响应恢复、报告兼容、390px和0 JS异常；原基础／通行／任务回归适当检查。
6. 实现反馈与结果回流，记录修订或当前局限，不要求凑出模型胜利。
