# ITER-0022 证据索引

这里保存本轮可公开的测试结果和画面，不含数据库、凭据或居民私有恢复文件。`provenance.json` 逐项记录本机原始文件位置及SHA256；标为 `exact` 的文件按原字节复制。失败记录保持失败标记，不能把后续单项复验改写成首次全过。

| 层次 | 入口 | 解释 |
|---|---|---|
| 构建者HTTP | [首次](author-api-first.json)、[故障复验](author-api-fault-recheck.json)、[时钟边界](author-time.json) | 首次8项中测试辅助调用错误1项；修正后单项复验。最终组合回归另列 |
| 最终组合回归 | [首次组合](author-full-first.json)、[分项与复验汇总](author-final-composite.json)、[材料8项](author-api-final.json)、[时钟2项](author-time-final.json)、[Python11项](author-python-final.json) | 278项HTTP／SQLite通过；154项旧Chrome通过，新生成器首次失败后单独复验8项通过，共162项。汇总内嵌各原始结果并保留哈希 |
| 新Chrome默认入口 | [首次生成器失败](author-browser-generator-first.json)、[修正后8项通过](author-browser-final.json) | 只改测试调用的类名前缀；默认路径重新生成真实世界任务报告后执行浏览器检查，产品文件保持独立验收版本 |
| 构建者原生 | [首次恢复失败](author-godot-first-recovery.json)、[修复后](author-godot-recovery-fixed.json)、[完整8套](author-godot-combined.json)、[最终标签复验](author-godot-label-final.json) | 完整回归50组705断言；之后仅移动来源文字，UI21断言再验 |
| 独立构建worker自检 | [交付](worker-handoff.json)、[首8项](worker-eight.json)、[最后4项](worker-final-four.json) | 共11个不同新场景，版本与增量范围明确列出；不是独立QA |
| 独立服务验收 | [核心](qa-core.json)、[协议／空间及初次失败](qa-boundary-first.json)、[原命令恢复及旧规则初次失败](qa-boundary-recovery.json)、[旧规则复验](qa-boundary-legacy-final.json) | 10组功能场景通过，核心文件另含真实采集形成的初态；初次失败分别保留 |
| 独立Godot验收 | [首批](qa-godot-first.json)、[原事件与UI复验](qa-godot-events-ui-final.json)、[最终标签UI复验](qa-godot-label-final.json) | 6组，包括真实原body重试、损坏记录、同URL换库及真实采空初态下的本人平台；最后仅标签位置变化，实际UI再次独立通过 |
| 独立Python验收 | [CLI及原记录](qa-python-cli-records.json)、[累计预算](qa-python-budget.json)、[到期与原历史](qa-python-expired-original-history.json)、[未用权限的普通任务](qa-python-unused-permission.json) | 7组通过；前两份保留整体false及夹具修正边界，不能将局部复验写成完整重跑 |
| 独立Chrome验收 | [8项结果](qa-browser.json) | 使用测试方实际完成、暂停、到期、查询耗尽及普通任务报告；无世界请求或JS错误 |
| 独立验收总表 | [逐项证据与源码版本](qa-summary.json) | 服务10组、Godot6组、Python7组、Chrome8项；包含每份实际接受的分项、源码冻结版本与测试方停服检查 |
| 最终源码归属 | [独立只读核对](qa-final-source.json) | 对47个交付文件、此前36份原始复制及作者回归总数逐项核对通过；随后仅在本目录收录此审计并加索引。总表保留较早时点，不覆写历史记录 |
| 实际启动 | [脚本验证](author-launch.json) | 隔离端口与数据，初态关闭→停服开启→同实例重启，测试后停服 |

[最终原生画面](godot-material-final.png)与[排队画面](godot-material-queued.png)来自真实Godot运行。[桌面报告](report-material-desktop.png)和[390px报告](report-material-mobile.png)来自最终默认生成入口，实际固定任务28条命令、44次查询、3木材。客户端与研究者的审阅不计为额外独立执行，固定目标选择不计为真实模型调用。所有本轮世界测试的真实模型调用均为0。

[交付源码清单](candidate-source.json)列出本次变更的文件与SHA-256，不包含本目录，避免证据自身递归。各试验使用的更早候选仍以原记录和独立总表为准；标签与启动文案修订、测试调用修正不冒充全部试验在最终版本重新执行。

产品结论、运行方式、最终组合与验收范围见[结果报告](../../ITER-0022-results.md)。有限12木材耗尽后仍会拒绝新需求；这些证据不证明永久供给、公平身份识别或完整元宇宙已完成。
