# Godot 3D 俯视原型

先用 Godot 做原型，后续迁移 Unreal。当前使用 Godot 4.7.2 标准版 / GDScript，兼容渲染器；不需要 Godot .NET。这是同一 `World.Server` 的原生客户端，初始分散居民、采集、库存、建造、通路与持久化仍由服务端裁决。浏览器保留为观察与调试入口。

## 运行

先在仓库根目录启动服务：

```bash
npm start
```

另开终端运行客户端：

```bash
GODOT_BIN=/path/to/godot npm run start:godot
# 本工作区已放置独立 Godot 二进制时，可以直接 npm run start:godot
```

脚本默认连接 `http://127.0.0.1:5088`，从本机 `.local/wilderness/access.json` 读取 a1 的令牌，不打印或把令牌传进命令参数。`WORLD_ACTOR=a2` 可进入另一居民；`WORLD_URL`、`WORLD_ACCESS_FILE` 可指定另一服务和凭据文件。直接在 Godot 编辑器打开 `project.godot` 并按 F6/F5 运行时，也可在客户端填写地址与令牌。

操作：鼠标选择树木或地块，按钮走到树旁／走到这里；WASD、方向键或屏幕方向按钮逐格移动；树旁按 E 或点击砍取，每次获得1木材。采空后可通行，在空地搭平台、在相邻水面铺桥段，各耗3木材。滚轮缩放，Esc／停止按钮中断后续寻路；已经发送的那一步等待原回执。当前是8×8格的玩法原型，没有连续运动、角色动画、工具或生态再生。

本版连接 `wilderness-v1` / r7。旧实验场景继续使用原浏览器；不静默迁移旧库。接入失败或读取失败时暂停新动作，显示上次已确认画面。动作发送前先把原ID、载荷与居民关联写入 `user://pending.json`，无令牌；结果未知时保留，可查询或原样重试。重启客户端和服务后按同一地址、居民恢复，不新建替代动作。`WORLD_CLIENT_STATE` 可指定独立恢复文件，自动验收使用它隔离数据。

## 引擎边界

- `world_client.gd`：现有 HTTP / JSON 协议适配、认证观察、命令与回执、未决记录。
- `world_view.gd`：把观察映射为地块、树木、居民、平台／桥梁；碰撞体仅用于鼠标选择。
- `main.gd`：输入、界面与逐步寻路。规划只建议下一步，每一步都需服务器确认；不直接修改权威位置、库存或资源。

Godot 使用 X/Z 表示服务端二维 x/y，1格对应1视觉单位。后续 Unreal 重新实现输入、画面、镜头和协议适配，继续接入相同世界ID、居民身份、命令和版本规则；世界数据库不因换引擎重建。GDScript、场景、材质、UI不会自动转为 Unreal。现阶段不增加双引擎抽象框架，也不把规则搬进 Godot。

## 验证

```bash
# 先构建 World.Server；普通回归仍为 npm test
dotnet build src/World.Server/World.Server.csproj --no-restore
GODOT_BIN=/path/to/godot npm run test:godot
```

Linux验收还需要 `xvfb-run`。脚本启动真实 Godot OpenGL 渲染器，给实际场景注入鼠标／键盘输入，连接隔离的 .NET / SQLite 服务，并用代理制造丢响应；自动保存截图与结果。服务、代理和客户端都在结束后停止，数据在 `.local/iter0011/`。模型调用为0。无图形界面的 `--headless` 导入检查不替代真实渲染验证。

依据：[Godot下载](https://godotengine.org/download/linux/)、[HTTPRequest](https://docs.godotengine.org/en/stable/classes/class_httprequest.html)、[Camera3D](https://docs.godotengine.org/en/stable/classes/class_camera3d.html)。下载版本已通过官方 `SHA512-SUMS.txt` 校验。
