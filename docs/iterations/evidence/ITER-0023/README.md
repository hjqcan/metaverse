# ITER-0023 原始验证记录

这些文件是本轮实际运行产物的只读归档，不是可执行脚本、正式世界存档或线上认证。原路径、文件长度和SHA256由`provenance.json`列出。JSON按原字节保存，不把早期false改为true；完整解释见[结果报告](../../ITER-0023-results.md)。

| 证据 | 内容 |
|---|---|
| [最终源码清单](candidate-source.json)、[归档来源与哈希](provenance.json)、[作者收尾检查](author-final-audit.json) | 37个源码/测试/文档文件的最终哈希；原件逐字节归档、链接检查及测试服务退出 |
| [独立最终归属审计](qa-final-source.json) | 核对37个最终文件、此前39份归档、全部43套HTTP/Chrome及9套Godot原结果；本审计作为第40份证据随后归档，未改已有记录 |
| [最终完整组合](author-full.json)、[含全部原始分项](author-full-expanded.json) | 25套HTTP/SQLite 293项、18套Chrome 170项全部通过，0跳过；当前构建、默认真实基线入口 |
| [最终Chrome默认入口](author-browser-default.json) | 现场生成耗尽世界和实际CLI报告后完成8项检查 |
| [默认HTTP入口](author-api-default.json) | 不依赖私有快照，通过真实世界命令形成耗尽基线后运行2组 |
| [worker完整13组](worker-python-full.json)、[移交](worker-handoff.json) | 构建者自检，六文件前后哈希一致，含实际旧服务兼容且无跳过 |
| [worker默认入口](worker-default-entry.json) | 实际新建耗尽基线；1项通过，缺旧DLL的一项明确跳过，不能计作2项通过 |
| [a2实际报告](resident-a2.json)、[a3原引用回复](resident-a3.json) | 固定输入CLI，各33命令、37查询、0木材；1次固定策略回调，外部模型调用0 |
| [查询4次后的报告](resident-query4.json) | 已确认手记仍在报告中，整个任务状态为budget_exhausted，未伪造返回 |
| [独立Python汇总](qa-python-summary.json)、[CLI/恢复原记录](qa-python-cli-recovery.json)、[预算/旧服务复验](qa-python-budget-legacy.json) | 6组通过；首次整体false来自QA旧二进制清单字段错误，采纳的分项明确分列 |
| [独立服务端汇总](qa-core-summary.json) | 7组验收及所采纳原始分项；原自然运行所属整体false来自后续夹具错误，分项与复验分列 |
| [自然双作者](qa-core-natural.json)、[边界与恢复](qa-core-boundaries.json)、[采用与旧规则](qa-core-adoption-legacy.json) | 同一实际耗尽基线分支、原404回执及实体/库存/来源保持；故障探针与自然运行分开 |
| [作者原生恢复](author-godot-core.json)、[首次输入失败](author-godot-initial-failure.json)、[最终UI](author-godot-final-ui.json) | 早期问题原样保留，修复与最终源码归属在结果报告说明 |
| [最终全部Godot](author-godot-all.json)、[最终手记套件](author-godot-notes-final.json) | 9套56组767断言通过，运行前后源码保持；含新6组62断言 |
| [独立Godot汇总](qa-godot-summary.json) | v1恢复、v3原桥校验、v4最终界面的准确归属；10条采纳分项含重复恢复复验，不能当作10个不同场景 |
| [独立原生恢复](qa-godot-recovery.json)、[旧动作](qa-godot-old-actions.json)、[原桥证据](qa-godot-bridge-evidence.json) | 新旧原请求、同地址换库、原事件/手记/桥和损坏记录检查 |
| [长文UI](qa-godot-long-ui.json)、[实际指针输入](qa-godot-pointer-input.json) | 160字首发和另一居民原引用接写；24检查及12处按钮命中。滚轮漏release属于QA输入修正 |
| [作者Chrome](author-browser-initial.json)、[独立Chrome](qa-web.json) | 8项作者与11项独立报告页检查；固定文本、异常导入、390px、重复读取和零世界写入 |
| [最终报告导入](qa-web-final.json) | 再用独立CLI、queries3/4及作者queries4做5项检查，合计16项独立Chrome检查 |
| [独立总表](qa-independent-summary.json)、[独立服务退出](qa-services.json) | 每个采纳分项的原路径/哈希、源码归属与限制；后续最终源码/提交审计另存，不覆盖此表 |
| [Godot双作者](godot-reply.png)、[长文滚动](godot-long-reply.png) | 实际原生窗口截图 |
| [桌面报告](report-desktop.png)、[390px报告](report-mobile.png) | 实际Chrome截图 |

固定任务正文、测试替身和故障注入不代表真人喜欢或模型自主创作。数据库和访问凭据不随此目录发布；原请求及恢复片段是故障复核证据，不作为新任务输入。来源耗尽后文本活动可用，不代表持续材料入口已解决。
