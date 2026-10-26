# ITER-0018 · 原命令恢复与世界实例

2026-10-26。新 r8 世界具有持久实例身份。地址被换成另一份数据库时，客户端保留原世界未确认命令，不向新世界重放；同一数据库换地址或更新会话后，仍按原命令恢复。两个 Godot 客户端共用恢复目录时不再覆盖彼此记录，同居民、同版本的重连也会刷新场景并停止旧路线。

本轮采用[研究中的实例绑定契约](../research/2026-10-26-continuous/03-instance-binding-contract.md)，实际接口见 [world-instance-v1](../contracts/world-instance-v1.md)。[ITER-0016 导航](ITER-0016-results.md)和 [ITER-0017 建造任务](ITER-0017-results.md)分别实现，再整合验收。

## 实现与恢复行为

新建 r8 数据库在创建事务中生成唯一实例 ID；已有 r1—r8 库不自动采用，也不迁移。认证后的观察公布身份，命令提交、回执查询和会话撤销在各自事务内校验 `World-Instance-Id`。缺失条件返回428，错误实例返回412，非法或重复条件返回400；均不生成业务回执、不推进世界版本。旧回执仍逐字返回，不修改原 JSON 或原会话身份。

Godot 的保护记录固定实例、居民、原命令 ID 和原始请求正文，按命令分别原子保存。同库换 URL 可以找回；其他世界的记录保留并持续提示。旧格式无实例记录不能根据当前观察补造身份，损坏保护记录也不能降级。旧聚合文件只读，以匹配原记录的结清标记防止再次恢复。当前保证针对进程退出与新客户端并行，不宣称断电落盘、数据库克隆双写或旧客户端同时写旧格式的安全性。

Python 传输先绑定已保存身份再观察。持久任务保存实例、原目标、起点和累计预算；迁址必须认证到原实例及居民，已完成任务作为历史报告读取，不发世界请求。具体任务接入与建造证据归属 ITER-0017。

连接代际参与 Godot 场景缓存。重连清空旧路线、排队点击、选择、建造预览和按住的移动输入，新观察更新导航几何；导航仍只产生意图，位置及碰撞以服务端为准。

## 已完成验收

以下均用隔离目录、随机本机端口及实际服务；模型调用0。构建自测、独立测试和导航作者的交叉复核分别列出，数量不相加成一个独立验收总数。

| 检查 | 结果 | 证据 |
|---|---:|---|
| 构建自测：实例 HTTP / SQLite | 8项通过 | [结果](evidence/ITER-0018/self-instance-api.json) |
| 构建自测：Godot 实例恢复，真实无头进程 | 9组、27断言通过 | [结果](evidence/ITER-0018/self-instance-godot.json) |
| 构建自测：共享目录、并发发布、结清和旧格式 | 6场景、400断言通过 | [结果](evidence/ITER-0018/self-shared-store.json) |
| 集成自测：Godot 实际渲染、输入、采集建造与恢复 | 9组、56断言通过 | [结果](evidence/ITER-0018/integrated-continuous-godot.json) |
| 集成自测：Godot 实际点击导航及双居民过桥 | 5组、42断言通过 | [结果](evidence/ITER-0018/integrated-navigation-godot.json) |
| 独立测试：直接原始 HTTP，含全部三种受保护操作 | 22项通过 | [结果及源码哈希](evidence/ITER-0018/independent-instance-api.json) |
| 独立测试：换库、回原库、迁址换会话与旧记录 | 5场景通过 | [结果](evidence/ITER-0018/independent-instance-godot.json) |
| 独立测试：共享未决、同版本换连接与旧记录结清 | 通过 | [结果](evidence/ITER-0018/independent-shared-recovery.json) |
| 独立测试：实际旧 r8 程序建库后升级 | 全库逻辑事实及原回执不变 | [结果](evidence/ITER-0018/independent-legacy-upgrade.json) |
| 独立测试：导航、实际 a2 身份及停服后数据库审计 | 5组通过 | [结果](evidence/ITER-0018/independent-navigation.json) |
| 独立测试：旧记录、损坏、异世界及原未决 UI | 4场景通过 | [结果](evidence/ITER-0018/independent-recovery-ui.json) |
| 独立测试：另一个进程结清原命令后，异世界提示消失 | 通过，新世界版本仍为0 | [结果](evidence/ITER-0018/independent-notice-resolution.json) |
| 独立测试：Python 同地址换库、原库迁址及会话轮换 | 通过，替换库所有表不变，原任务与预算保留 | [结果](evidence/ITER-0018/independent-mission-recovery.json) |
| 独立测试：实际平台建成后丢响应，再换会话恢复 | 通过，只提交一次建造，扣3木一次，实际到达返回 | [结果](evidence/ITER-0018/independent-construction-recovery.json) |
| 独立重跑：建设与任务实例专项 | 18项通过 | [结果及前后源码哈希](evidence/ITER-0018/independent-mission-suites.json) |
| 独立 Chrome：使用测试方真实丢回包恢复报告 | 8项通过，无 JS 错误、世界请求或390px横向溢出 | [结果](evidence/ITER-0018/independent-construction-browser.json) |
| 导航作者交叉复核：换实例取消路线及等待 HTTP 的点击 | 13断言通过，仅无头集成 | [结果](evidence/ITER-0018/navigation-connection-crosscheck.json) |

完整组合在 `941c97a` 的实现上通过216项 HTTP、134项 Chrome，包含新增建设13项、实例任务5项和建设报告8项，见 [正常入口全部结果](evidence/ITER-0017/integrated-regression.json)。这是 ITER-0017 作者运行的完整自测，构建协调者逐份核对原始证据计数并查看桌面及390px截图；独立任务复验另列。较早的198项 HTTP、126项 Chrome保留在 [HTTP](evidence/ITER-0018/http-regression.json)和 [Chrome](evidence/ITER-0018/browser-regression.json)，不重复累计。

独立测试方另以停服 SQLite 复核同世界建设链：a1 用61命令、6木材建桥；a2 用14命令、3木材建平台；a1 再用82命令、0木材访问平台并返回。设施归属与各自原命令一致，野外3木材加设施9木材仍为12，两人返回各自起点且库存0。该会话已报告问题全部复验关闭，自启服务无残留，见[最终状态](evidence/ITER-0018/independent-final-status.json)。受测实现及本目录证据哈希见 [manifest](evidence/ITER-0018/manifest.json)。

## 检出的缺陷及证据边界

最初 Python 只更新传输层，任务没有持久绑定原实例。独立测试实际在替换库执行了旧 pending：木材从0变1。[失败记录](evidence/ITER-0018/independent-mission-initial.json)保留。`941c97a` 接入后，同一独立探针确认替换库所有表不变、木材与版本仍为0、旧 ID 在新库仍查不到回执；原请求、初始观察、目标、起点、决定及累计预算保持。回到原库的新地址并轮换会话后，查询原回执继续。完成任务另以全离线客户端读取，零联网且状态文件字节不变。

独立 UI 测试还发现异世界记录提示三秒后被普通操作说明覆盖。[初次失败](evidence/ITER-0018/independent-recovery-ui-initial.json)保留。修复后提示持续可见，并在另一个客户端真实结清原命令后消失。导航初轮曾因忙碌时切换身份被忽略而误把 a1 当作 a2；撤回的结论、截图和修订见 ITER-0016，当前测试明确核对 a2 身份、坐标及原回执。

源码提交分别为 `a1a9635`（服务与传输）、`e25814d`（Godot 持久恢复）、`b180c80`（导航整合及恢复提示）、`941c97a`（指定建造与任务实例绑定）。每份独立结果记录受测源码哈希，较早导航运行与最后两行提示修复的范围分别保留；最后提示复验和导航作者交叉复核覆盖最终 Godot 文件。

## 运行边界与后续研究

本轮没有重启或迁移已有5089预览，没有新增模型调用，也没有增加木材、改变经济规则或删除历史回执。已有预览不因源码测试通过而获得新实例身份。

冻结研究批次为 [frozen-batch-01](../research/2026-10-26-continuous/frozen-batch-01.json)和 [frozen-batch-02](../research/2026-10-26-continuous/frozen-batch-02.json)：合计23份文件逐项核对哈希，后续新增研究不自动纳入。第二批已在受实例保护的 r8 实际执行121条命令：先行者采空12木材、建桥消耗6并保留6，另一居民能零木材往返公共桥，却仍无法造平台。材料耗尽后后来者缺少建材、全局版本导致移动竞争，以及移动回执存储增长均有实验记录；FIFO配额、参与单位、时间和再生参数仍为建议，不算已实现的公平或经济机制。

复现入口：`npm test`；设置 `GODOT_BIN` 后运行 `npm run test:godot`。普通回归不调用外部模型，Godot 完整入口同时包含存储、实例、连续交互及导航。真实渲染验收与无头恢复探针必须分别解释。
