# 首版共同接入、表现层与验证建议

检索日期：2026-10-25（Asia/Shanghai）；下列官方页面均已实际打开。状态：研究建议，未实现、未运行实验。

**项目边界。** 已读 AGENTS.md 与 docs/00、09、03、06、07：人类与 Agent 共同参与、制造消耗材料、外部研发与内部测试是确认方向；引擎、接口、权限细节及阈值仍待选择。以下建议回答 Q06—Q09，不新增用户决定。

**表现层取舍。** 建议首轮采用浏览器二维 Canvas、普通 HTML 操作栏及候选 C#/.NET 权威服务；移动采用离散格点。人类点击与 Agent API 使用同一命令处理器，客户端只呈现服务器结果。

| 方案 | 文档事实与本轮判断 |
|---|---|
| 浏览器二维／轻量 3D | [Playwright .NET](https://playwright.dev/dotnet/docs/intro)支持 Linux、多个浏览器引擎及有／无界面测试。建议二维先行，按钮、库存、拒绝原因可直接断言，Canvas 再检查实际点击和截图；轻量 3D 等空间遮挡确实影响任务时再引入，避免首轮增加相机和拾取变量。 |
| Godot C# 桌面 | [官方 C# 文档](https://docs.godotengine.org/en/stable/tutorials/scripting/c_sharp/c_sharp_basics.html)支持 Linux 桌面导出，需 .NET 版编辑器及独立 SDK，内置 C# 编辑支持有限；检索当日仍明确 **Godot 4 C# 不能导出 Web**。建议需桌面 3D 时再做候选，不承诺一套 C# 客户端直接覆盖浏览器。 |
| Unity | [Unity 6.0 要求](https://docs.unity3d.com/6000.0/Documentation/Manual/system-requirements.html)列出 Ubuntu、桌面和驱动条件。建议本轮后置：尚无必须使用其场景工具的任务；编辑器构建、资产导入和图形测试需另设验证链，不能用后端 dotnet 测试通过代替客户端验收。 |

[Godot SceneMultiplayer](https://docs.godotengine.org/en/stable/classes/class_scenemultiplayer.html)明确高层多人协议是实现细节，不面向非 Godot 服务端；因此建议未来 Godot 客户端也走本轮 HTTP 契约，暂不把场景同步作为世界规则。

**身份与额度。** 建议 Actor 持有居民历史、位置、资产；Operator 是认证及授权主体，负责委托、撤销、费用归属和同控制主体归组；Session 绑定操作者、居民、控制器类型、环境、权限、期限及预算。本轮每个 Actor 只允许一个有效写 Session。控制器不能自行声明身份、换 Session 清零预算或扩大权限；服务端按 Operator 总额预留、结算，区分材料额度与推理／工具费用。

测试使用独立身份域、账本、签发密钥和 audience；正式入口拒绝测试凭据及测试资产。研发登录不等于居民权限，凭据留在现有密钥管理中，模型输入、仓库及证据包只保留非秘密引用。撤销必须作用于后续命令及事件读取。

**最小 HTTP 草案。** 前缀 `/v1/worlds/exp01`；全部请求通过 TLS 携带 `Authorization: Bearer TEST_SESSION_TOKEN`（示意，非真实凭据）。服务端查 token 记录得到身份；正文身份不得覆盖绑定，冒充其他 Actor／Operator／Session 返回 403。`schemaVersion` 是接口格式，`rulesVersion` 是规则集，`stateVersion` 是世界提交序号。

`GET /observation` 返回授权视野及自身库存；示例 HTTP 200：

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":12,"commandId":null,"identity":{"source":"serverTokenRecord","operatorId":"opT","actorId":"a1","sessionId":"s1","environment":"test"},"eventCursor":44,"position":[1,1],"visibleCells":[{"position":[2,1],"walkable":true}],"inventory":{"wood":4},"error":null}
```

`POST /commands` 请求；身份来源仍为上述认证头，不接收正文中的身份覆盖。此草案用全局 `expectedStateVersion` 作为前置条件，会使无关居民动作互相冲突；仅作为双居民原型的保守简化，扩大规模时应评估相关对象的 revision，并将观察顺序与并发前置条件分开：

```json
{"schemaVersion":1,"rulesVersion":"r1","commandId":"c01","expectedStateVersion":12,"action":{"type":"move","dx":1,"dy":0}}
```

提交完成才返回 HTTP 200；`GET /commands/c01` 经同一身份鉴权后返回相同结果：

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":13,"commandId":"c01","identity":{"source":"serverTokenRecord","operatorId":"opT","actorId":"a1","sessionId":"s1","environment":"test"},"status":"committed","eventCursor":45,"error":null}
```

统一错误保留同样版本、身份及 commandId 字段；例如 c02 持旧版本请求，HTTP 409：

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":14,"commandId":"c02","identity":{"source":"serverTokenRecord","operatorId":"opT","actorId":"a1","sessionId":"s1","environment":"test"},"status":"rejected","error":{"code":"STALE_STATE","retryable":false,"mutated":false}}
```

401 表示凭据无效（identity 及受保护状态字段为 null）；403 表示越权；409 还区分规则版本错误、同 ID 异载荷；422 表示材料不足／不可达；429 返回 Retry-After。拒绝不改变世界状态。身份、版本、空间、材料及预算检查均在权威服务执行；成功时状态、资源账、命令结果和事件原子提交。首轮动作仅 move、claim、build：移动限相邻一格，领取扣公共储备；建造载荷如 `{"type":"build","recipeId":"platform.v1","at":[2,2]}`，成本由服务器配方决定。

幂等键建议为 `(world, actor, commandId)`，保存规范化载荷摘要及结果至实验归档；先鉴权、查重复，再验新命令版本。同 ID 同内容返回原结果，同 ID 改材料数量返回冲突；未知版本不静默迁移。超时表示结果未知：先查询，404 只表示尚无记录，可原样重发同 ID，不能换 ID 重造物品。旧版本拒绝后重新观察、重新决策才产生新 ID。撤权后的重试仍拒绝，不能借幂等缓存泄露结果。

事件建议先用 `GET /events?after=44&waitSeconds=20` 长轮询；200 返回版本及身份信封，数据如 `{"events":[{"seq":45,"commandId":"c01","stateVersion":13,"type":"moved","position":[2,1]}],"nextCursor":45}`。seq 属于该授权视图，不能用过滤后的全局事件空洞判断丢包。快照与游标一致读取；按 seq 去重、缺口补拉，游标过期返回 410 并重取快照。断线时禁用提交并显示状态，重连先恢复观察再处理未决命令；权限变化使旧游标失效。

[SignalR 官方文档](https://learn.microsoft.com/en-us/aspnet/core/signalr/javascript-client?view=aspnetcore-10.0)说明默认不自动重连，启用后初次连接失败仍需另行处理。即使后续换 SignalR，建议保留上述业务恢复协议；连接恢复本身不能作为命令已落账的证明。

**可复现证据。** 固定策略冻结路径及预算；LLM 探索改变任务组合；对抗测试注入越权、旧版本、重复发送、断线和并发抢料。三类策略在相同快照和限额下比较世界版本，分场景报告失败率及成本，重放不计为独立样本。同模型换角色或换账号不等于独立性；验收器和保留场景由不同责任人控制，构建者不能修改通过标准。

[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)说明结构化输出仍可能包含错误。因此 JSON 合规只证明形状，不能证明有权限、材料足够或目标可达；拒绝、截断和解析失败不提交动作。证据包记录代码／规则／接口／验收器版本、快照及哈希、场景种子、可观察模型输入输出、实际命令、结果、事件和成本；动作重放校验最终状态哈希，重新调用 LLM 属于新实验。发布判断来自程序断言及实际客户端轨迹，不来自模型自评。

**前置实验与通行。** 建议先在 8×8 地图测试两居民、障碍及有限木材。A：浏览器与固定策略分别绕障碍到目标，墙内移动必须拒绝；B：领取有来源的 4 木材，耗 3 建一平台，剩 1；再建失败。建议每条轨迹上限 100 命令、10 分钟，探索另限 20 次模型调用，外部费用上限运行前冻结。

A/B 通过后才在重置初态的隔离副本做通行：两岸隔一格，建造前不能过，耗 3 木搭桥后两居民往返；不需要海洋物理、交易市场或完整 3D。通过条件：所有硬断言成立；重复命令只扣一次、并发不能透支、越权零成功；提交后丢响应及服务重启仍可查原结果；客户端重连后与授权快照一致。附实际 UI 轨迹、账本及失败复现，再完成一次反馈修订和复核。

**待验证。** 本轮仅完成文档取证；接口、持久化原子性、游标保留量、Linux 图形兼容、延迟、体验及长期行为均未实测，不能声称已通过。

**协调者集成补充。** 本专项报告交付后，独立[事务探针](03-experiment-results.md)已有 9 场景结果；它采用 2 单位材料制造 1 物品，与本文平台成本 3 的场景不同，也未验证本文 HTTP／身份／UI 契约。首轮实际构建范围、参数和本机访问方式以 [ITER-0001](../../proposals/ITER-0001-foundation.md) 为准。
