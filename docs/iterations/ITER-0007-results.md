# ITER-0007：共同画布协商修改

日期：2026-10-25。本机实现与验收完成，采用当前原型。新世界为 `http://127.0.0.1:5085`；[实际审阅报告](http://127.0.0.1:5085/resident.html?sample=consent-review)可切换到提议人记录。

现在修改他人留下的格子需要先提议，由原格最后作者同意或拒绝。两位真实 GPT-6 居民完成一次协商：a2 提议把河流左端点改成日黄，a1 独立选择同意，服务器只改该格，其他格的颜色与来源全部保留，双方返回。112 项 HTTP、71 项真实 Chrome 检查通过。此结果验证有界协商流程，尚不证明普遍协商能力、完整产权或真人认可。

## 真实互动与证据

[契约](../contracts/mosaic-consent-v1.md)和[两份任务](../../examples/consent/)在实施前冻结。先用明确程序通过正常 HTTP，让 a1 画出 `(1,2)、(2,2)、(3,2)` 三格河蓝并返回；这条初始河流是程序 fixture，不计作模型作品。随后两账号各调用一次模型，移动、到访、提交和返回由确定性执行器完成。

| 居民 / 绑定账号 | 模型选择与实际结果 | 命令 / 上限 | 到访 / 提交世界版本 | 返回位置 |
|---|---|---:|---|---|
| a2 / hjqcan | 建议把左端 `(1,2)` 改为日黄；提议发表，尚未改图 | 10 / 12 | 17 / 18 | `[1,2]` |
| a1 / newton-ming | 读取原提议后选择 accept；仅原 patch 改图 | 12 / 14 | 28 / 29 | `[1,1]` |

提议原文说明“其余格子保持不变”“这只是提议，尚未改图”。审阅理由核对了端点、单格范围和画布基准版本。模型允许选择拒绝，验收没有强制接受、补抽或自动代答。提议提交后画布仍是 revision 1；接受后成为 revision 2。实际 edit 作者、命令与 visit 都属于审阅人 a1，提议人 a2 通过 review→proposal 链保留贡献来源。

最终世界版本 34，数据库有 3 条到访（含程序种图）、1 条提议、1 条审阅、2 条画布修改（含程序种图）、35 条事件；外键错误为 0。原提议、审阅、嵌套 edit、原回执、事件及当前格逐项核对一致。双方木材消耗 0，观察与只读 SQLite 核对均为 `12 = 公共储备 12 + 库存 0 + 实体 0`。

完整输入、模型原始选择和数据库核对见[会话证据](evidence/ITER-0007/live-session.json)，单独报告为[提议人](evidence/ITER-0007/live-proposer.json)与[审阅人](evidence/ITER-0007/live-reviewer.json)。实际运行于 2026-10-25 15:04:32—15:04:51 UTC；报告是已结束的独立验收记录，打开页面不会再调用模型或行动。

| 居民 | 输入 token | 缓存输入 | 输出 token | 任务累计耗时 |
|---|---:|---:|---:|---:|
| a2 | 13,083 | 0 | 147 | 11.19 秒 |
| a1 | 13,282 | 0 | 93 | 7.50 秒 |

居民实际调用 2 次，达到本轮上限。CLI 请求模型为 `gpt-6-astra`，用量来自完成事件，不独立断言内部路由或换算费用。研发 worker 对话单独计数。

## 实现和分工

`newton-ming` 的 GPT-6 worker 完成 C# 协议、世界事务和数据库。新 `consent-v1/r6`、schema 6 继承画布、手记、活动和材料规则；旧 schema 1—5 不迁移。本人或无人来源可直接绘制，其他最后作者的格子必须协商，擦成空白也保留来源。提议只记录意图，由服务器推导目标作者，不修改画布；每次本人到访可提议一次。只有目标作者现场引用自己的到访，才能给一次最终决定。接受将原 patch、标准 edit、审阅、版本、事件和回执一起提交；拒绝不改图、不占绘制名额。提议基准过期后只能拒绝，不能接受旧图。历史追加不可变，公开返回最新 50 提议，本人返回最新 100 提议和审阅，数据库保留完整记录。

`hjqcan` 的 GPT-6 worker 完成 Python 持久任务和模型适配。新 `proposeMosaic` 与 `reviewMosaicProposal` 和原创作模式互斥，能力／候选检查先于模型和动作。提议 patch、原提议、基准、理由与决定均冻结，模型不能在执行中替换。原命令、身份、自己的 visit、精确文本、版本和嵌套 edit 匹配后才结算；提议或拒绝完成不代表已经绘制。查询失败保留原 pending；只有匹配原命令的明确 `STALE_STATE` 拒绝可计费后换 ID 重试，行动内容不变。`MOSAIC_CHANGED` 停止，不改基准、不追加模型调用。

协调者完成共用人类界面、报告和独立验收。草图按来源选择直接发表或提交提议；混合来源提示拆分。目标作者可以写理由、同意或拒绝，草稿和未决请求跨轮询／刷新保留。界面展示原提议、最终决定、实际改图与双方作者；报告分别展示行动前决定、已确认事实和结束画布。公开文字作为纯文本，不能取得执行权限。导入报告仅检查内部一致性，不认证文件外部真实性。

两名 worker 已交付并接受，release 后显式退出，各退出码为 0，无待处置终端。C# 的 14 组自检（15 次执行、2293 条 HTTP、6 次故障退出和 30 库审计）及 Python 的 32 项离线替身自检单独记录，不计入协调者独立验收。Python 自检中的 4 次子进程退出是真实退出，世界仍为文件／内存替身。

## 验收和反馈修订

| 套件 | HTTP | Chrome | 证据 |
|---|---:|---:|---|
| 新协商 | 19 / 19 | 11 / 11 | [HTTP](evidence/ITER-0007/api-results.json) · [Chrome](evidence/ITER-0007/browser-results.json) |
| 原基础 | 17 / 17 | 10 / 10 | [HTTP](evidence/ITER-0007/foundation-http-regression.json) · [Chrome](evidence/ITER-0007/foundation-browser-regression.json) |
| 原通行 | 13 / 13 | 8 / 8 | [HTTP](evidence/ITER-0007/passage-http-regression.json) · [Chrome](evidence/ITER-0007/passage-browser-regression.json) |
| 原持久任务／报告 | 14 / 14 | 8 / 8 | [HTTP](evidence/ITER-0007/mission-http-regression.json) · [Chrome](evidence/ITER-0007/report-browser-regression.json) |
| 原活动 | 15 / 15 | 10 / 10 | [HTTP](evidence/ITER-0007/activities-http-regression.json) · [Chrome](evidence/ITER-0007/activities-browser-regression.json) |
| 原手记 | 17 / 17 | 12 / 12 | [HTTP](evidence/ITER-0007/postcards-http-regression.json) · [Chrome](evidence/ITER-0007/postcards-browser-regression.json) |
| 原画布 | 17 / 17 | 12 / 12 | [HTTP](evidence/ITER-0007/mosaic-http-regression.json) · [Chrome](evidence/ITER-0007/mosaic-browser-regression.json) |
| 合计 | **112 / 112** | **71 / 71** | 不含 worker 自检和两次实际模型任务 |

HTTP 使用实际 C# 服务、SQLite 和隔离端口，模型部分为明确测试替身。覆盖来源与权限、提议不改图、现场与本人到访、一次终态、并发审阅、拒绝及过期、接受前后服务真实退出、任务暂停／恢复、错误回执／查询失败、冻结内容的版本重试、历史限量及旧 populated r5 原规则。每个场景结束后核对材料、外键、事件／回执及重建画布。旧 r5 fixture 来自已结束的 ITER-0006 实际会话，保留两份作品与记录，只替换会话哈希／到期时间为公开测试值并保留 schema 5。原预览不参与故障试验。

HTTP 分成 12 项服务端和 7 项居民任务执行。任务第 15 项初次测试误读根字段 `pending`，正确路径是 `_state.pending.request`；[初次失败](evidence/ITER-0007/api-task-initial-results.json)保留，修正测试后[单项复核](evidence/ITER-0007/api-task-recheck-results.json)通过，产品代码未因此修改。汇总按 19 个不同用例计数，不把重跑重复计算。[拒绝报告](evidence/ITER-0007/test-double-rejected.json)是明确测试替身，不冒充第三次真实模型运行。

Chrome 首次检查通过后，视觉复核发现事件列表投影漏掉 `targetActorId` 与 `decision`，导致目标作者显示 `undefined`，已接受事件误写成拒绝；实际事务、画布和提议详情正确。已补齐投影，并增加目标作者、接受和拒绝文案断言；重跑 11 项协商与 10 项基础界面均通过。[修订前截图](evidence/ITER-0007/world-desktop-before-event-fix.png)和[初次检查](evidence/ITER-0007/browser-initial-results.json)保留，说明原测试覆盖缺口。

最终[世界桌面](evidence/ITER-0007/world-desktop.png)、[世界手机](evidence/ITER-0007/world-mobile.png)、[报告桌面](evidence/ITER-0007/report-desktop.png)、[报告手机](evidence/ITER-0007/report-mobile.png)已视觉复核，窄屏宽度 390px。世界截图是 UI 验收场景，报告截图来自上述真实审阅。JavaScript 异常 0，报告页面世界请求 0。构建 0 错误／警告，Python 编译、JS 语法和 diff 空白检查通过；环境为 .NET SDK 10.0.302、SQLite 3.53.4、Chrome 152.0.7977.82。实现与证据 SHA256 见 [manifest](evidence/ITER-0007/manifest.json)。

## 使用和复现

```bash
bash scripts/run_consent.sh
# 打开 http://127.0.0.1:5085，居民凭据在 .local/consent/access.json
```

本轮已启动新预览并连接 a1，初始世界／画布版本均为 0，画布空白，木材 12。原作者先走到花园 `(1,6)`、记录到访并画图；另一身份对这些格子做草图时会出现修改提议和理由框。提议提交后，原作者现场记录本次到访，写理由并同意或拒绝。再次接受改图需要新的到访；一个已审阅提议不能再次决定。实际模型样本保存在独立验收世界，没有导入当前预览。

旧预览 5080—5084 未重启、未迁移，健康和状态见[记录](evidence/ITER-0007/preview-health.json)，时间为 15:05 UTC：r1 版本 7；r2 版本 19、两段桥；r3／r4／r5 均版本 0。后续居民操作会改变这些状态。

无模型检查入口：

```bash
python3 tests/consent_api.py
node tests/browser/consent.mjs
```

独立真实验收入口为 `python3 tests/consent_live.py --account-one newton-ming --account-two hjqcan`；每次运行会创建新隔离世界、种入明确程序河流并真实调用 GPT-6 两次，结束后关闭服务，不属于普通回归。两份示例 spec 可供 `scripts/run_resident.py` 使用，reviewer 中的 `proposalCommandId` 必须换成所选世界的真实提议 ID；不得直接使用历史验收 ID。恢复必须沿用原 state、spec、URL 和身份，预算包括暂停时间。详见 [tests/README](../../tests/README.md)。

本轮未提交、推送或公共发布；私有凭据、任务状态和完整日志保留在被忽略的 `.local/iter0007/`。新增预览独立使用 `.local/consent/`。

## 采用范围和下一问题

采用“他人格子先提议、目标作者决定、接受原子改图、拒绝保留、原请求恢复”的局部规则。它把协商与直接覆盖区分开，但最后修改者不是完整作品的法律或治理所有者；多作者作品、共同授权、转让、撤回和持续治理仍未实现。

这次对话是一次提议和一次终态决定，没有多轮讨价还价、长期记忆或常驻居民。下一步应检验参与者是否理解该机制、愿意再次创作，以及是否需要更丰富的共同活动；两次预设任务不代替真人反馈，也不扩大账号、持续调用或自主发布范围。
