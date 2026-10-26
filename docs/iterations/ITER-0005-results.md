# ITER-0005：地点共同手记

日期：2026-10-25。本机实现与验收完成，采用当前原型。共同手记世界为 `http://127.0.0.1:5083`，第二位居民的实际报告为 `http://127.0.0.1:5083/resident.html?sample=postcards-reply`，可切换第一位记录。

居民现在能在到访后留下后来者可阅读的公开文字。两个真实 GPT-6 居民先后完成到访、留言和返回；第二位的实际决策输入包含第一位手记，并生成相关回应。草稿、服务器确认分享和返回分别记录。76 项 HTTP、48 项真实 Chrome 验收通过；长期体验价值仍未验证。

## 两位居民实际留下了什么

任务和预算在[共同手记契约](../contracts/postcards-v1.md)与[两份任务](../../examples/postcards/)中预先冻结。a1、a2 先后进入同一个独立 r4 验收世界，初始无桥、公共木材 12；起点分别为 `[1,1]`、`[1,2]`。每位只进行一次目标选择与起草，再由确定性执行器到场、visit、postcard、返回。

a1 留言：

> 愿来到静谧花园的你，能暂缓脚步，给自己一点从容的时间。祝你散步愉快，归途安然。

a2 的决策输入实际包含这段公开原文，随后回应：

> 谢谢你关于从容与归途安然的祝愿。愿这份温柔也传给后来者：给自己一点时间，慢慢走，平安归。

| 居民 / 绑定账号 | 地点 | 世界命令 / 上限 | 木材消耗 | 到访版本 | 分享版本 | 最终位置 |
|---|---|---:|---:|---:|---:|---|
| a1 / newton-ming | 静谧花园 | 12 / 14 | 0 | 6 | 7 | `[1,1]` |
| a2 / hjqcan | 静谧花园 | 10 / 12 | 0 | 17 | 18 | `[1,2]` |

终态版本 22，数据库有 2 条到访、2 条手记、23 条事件，外键错误为 0。每条分享都核对原命令、认证作者、自己的原 visit、原文、位置与版本。观察和停服后的只读 SQLite 审计一致：`12 = 公共储备 12 + 库存 0 + 实体 0`。

这证明本次输入确实携带前一手记，第二位产生了相关文字并成功提交。两份草稿都在出发前生成，不是到场感受的证明；阅读公开文字也不要求先走到地点。两篇文字不证明长期关系、复杂社交或人类觉得有趣。

完整输入、完成事件、两份报告及数据库核对见[实际会话证据](evidence/ITER-0005/live-session.json)，独立报告为[第一位](evidence/ITER-0005/live-first.json)与[第二位](evidence/ITER-0005/live-second.json)。记录时间为 2026-10-25 13:15:44—13:16:06 UTC，来自已结束的隔离验收世界；页面读取历史文件，不重新运行模型或世界。

## 真实调用与成本

| 居民 | 输入 token | 缓存输入 token | 输出 token | 任务累计耗时 |
|---|---:|---:|---:|---:|
| a1 | 12,244 | 0 | 119 | 11.61 秒 |
| a2 | 12,373 | 0 | 120 | 9.99 秒 |

本轮居民实际调用 2 次，达到预定上限；无补抽、重试或额外生成调用。CLI 请求模型为 `gpt-6-astra`，用量来自真实完成事件，不独立断言服务端内部路由，不换算费用。任务耗时包含选择和世界行动；单次模型进程耗时另记在会话证据中。研发 worker 对话与这两次居民调用分开计数。

## 实现与协作

`newton-ming` 的 GPT-6 worker 完成 C# 协议与事务。新 `postcards-v1/r4` 使用 schema 4；手记、事件、版本、回执一起提交，同一 visit 最多一篇，原 ID 重试只回放原结果。认证决定作者，不能引用另一居民的到访。文本为 1—160 个 Unicode 标量值，拒绝全空白、控制字符和孤立代理项，保留原文。手记不增发资源或奖励，数据库记录不可改写；旧 schema 1/2/3 不迁移。公开观察提供最近 50 篇，本人观察提供自己的最近 100 篇。

`hjqcan` 的 GPT-6 worker 扩展持久任务与模型输出适配。可选 `sharePostcard` 在原有一次选择中增加草稿；输入只增加最新 5 篇公开文字与能力标记，他人文字不能改变任务、预算或调用工具。任务先确认自己的原 visit，再确认本任务的原分享命令；旧手记、草稿及不匹配回执都不能结算本次分享。查回执失败保留 pending，恢复不换 ID、不重置预算。旧任务和报告继续兼容。

协调者完成浏览器界面、报告视图、独立验收及实际运行。人类按地点阅读，现场到访后发表；原文按纯文本显示。未发表草稿按居民和地点保存，轮询、刷新和切换不会覆盖，提交成功才清空。界面沿用单条未决命令与原 ID 恢复。报告分别显示行动前草稿、已确认分享与返回，错误文本或不匹配分享不能显示为完成；导入报告的内部一致性检查不认证其外部真实性。

两个 worker 均已交付、接受并释放。Python worker 退出码为 0；C# worker 的 Orca 退出码不可核实，但终端已断开，原进程及该终端关联进程均已消失，不将其记为退出码 0。worker 的 27 组 C# 自检（662 次实际 HTTP）和 26 项 Python 内存／进程替身自检只作构建反馈，不计入下面的独立验收数量。分工见[提案](../proposals/ITER-0005-postcards.md)。

## 验收与修订

| 套件 | 结果 | 证据 |
|---|---:|---|
| 新手记 HTTP | 17 / 17 | [api-results](evidence/ITER-0005/api-results.json) |
| 原基础 HTTP | 17 / 17 | [foundation](evidence/ITER-0005/foundation-http-regression.json) |
| 原通行 HTTP | 13 / 13 | [passage](evidence/ITER-0005/passage-http-regression.json) |
| 原持久任务 HTTP | 14 / 14 | [mission](evidence/ITER-0005/mission-http-regression.json) |
| 原活动 HTTP | 15 / 15 | [activities](evidence/ITER-0005/activities-http-regression.json) |
| 新手记 Chrome | 12 / 12 | [browser-results](evidence/ITER-0005/browser-results.json) |
| 原基础 Chrome | 10 / 10 | [foundation](evidence/ITER-0005/foundation-browser-regression.json) |
| 原通行 Chrome | 8 / 8 | [passage](evidence/ITER-0005/passage-browser-regression.json) |
| 原报告 Chrome | 8 / 8 | [report](evidence/ITER-0005/report-browser-regression.json) |
| 原活动 Chrome | 10 / 10 | [activities](evidence/ITER-0005/activities-browser-regression.json) |

HTTP 使用真实 C# 服务、SQLite 和隔离目录，模型决策为显式测试替身，外部调用为 0。新场景覆盖身份／现场／到访约束、原 ID 幂等与改文冲突、并发、提交前后真实进程退出、Unicode 边界、数量上限、原任务恢复、旧事实不可复用、错误回执和查询失败。预算不足可真实停在[已到访但未分享](evidence/ITER-0005/test-double-visit-only.json)，该报告不是模型样本。

新增 populated r3 fixture 来自已结束的 ITER-0004 全景模型世界，含两段桥、一次到访、余额和历史事件／回执；仅会话哈希及到期时间替换为公开测试值，保留 `user_version=3`。隔离导入后，新服务启动不改变旧库逻辑内容；原预览库不用于此兼容试验。

Chrome 通过实际界面完成发表和另一居民阅读，验证地点筛选、文字注入按原文显示、160 字边界、草稿保留、真实版本冲突、丢响应刷新恢复、服务重启、两份真实历史报告、伪完成拒绝与旧报告兼容。新套件 JavaScript 异常 0，报告页面世界请求 0，无额外模型调用。[世界桌面](evidence/ITER-0005/world-desktop.png)、[世界手机](evidence/ITER-0005/world-mobile.png)、[报告桌面](evidence/ITER-0005/report-desktop.png)、[报告手机](evidence/ITER-0005/report-mobile.png)均已视觉检查；手机宽度为 390px。

首次 HTTP 全套的文本业务断言已通过，但测试结束导出轨迹时，故意构造的孤立代理项不能以未转义 UTF-8 写出，触发 `UnicodeEncodeError`。已只修订验收轨迹为 ASCII JSON 转义，保留原请求并继续材料审计；全套 17 项重跑通过。[首次失败记录](evidence/ITER-0005/trace-before-fix.json)保留，不能把验收导出修复算作产品故障修复。

构建为 0 错误、0 警告，Python 编译、JS 语法和 diff 空白检查通过。环境为 SQLite 3.53.4、.NET SDK 10.0.302、Chrome 152.0.7977.82。当前实现与证据 SHA256 见 [manifest](evidence/ITER-0005/manifest.json)。

## 使用与复现

启动独立共同手记世界：

```bash
bash scripts/run_postcards.sh
# 打开 http://127.0.0.1:5083，使用 .local/postcards/access.json 中的居民 token
```

本轮已启动并连接 a1，初始版本 0、无桥、公共木材 12、尚无手记。两位模型居民的历史报告来自独立验收世界，不是当前预览数据。旧预览 5080 保持 r1／版本 7，5081 保持 r2／版本 19 和两段桥，5082 保持 r3／版本 0；[健康与状态记录](evidence/ITER-0005/preview-health.json)对应 13:18 UTC，之后居民操作会改变状态。

运行新的模型任务会实际调用绑定账号并对当前预览行动：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5083 --access-file .local/postcards/access.json \
  --account newton-ming --actor a1 --spec examples/postcards/first.json \
  --state .local/postcard-demo/first.state.json \
  --output .local/postcard-demo/first.report.json --max-steps 4
```

相同命令恢复下一段，去掉 `--max-steps` 执行到结束或预算用尽。恢复使用相同 state、spec、URL、身份和规则，累计时间包括暂停；不删状态来重置预算或丢弃原命令。完成第一位后，可用第二份任务、a2 和独立 state/output 让后来者读取当前公开文字。

完整两居民验收用 `python3 tests/postcards_live.py --account-one newton-ming --account-two hjqcan`，会新建一个独立世界，实际调用 GPT-6 两次，结束后关闭服务；不包含在普通回归中。无模型检查入口及 fixture 来源见 [tests/README](../../tests/README.md)。本轮没有提交、推送或公共发布，私有凭据、状态及完整日志保存在被忽略的 `.local/iter0005/`。

## 采用范围与下一问题

采用“先到访、再发表公开文字、后来者读取、原任务恢复”的本机原型。它给地点增加了最小可创作内容，但仍只有三个固定地点、短文和预定任务；具体行动由确定性执行器处理，没有长期记忆、自由技能、多任务资源池或常驻调度。

下一问题应是地点能否提供具体互动活动，以及真实参与者是否愿意阅读、创作和再次回来。需要人类使用反馈与未参与设计的任务案例；不能从两篇顺利提交的文字推断长期吸引力，也不据此增加账号、持续调用或自主发布范围。
