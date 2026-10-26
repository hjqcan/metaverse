# Godot 3D 俯视原型

Godot 4.7.2 / GDScript，兼容渲染器。当前是连续自然地图：角色在河谷里自由行走，靠近树木采集，选择位置搭平台或造整座木桥。位置、碰撞、木材和建筑由 `World.Server` 权威裁决。

## 运行

```bash
npm start
# 另开终端
npm run start:godot
# 第二名居民
WORLD_ACTOR=a2 npm run start:godot
```

默认服务 `http://127.0.0.1:5089`，新 r8 预览数据在 `.local/continuous`。启动脚本从该目录的 `access.json` 读取令牌，不打印凭据。旧 r7 数据保留在 `.local/wilderness`，可以用 `npm run start:wilderness` 启动其历史服务；不会迁移或重置旧存档。

需安装 Godot 4.7.2，或设置 `GODOT_BIN=/path/to/godot`；本工作区已有经过官方 SHA512 校验的独立二进制。`WORLD_URL`、`WORLD_ACCESS_FILE`、`WORLD_ACTOR` 可覆盖连接。编辑器打开 `project.godot` 后运行，也可使用右上角连接面板。

## 操作

- WASD / 方向键自由行走，支持斜向；点击地面连续前往，点击树冠走近。撞到树、岩石、河岸便停下；点击路径暂不自动绕障碍。
- 靠近树中心 1.6 米内按 E 采集，每次取得1木材；采空变为树桩并移除树干碰撞。
- 1 选择平台，消耗3木材；2 选择整座木桥，消耗6木材。移动鼠标预览占地，左键确认。桥会对齐河道中心线；绿色表示当前可建，红色不可建。最终结果仍由服务器验证。
- Esc 取消行走／建造；滚轮缩放。镜头平滑跟随，遮住居民的树冠淡出，采集有动作与到账反馈。

接入失败或结果未知时暂停新动作，保留上次确认状态。原 ID、原请求和居民关联逐条保存到 `user://continuous-pending.json.d/` 的独立命令文件，不保存令牌。新建 r8 世界使用[持久世界实例绑定](../../docs/contracts/world-instance-v1.md)：记录按实例／居民分组，查询与重试携带原实例前置条件，同地址换新库不会重放旧动作；同实例换地址、换会话仍可找回原记录。一次重试只针对点击时的原命令，同居民多条未决逐项确认。`WORLD_CLIENT_STATE` 指定恢复路径前缀。每次重新连接都会刷新场景，即使居民与版本号相同。

已有 r8 数据库保持 legacy 模式，不自动迁移或新增实例标识，仍按原地址／居民恢复。旧 `continuous-pending.json` 只读兼容，确认后写入匹配原请求的完成标记，不整表回写；缺少实例来源的旧记录遇已标识新世界时保留并暂停替代动作。新格式 `recordVersion=2` 缺少实例 ID 属于损坏，不能降级。多进程保护适用于新版客户端；这里验证进程退出和重启恢复，未验证断电持久性。

## 协议与引擎边界

[`continuous-world-v1.md`](../../docs/contracts/continuous-world-v1.md) 是 Godot 与 Python Agent 共用的 r8 契约。`[x,z]` 是米制实数，不再是格子编号。

- `world_client.gd`：HTTP / JSON、认证观察、命令回执和恢复。
- `pending_store.gd`：逐命令持久记录、多实例隔离及旧格式读取。
- `main.gd`：键鼠输入、交互、建造预览和 HUD。
- `world_view.gd`、`river.gdshader`：连续地形、场景对象、角色表现和跟随镜头；Godot 碰撞体用于场景拾取，服务端负责行走碰撞。
- `src/World.Server/ContinuousWorld.cs`：可独立于引擎复用的几何、速度额度与资源规则。

当前仍是小型原型，四棵资源树共12木材，无工具制造、生态再生和角色骨骼资产。以后迁移 Unreal 需要重写客户端、材质和交互；世界身份、HTTP 契约与持久事实可继续使用，并不承诺 GDScript 自动转换。

## 验证与参考

```bash
dotnet build src/World.Server/World.Server.csproj --no-restore
npm run test:continuous
npm run test:godot
```

HTTP 验证和真实 Godot / OpenGL 输入测试使用隔离数据库和随机本机端口；故障代理测试断线、丢回包、原请求恢复和身份隔离。结果与截图写入 `.local/iter0014/`。Linux 需要 `xvfb-run`；模型调用0。

`test:godot` 还先运行双进程恢复存储回归：同居民并发发布、分别结算、重启保留全部未决，以及旧格式兼容、同ID异载荷和损坏记录。该部分使用真实 Godot 无画面进程，证据在 `.local/godot-recovery/`。随后运行同地址换库、同库搬地址与换会话、旧格式屏障和损坏保护记录回归，证据在 `.local/world-instance/godot/`；它们与实际渲染验收分别计数。

本轮按用户提供的 [游戏开发技能库](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) 使用 `godot-3d-essentials`、`godot-physics`、`camera-systems`。参考 [Sac 的 3D 游戏工作流](https://x.com/Saccc_c/status/2110694725640474759) 的统一风格、场景与角色分工、多角度实机检查；没有使用该游戏的模型、付费服务或改换引擎。

恢复实现按同一技能库的 `godot-gdscript`、`godot-gdscript-headless-testing` 和 `save-systems` 检查原请求保存、格式版本、并发写入与进程恢复。
