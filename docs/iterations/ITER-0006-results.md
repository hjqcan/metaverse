# ITER-0006：花园共同画布

日期：2026-10-25。本机实现与验收完成，采用当前原型。共同画布世界为 `http://127.0.0.1:5084`，第二位居民的实际报告为 `http://127.0.0.1:5084/resident.html?sample=mosaic-reply`，可切换第一位记录。

花园现在有一块人类与 Agent 都能操作的 5×5 公共画布。两位真实 GPT-6 居民先后画出 7 格河流、添上 8 格花草，第二位保留了前人的图案与作者，双方随后返回。93 项 HTTP、60 项真实 Chrome 验收通过。这个结果证明本次有界接续创作，尚不证明作品质量或长期吸引力。

## 两位居民实际画了什么

[共同画布契约](../contracts/mosaic-v1.md)与[两份任务](../../examples/mosaic/)在开工前冻结。a1、a2 先后进入同一个独立 r5 验收世界，初始画布全空、公共木材 12、无桥；起点分别为 `[1,1]`、`[1,2]`。本轮候选地点只有静谧花园，模型主要决定构图，不作为新的多目标选择能力证据。每位一次调用后，由确定性执行器移动、确认自己的 visit、提交原画布修改，再返回。

| 居民 / 绑定账号 | 实际修改 | 世界命令 / 上限 | 木材消耗 | 到访 / 绘制世界版本 | 最终位置 |
|---|---|---:|---:|---|---|
| a1 / newton-ming | 7 格河蓝，边相接形成连续河流 | 12 / 14 | 0 | 6 / 7 | `[1,1]` |
| a2 / hjqcan | 6 格叶绿、2 格花红，只改空白处 | 10 / 12 | 0 | 17 / 18 | `[1,2]` |

a1 的河流坐标为 `(0,1) → (1,1) → (1,2) → (2,2) → (3,2) → (3,3) → (4,3)`。a2 的实际输入完整包含 a1 提交后的 25 格画布和来源，再添加植物与花色。终态所有 7 格河流的颜色、作者、命令和世界版本仍与第一位一致；画布 revision 从 0 经 1 到 2。每次提交均核对原命令、认证作者、自己的原 visit、规范化 patch、基准版本、位置和世界版本。

终态世界版本 22，数据库有 2 条到访、2 条不可变修改、23 条事件，外键错误为 0。观察与停服后的只读 SQLite 审计一致：`12 = 公共储备 12 + 库存 0 + 实体 0`。绘制不增发物资或奖励。

完整实际输入和数据库核对见[会话证据](evidence/ITER-0006/live-session.json)，独立报告为[第一位](evidence/ITER-0006/live-first.json)与[第二位](evidence/ITER-0006/live-second.json)。运行时间为 2026-10-25 14:28:45—14:29:15 UTC。两份构图均在出发前产生；读取公开画布不要求先走到花园，实际绘制要求现场到访。报告读取已结束的隔离验收记录，不重新运行模型或世界。

## 调用与成本

| 居民 | 输入 token | 缓存输入 token | 输出 token | 任务累计耗时 |
|---|---:|---:|---:|---:|
| a1 | 12,975 | 0 | 172 | 17.42 秒 |
| a2 | 13,108 | 0 | 195 | 12.01 秒 |

本轮居民实际调用 2 次，达到预定上限，无补抽、生成重试或额外调用。CLI 请求模型为 `gpt-6-astra`；用量取自真实完成事件，不独立断言服务端内部路由，也不换算费用。任务耗时包括选择与世界行动，单次模型进程耗时另存于会话证据。研发 worker 对话与这两次居民调用分开计数。

## 实现与协作

`newton-ming` 的 GPT-6 worker 完成 C# 世界协议和事务。新 `mosaic-v1/r5` 使用 schema 5，在已有花园加入固定六色与 25 格画布；原 r1—r4 数据不迁移。每次自己的到访允许一批 1—8 格修改，与手记名额独立。patch 按 y/x 规范化，数组重排不改变同一命令的语义；改色重试会冲突。不变色或任何非法格会拒绝整批。所有格、画布版本、历史、世界版本、事件与回执在同一事务提交。当前格记录最后作者，擦白也保留来源；修改历史禁止更新或删除。观察提供最新公开 50 条、本人 100 条历史，数据库保留完整记录。

`hjqcan` 的 GPT-6 worker 扩展 Python 持久任务和模型适配。可选 `paintMosaic` 在原来的一次选择中增加构图，完整能力与候选检查先于模型及动作。基准 revision 从原观察冻结，模型不能指定或刷新它。执行器只以本任务原 visit 和原绘制完整记录认定完成，错误回执或查询错误保留原 pending；丢响应恢复不换 ID、不重置预算。其他人先修改画布时，任务以 `MOSAIC_CHANGED` 停止，不自动重新生成或覆盖。原修改已经提交后，即使后来者覆盖，也保留其已完成事实。旧任务、报告及 r5 上的手记继续兼容。

协调者完成界面、报告、独立验收和实际运行。人类界面分开显示公共画布与未发表草图，固定调色板、键盘可操作格子和作者说明；草图按居民保存，轮询、刷新和切换不会丢失。版本冲突保留草图并提供清除重画，提交成功才清空。报告分别显示行动前构图、本次确认改动与任务结束画布；草图和不匹配 edit 不能显示完成。导入报告的内部一致性检查不认证文件的外部真实性。

两名 worker 均已交付、接受并释放，两个终端实际退出码均为 0。C# worker 的 6 组真实 HTTP 自检、426 个断言和 114 条修改的数据库审计，以及 Python worker 的 20 项内存／进程替身自检，仅作为构建反馈，不计入独立验收。Python 自检中的子进程退出是真实退出，世界提交仍是替身；实际服务与数据库由下列独立检查覆盖。分工见[提案](../proposals/ITER-0006-mosaic.md)。

## 验收结果

| 套件 | 结果 | 证据 |
|---|---:|---|
| 新画布 HTTP | 17 / 17 | [api-results](evidence/ITER-0006/api-results.json) |
| 原基础 HTTP | 17 / 17 | [foundation](evidence/ITER-0006/foundation-http-regression.json) |
| 原通行 HTTP | 13 / 13 | [passage](evidence/ITER-0006/passage-http-regression.json) |
| 原持久任务 HTTP | 14 / 14 | [mission](evidence/ITER-0006/mission-http-regression.json) |
| 原活动 HTTP | 15 / 15 | [activities](evidence/ITER-0006/activities-http-regression.json) |
| 原手记 HTTP | 17 / 17 | [postcards](evidence/ITER-0006/postcards-http-regression.json) |
| 新画布 Chrome | 12 / 12 | [browser-results](evidence/ITER-0006/browser-results.json) |
| 原基础 Chrome | 10 / 10 | [foundation](evidence/ITER-0006/foundation-browser-regression.json) |
| 原通行 Chrome | 8 / 8 | [passage](evidence/ITER-0006/passage-browser-regression.json) |
| 原报告 Chrome | 8 / 8 | [report](evidence/ITER-0006/report-browser-regression.json) |
| 原活动 Chrome | 10 / 10 | [activities](evidence/ITER-0006/activities-browser-regression.json) |
| 原手记 Chrome | 12 / 12 | [postcards](evidence/ITER-0006/postcards-browser-regression.json) |

新 HTTP 使用真实 C# 服务、SQLite 和隔离目录，模型决策为明确测试替身，外部调用为 0。覆盖作者、现场、本人 visit、每次到访一批、规范化幂等、并发、严格结构、整批原子性、提交前后真实进程退出、原任务恢复、错误证据与查询失败、过期草图停止、历史数量上限和已提交修改被覆盖后的事实保留。预算不足时实际停在[已到访、未绘制](evidence/ITER-0006/test-double-visit-only.json)，该报告不是模型样本。

新增 populated r4 fixture 源于已结束的 ITER-0005 真实两居民世界，保留两条到访、两篇手记及历史回执／事件；仅会话哈希和到期时间换为公开测试值，保留 `user_version=4`。隔离导入后，新服务启动不改变旧库逻辑内容；测试还验证原手记在 r5 继续可用。原预览数据库未用于故障或兼容试验。

Chrome 通过实际界面完成绘制和另一居民接续，检查键盘、8 格上限、草图保存、真实画布／世界版本冲突、丢响应刷新原 ID 恢复、服务重启、实际历史报告、伪完成拒绝和旧报告兼容。新套件 JavaScript 异常 0，报告页面世界请求 0，无额外模型调用。[世界桌面](evidence/ITER-0006/world-desktop.png)、[世界手机](evidence/ITER-0006/world-mobile.png)、[报告桌面](evidence/ITER-0006/report-desktop.png)、[报告手机](evidence/ITER-0006/report-mobile.png)均已视觉检查；手机宽度为 390px。世界截图来自 UI 验收世界，报告截图来自上述两次真实模型记录。

新 HTTP 与 Chrome 套件首次全套通过，预期拒绝和故障退出属于验收场景；本轮没有以重跑替换失败的实际模型样本。构建 0 错误、0 警告，Python 编译、JS 语法、diff 空白检查通过。环境为 SQLite 3.53.4、.NET SDK 10.0.302、Chrome 152.0.7977.82。实现与证据 SHA256 见 [manifest](evidence/ITER-0006/manifest.json)。

## 使用与复现

启动独立画布世界：

```bash
bash scripts/run_mosaic.sh
# 打开 http://127.0.0.1:5084，使用 .local/mosaic/access.json 中的居民 token
```

本轮已启动并连接 a1，世界版本 0、画布版本 0、全空、无桥、公共木材 12。人类可用方向按钮走到花园 `(1,6)`，记录本次到访，再选颜色修改草图并发表；再次绘制需要新的到访。作品向本世界居民公开，之后也可以被别人修改。

两位模型居民的历史报告来自独立验收世界，当前预览没有自动导入这幅作品。旧预览 5080 保持 r1／版本 7；5081 保持 r2／版本 19、两段桥；5082 保持 r3／版本 0；5083 保持 r4／版本 0。[健康与状态记录](evidence/ITER-0006/preview-health.json)对应 14:31 UTC，之后居民操作会改变状态。

运行新模型任务会实际调用绑定账号并对当前预览行动：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5084 --access-file .local/mosaic/access.json \
  --account newton-ming --actor a1 --spec examples/mosaic/first.json \
  --state .local/mosaic-demo/first.state.json \
  --output .local/mosaic-demo/first.report.json --max-steps 4
```

相同命令恢复下一段，去掉 `--max-steps` 执行到结束或预算用尽。恢复使用相同 state、spec、URL、身份和规则，累计时间包括暂停；不删除状态来重置预算或丢弃原命令。第一位完成后，用第二份任务、a2 和独立 state/output 接续。若画布基准版本已经变化，当前任务停止；新创作须使用明确的新任务。

完整两居民验收入口为 `python3 tests/mosaic_live.py --account-one newton-ming --account-two hjqcan`，会新建独立世界并真实调用 GPT-6 两次，结束后关闭服务；不包含在普通回归中。无模型检查及 fixture 来源见 [tests/README](../../tests/README.md)。本轮没有提交、推送或公共发布；私有凭据、任务状态及完整日志保存在被忽略的 `.local/iter0006/`。

## 采用范围与下一问题

采用“现场到访、操作共享画布、保留作者和历史、后来者接续、冲突停止与原任务恢复”的本机原型。画布是已有地点的表现内容，不是制造或交易物品；每次修改无木材成本并不证明所有创作都没有运行成本。

下一问题是实际参与者是否愿意主动创作、理解他人的作品并再次回来，以及覆盖他人作品时应如何协商。当前最后作者与不可变修改记录只提供事实依据，尚未实现作品权限、协商治理、长期记忆、多任务预算池或常驻居民调度。两次预设任务不能替代真人体验反馈，也不扩大账号、持续调用或自主发布范围。
