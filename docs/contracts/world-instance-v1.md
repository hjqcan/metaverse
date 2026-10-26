# 世界实例绑定 v1（ITER-0018）

采用研究建议中的持久实例 ID 与 HTTP 前置条件。它区分独立新建的数据库，不改变 r8、`PRAGMA user_version=8`、命令 JSON、语义哈希或历史回执 JSON。

## 数据边界

新建 `wilderness-continuous-v1` 数据库在播种事务内建立 `world_instance`，保存唯一 `w_` 加 32 位小写十六进制随机 ID。普通重启、换会话和换监听地址保持它；UPDATE/DELETE 被拒绝。表已存在但内容损坏时启动失败，不重新生成身份。

已有 r1—r8 库和新建历史场景维持 legacy 模式，启动与读取不自动添加元数据。**已有预览库不会因此获得保护。** 本轮没有旧库采用命令，也不执行迁移或重建。复制数据库会复制 ID；本协议不处理热换库、备份回退裁决、克隆双写或不可信服务器冒充。

## HTTP

已标识世界的 observation 同时返回：

```json
{
  "world": {"id": "foundation-01", "instanceId": "w_0123456789abcdef0123456789abcdef"},
  "commandBinding": {"version": 1, "required": true, "header": "World-Instance-Id"}
}
```

响应头 `World-Instance-Id` 必须与 body 一致。其余 world 字段保留。历史回执以相同 JSON 字节和历史 sessionId 返回，实例信息只在响应头中携带。

| 请求 | 前置条件 |
|---|---|
| 首次 observation | 可不带头，以发现实例 |
| observation、events、proposal 读取 | 若带头，必须匹配 |
| POST commands、GET commands/{id}、DELETE session | 已标识世界必须带匹配头 |

认证先于实例校验。写事务执行顺序为 `BEGIN IMMEDIATE` → 认证 → 读取实例并校验 → 查询原回执 → 原有规则与状态校验 → 修改及提交。匹配实例后，幂等回执仍先于状态版本校验返回。

| 条件失败 | HTTP / code |
|---|---|
| 必需头缺失 | 428 `WORLD_INSTANCE_REQUIRED` |
| 实例不匹配 | 412 `WORLD_INSTANCE_MISMATCH` |
| 已绑定请求访问 legacy 世界 | 428 `WORLD_INSTANCE_UNAVAILABLE` |
| 空值、重复、逗号拼接或非法格式 | 400 `INVALID_WORLD_INSTANCE` |

头名不区分大小写，值精确匹配。条件失败没有业务 `status:rejected`，不保存业务回执，不改世界版本、事件或资源。`mutated=false` 仅说明当前请求没有改变当前库，不能结清原世界的未决命令。无头旧客户端不能写已标识世界。

## 客户端恢复

Godot 新保护记录使用 `recordVersion=2`，冻结 `instanceId/worldId/actorId/commandId/body/endpoint`；endpoint 是来源信息，索引由实例、世界和居民组成。同实例换地址时，用户明确连接新地址并认证后，可恢复原记录。不会自动转发令牌或跟随重定向。

同地址换实例时，保留原实例记录，不自动提交、结清或删除；新世界可使用自己的记录。新格式缺少有效 ID 属于损坏，不能降级。合法旧记录只能在 legacy 世界按原纪律恢复；遇已标识世界成为 `legacy_unbound`，保留原文并暂停替代动作。

Python `WorldClient` 首次观察核对响应头、`world.instanceId` 与 `commandBinding` 后固定绑定；后续请求自动发送该头。任务恢复必须在观察前调用 `bind_instance(saved_instance_id)`，显式 `None` 固定为 legacy。实例变化或无法验证响应抛出 `WorldBindingError`，不能据此清除 pending。任务层仍需保存并检查 actor、world、rules、spec、原起点、原请求和累计预算；不得给旧任务补上当前实例 ID。

回执和 `COMMAND_NOT_FOUND` 只有在响应绑定匹配时才可信。缺少或错误响应头、412/428、传输失败均保留原请求；确认不存在后只允许原 ID、原 body 重试。

## 验证入口

`python3 tests/world_instance_api.py` 使用隔离 HTTP 服务和 SQLite，覆盖新库唯一性、重启、旧库、元数据损坏、条件失败无业务副作用、同地址换库、换端口与会话后原回执字节保持。连续几何与动作回归仍运行 `python3 tests/continuous_api.py`。Godot、任务层与独立验收证据分别记录，源码契约本身不等于现场验收。
