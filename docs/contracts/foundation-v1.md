# Foundation HTTP v1（ITER-0001 实现契约）

2026-10-25，协调者冻结的候选契约。用户“继续”授权本轮构建与本机验证；没有远程发布或付费模型调用。场景参数沿用 [ITER-0001](../proposals/ITER-0001-foundation.md)。

## 服务与身份

- 程序：`src/World.Server`，ASP.NET Core net10.0，静态文件位于 `wwwroot/`；同源访问。默认 `http://127.0.0.1:5080`，环境变量 `WORLD_URL` 仅允许 loopback HTTP 地址，`WORLD_DATA_DIR` 默认仓库 `.local/world`（运行脚本明确传绝对路径）。
- 一库一世界 `foundation-01`。启动空目录时创建数据库、初态、会话及 `access.json`，文件权限 0600。重启不得重新发行资源、改变居民身份或复活已撤销会话。
- `access.json` 格式：`{"worldId":"foundation-01","sessions":{"a1":{"token":"随机秘密","sessionId":"s...","expiresAtUtc":"..."},"a2":{...}}}`。token 仅首次写本机文件，不打印日志，不放入仓库。数据库仅保存 token 的 SHA-256。正常有效期 24 小时。
- 首轮用户从本机文件取 a1 token 输入界面；固定居民使用 a2。没有公开的会话签发 HTTP 接口；本机文件读取者是受信任操作者，不把本原型描述成公共账号系统。
- 离线管理命令：`dotnet World.Server.dll issue-session --actor a1 --ttl-seconds 86400 --output <path>`，由同一 `WORLD_DATA_DIR` 指定数据库；替换该居民旧会话，写上述单会话字段 JSON 文件（token/sessionId/expiresAtUtc，0600），不打印 token。支持负 ttl 供过期验收。测试先停服务再使用此命令。
- 全部 `/v1/...` 请求用 `Authorization: Bearer <token>`；认证无效／过期／撤销返回 401。认证绑定 actor、operator、session，命令正文不得覆盖。未知世界返回 404，不回退到默认世界。
- `GET /healthz` 无认证：`{"status":"ok","worldId":"foundation-01","sqliteVersion":"..."}`。
- `DELETE /v1/session` 撤销当前会话，返回 204，后续包括读取、重复命令全部拒绝；这不是世界动作，不增加世界版本。

## 共同信封

所有世界响应的基本形状（失败时缺失的受保护状态为 null；`error` 成功时 null）：

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":0,"commandId":null,"identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s1"},"eventCursor":1,"error":null}
```

全局 stateVersion 初始 0，仅成功世界命令增加 1。初始发行事件 seq=1；每次成功世界动作再产生一个公共事件。全部本世界事件均可被本世界有效居民读取，不包含 token、私有库存快照或原始请求。事件不分页删除，按 seq 排序，单次最多返回 100 条，nextCursor 为最后已返回 seq；空批次保持请求游标。未知未来游标返回 409 `CURSOR_AHEAD`，客户端重取观察。

## 观察

`GET /v1/worlds/foundation-01/observation`：同一读事务读取已提交状态及 eventCursor。第一版地图和居民位置公开，仅返回调用居民的库存。

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":0,"commandId":null,"identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s1"},"eventCursor":1,"error":null,"world":{"id":"foundation-01","width":8,"height":8,"blocked":[[3,0],[3,1],[3,2]],"goal":[5,1]},"self":{"actorId":"a1","position":[1,1],"inventory":{"wood":0}},"residents":[{"actorId":"a1","position":[1,1]},{"actorId":"a2","position":[1,2]}],"depot":{"position":[1,1],"wood":12},"entities":[],"resourceAudit":{"issuedWood":12,"depotWood":12,"inventoryWood":0,"embodiedWood":0,"conserved":true}}
```

平台 entity 格式：`{"entityId":"...","definitionId":"platform","definitionVersion":1,"rulesVersion":"r1","ownerActorId":"a1","position":[2,1],"embodiedWood":3}`。公开 resourceAudit 仅有总量，不能用它返回其他居民的独立库存。

## 命令与查询

`POST /v1/worlds/foundation-01/commands`：

```json
{"schemaVersion":1,"rulesVersion":"r1","commandId":"unique-id","expectedStateVersion":0,"action":{"type":"move","dx":1,"dy":0}}
```

动作仅三种：`{"type":"move","dx":1,"dy":0}`、`{"type":"claim","quantity":4}`、`{"type":"build","recipeId":"platform.v1","at":[2,1]}`。整数严格检查，quantity 1—12；移动 Manhattan 步长恰为 1。坐标、距离、材料、平台占位由服务器校验；允许居民同格。

命令 ID 1—128 个 ASCII 字母、数字、连字符或下划线；世界版本非负整数；结构未知字段返回 400 `INVALID_REQUEST`。载荷若出现身份覆盖字段（actorId/operatorId/sessionId/identity）则返回 403 `IDENTITY_OVERRIDE`。材料价格不由客户端传入。

去重作用域 `(world,actor,commandId)`，规范化语义字段包含接口版本、规则版本、预期状态版本和动作。新旧 JSON 属性顺序不影响同一语义。身份和格式合法后，先查询回执再校验新命令的规则／状态版本；同键异参 409 `IDEMPOTENCY_CONFLICT`，同键同参返回原状态码和结果，不能重复修改。

提交后返回 200；业务拒绝使用相应 409／422，保存拒绝回执但不增加 stateVersion、产物、资源或事件。格式／认证错误不保存回执；基础设施错误 503 不写成确定业务拒绝，`error.mutated` 必须为 null 表示结果未知，不能用 false 暗示尚未发生变更。调用者仍用原 ID 查询或重试。

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":1,"commandId":"unique-id","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s1"},"eventCursor":2,"status":"committed","error":null,"result":{"action":"move","position":[2,1]}}
```

claim 的 result：`{"action":"claim","quantity":4,"inventoryWood":4,"depotWood":8}`；build：`{"action":"build","entityId":"...","position":[2,1],"inventoryWood":1}`。

```json
{"schemaVersion":1,"rulesVersion":"r1","stateVersion":1,"commandId":"c2","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s1"},"eventCursor":2,"status":"rejected","error":{"code":"STALE_STATE","message":"世界已更新，请重新观察","retryable":false,"mutated":false}}
```

409：`STALE_STATE`、`RULES_VERSION_MISMATCH`、`IDEMPOTENCY_CONFLICT`、`CELL_OCCUPIED`。422：`INSUFFICIENT_RESOURCE`、`UNREACHABLE`（距离／墙／边界）。400：`INVALID_REQUEST`。401：`UNAUTHORIZED`。403：`IDENTITY_OVERRIDE`。404：`WORLD_NOT_FOUND`、`COMMAND_NOT_FOUND`。错误 message 以中文说明，调用者用 code 判断。

`GET /v1/worlds/foundation-01/commands/{id}`：仅查询当前 Actor 的回执；找到返回原业务状态码及结果，未找到 404。换会话后仍能查询同 Actor 回执，返回的 identity.sessionId 是历史命令会话，仅当前认证决定读取权限。别人的相同 ID 不能泄露其回执。

超时／连接失败表示未知：客户端保留原始请求，先查询或原样重发；查不到不自动生成新 ID。明确业务拒绝后重新观察，再次用户动作产生新命令。不要自动重复已确认成功的动作。

## 事件和客户端

`GET /v1/worlds/foundation-01/events?after=1` 短轮询，不实现长等待；返回共同信封及：

```json
{"events":[{"seq":2,"stateVersion":1,"commandId":"unique-id","actorId":"a1","type":"moved","position":[2,1]}],"nextCursor":2}
```

type 为 `worldSeeded`、`moved`、`claimed`、`built`；后两种可附 quantity 或 entityId／position，但不包含完整回执、会话或 token。事件仅解释事实，客户端状态最终以一致观察为准。

浏览器：Canvas 8×8 地图与可访问 DOM 控件；令牌输入为 password、只保存在 sessionStorage、连接成功后不显露。显示自己和另一居民、墙、储备点、目标、平台、库存、公共材料、版本、网络状态及明确拒绝原因。点击地图选择建造目标；移动按钮／方向键移动；领取数量与建造按钮。每 1—2 秒刷新观察，按顺序处理回复，避免旧观察覆盖较新版本。单个未决动作时禁用新动作，保留“查询结果／重试原命令”操作。401 清除会话并要求重新连接；断线恢复重新观察及解决未决命令，绝不能将确认后的库存恢复为本地猜测。

Canvas 保持正方形且适应手机宽度；HTML 展示格点选择、坐标及库存，不能只靠颜色或画布传达错误。

## 故障与验证边界

仅当 `WORLD_ENABLE_FAULTS=1` 时，在有效命令带 `X-Test-Fault` 头的专用测试实例允许：`throw-after-debit`（扣料后抛异常回滚）、`before-commit`（完整写入后 commit 前 Environment.Exit(81)）、`after-commit`（commit 后响应前 Environment.Exit(82)）。默认禁用；不得对普通演示实例启用。三种注入仅测试 claim/build，不对读取／会话操作触发。原 ID 恢复必须完成一次或返回已有结果。

服务不调用 LLM、外部网络、其他数据库或现有服务。SQL 参数化；SQLite 使用短事务、FULL 同步和本地文件；每次连接独立。试验代码、客户端与验收器按目录分工，协调者集成。全局版本冲突、单机存储及本机 token 签发是明确原型限制。
