# ITER-0008：未处理提议持续可见

日期：2026-10-25。本机实现与验收完成，采用当前原型。新预览为 [5086](http://127.0.0.1:5086)，[实际审阅报告](http://127.0.0.1:5086/resident.html?sample=inbox-review)可切换提议人记录。

修复了“新记录把旧待办挤出最近列表后，居民无法再处理它”的读取缺口。新增完整提议收件箱、筛选、计数、游标分页和按原引用读取详情；沿用 r6、schema 6 和全部原审阅规则。两次真实 GPT-6 调用验证：原提议被 51 条更新且已处理的记录挤出最近 50 条之后，另一居民仍找到并审阅它。129 项 HTTP、84 项真实 Chrome 检查通过。

## 问题与实现

开工前用原二进制和明确程序数据复现：数据库中有 52 条提议，最早一条未处理，后 51 条已拒绝；公共观察仅含最近 50 条，原待办不可见。新建审阅任务报 `mosaic_proposal_not_found`，模型调用为 0。原事实仍在数据库，缺口在读取路径。[基线证据](evidence/ITER-0008/baseline-retention.json)与[冻结契约](../contracts/mosaic-inbox-v1.md)保留。

C# 新增两个认证只读接口：

- `GET /v1/worlds/{worldId}/mosaic-proposals`：按发给本人、本人提出或全部筛选，状态为等待决定、已处理或全部；每页最多 20 条，以原提议世界版本倒序和 `before` 游标翻页。计数覆盖完整数据库，不受本页和状态筛选影响。
- `GET /v1/worlds/{worldId}/mosaic-proposals/{proposalActorId}/{proposalCommandId}`：按原作者与原命令读取完整提议及审阅，能够定位最近列表以外的记录。

同一响应的计数、内容、嵌套结果与版本在一个只读事务中取得。GET 和错误请求不改变数据库逻辑内容。查询严格拒绝未知、重复和非法字段，身份来自认证。新 r6 观察追加 capability，原公开最近 50／本人最近 100 列表保持原样；旧 r1—r5 不查询不存在的表。没有新动作、schema 迁移或规则升级。

人类界面默认“发给我的／等待决定”，提供完整计数、返回较新页、更早提议和回到最新。轮询保留理由、焦点与选区；若新条目把正在编辑的页尾条目挤出，暂留旧页并暂停审阅，离开输入框后再更新。失败保留上次列表并标明未更新，迟到响应不能覆盖新筛选或身份。花园到访入口复用原命令通道，仍需本人到现场。旧 r6 服务没有 capability 时，界面明确标注仅覆盖最近 50 条，不请求新接口。

Python 只在新建审阅任务时按原引用读取详情，核对身份、原作者／命令、完整提议、未审阅状态和版本后才调用模型。详情比观察新时只刷新一次观察并核对世界／身份／规则。失败不回退到相似提议；既有任务与未决恢复不重新查询、不换引用、不重置预算。完整原提议保存在决定中，即使结束报告的最近 50 条不含它，仍可核对原决定与事实。

## 两次真实调用

隔离世界先由程序通过正常 HTTP 种入三格河流并返回，消耗 12 条命令；明确不是模型作品。a2 随后真实调用一次，提出将左端 `(1,2)` 从河蓝改成日黄并返回。再由程序生成 51 条新提议并逐条拒绝，含往返共 222 条命令，画布不变。这些是历史压力样本，不计为模型互动。

此时完整收件箱为待办 1、已处理 51、合计 52；原提议已不在公共最近 50 条中。a1 通过收件箱发现它，新建任务按原引用读取一次详情，完整原文和 patch 进入实际模型输入。a1 独立选择 accept，现场记录到访后接受并返回。

| 居民 / 账号 | 实际任务 | 命令 / 上限 | 到访 / 提交版本 | 返回位置 |
|---|---|---:|---|---|
| a2 / hjqcan | 提议只改河流左端点，尚未改图 | 10 / 12 | 17 / 18 | `[1,2]` |
| a1 / newton-ming | 从完整收件箱找到原提议，选择接受 | 12 / 14 | 250 / 251 | `[1,1]` |

接受只改原 patch 一格，其他格颜色与来源保持不变；实际 edit 由 a1 提交，提议人 a2 的来源链保留。双方共 22 条模型任务命令、0 木材；加上明确程序准备，最终世界版本 256、257 条事件、105 条到访、52 条提议、52 条审阅、2 条画布修改（含种图）。外键错误 0，材料为 `12 = 公共储备 12 + 库存 0 + 实体 0`。原命令、事件、审阅、原提议与当前格逐项核对。

真实运行时间为 2026-10-25 15:29:54—15:30:18 UTC，完整输入、收件箱发现、详情读取和数据库检查见[会话证据](evidence/ITER-0008/live-session.json)；单独报告为[提议人](evidence/ITER-0008/live-proposer.json)与[审阅人](evidence/ITER-0008/live-reviewer.json)。报告仅展示已结束会话，打开不会调用模型或操作世界。

| 居民 | 输入 token | 缓存输入 | 输出 token | 模型调用耗时 |
|---|---:|---:|---:|---:|
| a2 | 13,072 | 0 | 151 | 10.88 秒 |
| a1 | 13,269 | 0 | 94 | 9.56 秒 |

实际居民调用 2 次，达到冻结上限，无补抽。CLI 请求模型为 `gpt-6-astra`，用量来自完成事件；不独立断言内部路由或换算费用。研发 worker 对话单独计数。本轮验证旧记录可发现和原引用正确执行，不证明长期记忆、多轮对话或持续协商能力。

## 独立验收与反馈

| 套件 | HTTP | Chrome | 证据 |
|---|---:|---:|---|
| 新收件箱 | 17 / 17 | 13 / 13 | [HTTP](evidence/ITER-0008/api-results.json) · [Chrome](evidence/ITER-0008/browser-results.json) |
| 原基础 | 17 / 17 | 10 / 10 | [HTTP](evidence/ITER-0008/foundation-http-regression.json) · [Chrome](evidence/ITER-0008/foundation-browser-regression.json) |
| 原通行 | 13 / 13 | 8 / 8 | [HTTP](evidence/ITER-0008/passage-http-regression.json) · [Chrome](evidence/ITER-0008/passage-browser-regression.json) |
| 原任务／报告 | 14 / 14 | 8 / 8 | [HTTP](evidence/ITER-0008/mission-http-regression.json) · [Chrome](evidence/ITER-0008/report-browser-regression.json) |
| 原活动 | 15 / 15 | 10 / 10 | [HTTP](evidence/ITER-0008/activities-http-regression.json) · [Chrome](evidence/ITER-0008/activities-browser-regression.json) |
| 原手记 | 17 / 17 | 12 / 12 | [HTTP](evidence/ITER-0008/postcards-http-regression.json) · [Chrome](evidence/ITER-0008/postcards-browser-regression.json) |
| 原画布 | 17 / 17 | 12 / 12 | [HTTP](evidence/ITER-0008/mosaic-http-regression.json) · [Chrome](evidence/ITER-0008/mosaic-browser-regression.json) |
| 原协商 | 19 / 19 | 11 / 11 | [HTTP](evidence/ITER-0008/consent-http-regression.json) · [Chrome](evidence/ITER-0008/consent-browser-regression.json) |
| 合计 | **129 / 129** | **84 / 84** | 不含 worker 自检及两次真实居民调用 |

新 HTTP 使用实际服务与 SQLite，覆盖超过 50／100 条后的最早待办、完整计数、范围／状态、严格查询、游标和新插入、原记录审阅、读取权限、数据库逻辑完全不变、旧 populated r6、r1—r5、Python 预检错误先于模型、版本刷新、旧服务回退、原任务恢复与完成后无操作。模型选择为明确测试替身。`consent-v6-populated.sql` 来自已结束的 ITER-0007 实际会话，保留作品与提议／接受事实，只将 session 哈希和到期时间换成公开测试值，保留 schema 6。

新 Chrome 通过实际 HTTP 生成历史记录，检查默认待办定位、筛选和游标、插入后分页稳定、理由节点／焦点／选区、到访入口、503 保留列表并暂停审阅、筛选及身份迟到响应、草稿隔离、旧提议接受、旧服务回退、拒绝丢响应刷新后的原 ID 恢复、重启、真实报告和 390px。JavaScript 异常 0，报告世界请求 0，界面测试本身模型调用 0。

独立验收出现的测试问题已保留：

1. [HTTP 首次结果](evidence/ITER-0008/api-initial-results.json)为 15 通过、2 失败。断言误把命令回执专用 `action` 字段要求在提议／审阅详情中出现；按冻结详情契约修正断言后 17 项通过，未修改产品。
2. 原协商用例改为显式 all/all 后，[首次回归](evidence/ITER-0008/consent-browser-initial-results.json)在世界观察已更新而收件箱尚未返回时读取旧内容。补充等待独立列表完成后，[第二次](evidence/ITER-0008/consent-browser-second-results.json)发现旧断言要求已处理按钮节点被移除；新界面复用节点并隐藏整个表单，应断言按钮不可见。调整后 11 项通过，实际接受／拒绝和数据库结果始终正确。

[世界桌面](evidence/ITER-0008/world-desktop.png)、[世界手机](evidence/ITER-0008/world-mobile.png)、[报告桌面](evidence/ITER-0008/report-desktop.png)、[报告手机](evidence/ITER-0008/report-mobile.png)均已视觉复核。世界截图来自明确程序准备的 UI 验收世界；报告截图来自两次真实调用。构建 0 错误／警告，Python 编译、JavaScript 语法与 diff 空白检查通过。实现及证据哈希见 [manifest](evidence/ITER-0008/manifest.json)，前七轮历史证据保持原哈希。

## 分工与运行

两账号 GPT-6 worker 按文件独占完成 C# 只读接口和浏览器收件箱；协调者负责 Python 详情预检、报告入口、独立验收和真实会话。C# 自检包含 152 条旧 r6 记录、180 页组合读取、150 次并发 GET 和旧场景逻辑不变；UI 的 14 项 Chrome 自检使用完全拦截的 stub 响应。这些均未计入独立验收。worker 自检的 visit helper 字段错误及非安全测试域问题也保存在私有报告中。

两项任务均已接受并 release，无待处置 worker。UI 终端退出码 0；C# 终端显示 exited，但宿主给出 `-1 / stop_unverified`，只记录已离开运行状态，不宣称正常退出码已核实。源码、报告和验收结果已独立确认；没有扩大账号或持续运行居民任务。

```bash
bash scripts/run_inbox.sh
# 打开 http://127.0.0.1:5086
# 居民凭据：.local/inbox/access.json
```

已连接新预览的 a1，世界和画布版本均为 0，收件箱为空，木材 12。实际模型样本在另一个已结束的隔离世界，未导入当前预览。先到花园 `(1,6)` 绘图，另一身份提出修改，再由目标作者在收件箱处理；收件箱的到访按钮只在现场可用。旧 5080—5085 未重启、未迁移；[健康记录](evidence/ITER-0008/preview-health.json)确认旧 r1 版本 7、旧 r2 版本 19／两段桥，其余预览版本 0。5085 仍运行旧 r6 服务，界面会说明最近列表范围有限。

无模型检查：

```bash
python3 tests/inbox_api.py
node tests/browser/inbox.mjs
```

真实复现为 `python3 tests/inbox_live.py --account-one newton-ming --account-two hjqcan`；每次创建隔离世界，准备程序历史并真实调用两次 GPT-6，结束后停服，不属于普通回归。沿用 `examples/consent/` 任务语义；新审阅引用必须来自所选世界的真实提议，恢复沿用原 state、身份和任务。详见 [tests/README](../../tests/README.md)。

采用范围是持续可查询的待办和原引用读取。翻页不承诺跨请求快照，其他居民审阅会改变过滤结果；本轮未做大规模性能或真人体验验收。后续应根据实际参与反馈决定活动和协作方式，不能由两次预设任务推导长期吸引力。未提交、推送或公共发布；私有任务、凭据与日志保存在被忽略的 `.local/iter0008/`，新预览数据独立位于 `.local/inbox/`。
