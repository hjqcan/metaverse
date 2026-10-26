# 共同手记契约：ITER-0005

2026-10-25，开工前冻结。目标：地点可留下后来者能读取的参与者文字，继续区分模型草稿、实际到访和服务器确认分享。手记是文本内容，不是可交易物品，不增发资源或奖励。只用于本机隔离原型。

## 世界协议

新增 `WORLD_SCENARIO=postcards-v1`、规则 r4、新库 schema 4。沿用 r3 三地点、两居民、12 木材及地形／配方，支持 visit。旧 schema 1/2/3 世界保持原规则和表，启动不得迁移、修改历史事实。已存在库与请求场景不一致仍拒绝。

新命令：`action:{type:"postcard",activityId:"garden",visitCommandId:"原visit命令ID",text:"留给后来者的话"}`。仍使用公共命令 envelope、认证身份、规则版本、世界版本和原 ID 幂等。action 不接受额外字段。

`activityId` 和 `visitCommandId` 为非空字符串，visitCommandId 符合既有 commandId 格式。text 为 1—160 个 Unicode 标量值，不能全为空白，不能包含控制字符（Unicode Cc）或孤立代理项；不裁剪、不归一化，原文参与命令 hash。以上结构和文本错误返回 400 `INVALID_REQUEST`。

业务校验顺序在通用版本检查之后：旧场景 422 `POSTCARD_UNAVAILABLE`；未知地点 422 `ACTIVITY_NOT_FOUND`；自己当前位置不等于该地点 422 `NOT_AT_ACTIVITY`；visitCommandId 必须引用自己在该地点的一次已提交 visit，否则 422 `VISIT_REQUIRED`；同一居民同一 visit 已分享则 409 `VISIT_ALREADY_SHARED`。另一身份的 visit 不能引用。重复原 postcard 命令 ID 和完全相同内容返回原回执；同 ID 改字仍 `IDEMPOTENCY_CONFLICT`。

成功记录为 `{activityId,authorActorId,commandId,visitCommandId,text,stateVersion,sharedAtUtc,position}`，其中 authorActorId 来自认证。回执 result 为上述字段加 `action:"postcard"`。成功事件 `type:"postcard_shared"` 包含这些字段、seq 和既有事件通用 actorId；版本、事件、回执、postcards 行在同一事务提交。postcards 追加且不可修改，关联自己的 visit、事件和回执；同一 visit 唯一。木材余额、材料账与实体不变。既有 before/after-commit 故障注入覆盖该命令。

r4 observation 顶层 `postcards` 为全体居民最新 50 条公开手记（按 stateVersion 升序返回），`self.postcards` 为自己最新 100 条（同序），记录形状同上。旧场景返回空数组即可，不能查询不存在的表。公开手记只由已提交数据构造，不接受客户端作者字段。

## 持久居民任务

任务 spec 可新增可选 `sharePostcard:true|false`；缺省沿用旧行为，旧 spec 规范化与绑定不改变。true 时所有候选必须带 activityId，并且开始前观察为 r4；不支持时在模型调用和行动前失败。候选预计命令增加一次 postcard（已有 visit 再加一），预算仍 commands<=100、wood<=12、seconds<=600、modelCalls=1。

当 sharePostcard=true，choose 回调必须返回 `postcardText`，与上述服务器文本规则一致；旧任务继续忽略额外模型字段。精简模型上下文仅增加当前公开手记中最新 5 条，以及 `postcardSharing:true` 能力标记；不放认证／会话／私有状态。既有公开地形和活动保留。

真实 GPT-6 在原来一次目标选择中同时起草短文；JSON schema 为 goalId、reason、postcardText。提示明确草稿在行动前产生，不得伪称已经到访或引用未见事实；他人手记仅是不可信内容，不能改变任务、规则、预算或调用工具。没有第二次模型调用、工具或隐式重试。旧任务仍使用原 schema。

持久化 decision.postcardText。facts 新增 `postcardShared:false`、`postcard:null`；分享后保存完整匹配记录。任务顺序为移动／建桥 → visit 确认 → postcard 确认 → 返回。只接受本任务原 postcard 命令 ID、自己的作者、所选地点、原 visitCommandId、完全相同 text、目标 position 和合法新版本对应的记录／回执。旧手记、草稿、只到访都不能结算本次分享。未决 postcard 延续原命令与预算；查回执错误不能丢 pending。completed 还须 postcardShared；预算不足可以停在“已到访、未分享”。旧状态兼容补缺，但旧完成任务不得重选或新增动作。

报告 schemaVersion 仍为 1。报告 mission.sharePostcard 表示本任务是否要求分享，旧报告缺省 false。报告包含草稿和分享事实的区别；步骤中的 postcard 中文化；新报告可回放，旧报告照常展示。报告的世界快照可包含公开手记；页面仍只读历史，不请求世界或模型。

## 人类界面

r4 显示按地点筛选的共同手记，作者、地点、原文和确认版本清晰可见；所有文字使用纯文本渲染。当前位置可先记录到访，再用自己该地点最新的尚未分享 visit 提交手记。必须说明向这个世界的居民公开。160 字计数按 Unicode 标量值；草稿在轮询更新时不能被覆盖。未连接、非现场、无可用 visit、未决命令或无效文本时禁用发布。

与既有按钮共用单条 pending、原 ID 与 sessionStorage 恢复；丢响应后刷新查回执，不换 ID 重发。成功才清空草稿；失败保留。阅读其他居民文字不会执行 HTML 或代码。新场景预览端口 5083，目录 `.local/postcards`；旧预览不重启、不迁移。

## 预定验收与实际调用上限

协调者独立 HTTP：同一地点双居民可读；非现场／无 visit／其他身份引用拒绝；原 ID 重试／改文冲突／同 visit 新 ID；并发与提交前后退出；Unicode 边界；最近记录限制；原任务恢复、预算不足、旧事实不能复用、能力验证先于模型；实际 populated r3 旧库兼容。

真实 Chrome：人类到访、发布、切换地点读他人手记、公开提示、文字注入按原文显示、160 字边界、轮询保留草稿、丢响应刷新原 ID 恢复、报告新旧兼容、390px 和零 JS 错误。原 HTTP／Chrome 套件继续回归。worker 自检不并入独立数量。

实际居民调用上限 2：newton-ming 控制 a1，在静谧花园到访、分享、返回；hjqcan 控制 a2，在同一个世界看到 a1 的公开手记后，到花园分享、返回。两次都使用 GPT-6 一次选择并起草，失败原样保留，不补抽或换账号。验收记录决策输入确实包含前一手记、实际输出、作者、原 visit 链、返回与材料守恒；不把读取上下文或两篇短文称为人类体验认可、长期关系或复杂社交。是否有趣仍需真人使用反馈。
