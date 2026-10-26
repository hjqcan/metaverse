# ITER-0024 原始验证记录

本目录保存实际运行产物的只读副本。`provenance.json`列出原路径、长度与SHA256；早期false结果按原字节保存，不改为true。它不是运行存档或线上认证，数据库及访问凭据不随目录发布。最终范围见[结果报告](../../ITER-0024-results.md)。

| 证据 | 范围 |
|---|---|
| [原基线核对](qa-preflight.json) | 原ITER-0023耗尽、两条手记、616回执及WAL完整性 |
| [独立自然路径core-v1](qa-core-natural-v1.json) | 同实例第5个平台、持续生产到27，保留旧实体/手记/私人库存/回执 |
| [实际小数反例](qa-policy-fraction-counterexample.json) | core-v1错误接受REAL政策时间，明确隔离损坏库与0业务命令 |
| [独立core-v2四组](qa-core-v2-adoption-production.json) | 原反例及5种字段复验、v1自然状态748之后继续生产到30、采用与生产提交前后原子性、旧服务冷启动 |
| [独立队列与容量](qa-core-v2-queue-capacity.json) | 部分领取跨采用、原期限/FIFO/别名/取消/真实到期，以及满仓跳过、12秒停服与下一周期不补发 |
| [作者core-v1完整12组](author-core-v1.json) | 与最终core-v2分列，未把旧二进制结果改记为新版 |
| [作者小数探针初次失败](author-policy-type-initial-failure.json)、[修正驱动后通过](author-policy-type-fixed.json) | 离线CLI公开错误输出预期修正；产品严格类型修复未回退 |
| [worker最终10组](worker-python-full.json)、[交付](worker-handoff.json)、[默认入口](worker-default-entry.json) | 作者自检、原c6a2406 Python生成未决任务、真实基线，版本边界原样保留 |
| [worker修复版续跑](worker-core-v2-continuation.json)、[补充交付](worker-core-v2-addendum.json) | 原CLI世界不重建，a3按原预约继续领取及后续生产 |
| [磁盘满失败](worker-disk-full-failure.json) | 环境失败保持false，不以新副本运行冒充原任务恢复 |
| [真实平台任务](resident-platform.json)、[查询4次报告](resident-query4.json) | 固定程序、真实命令；已确认预约与整个任务预算耗尽分开 |
| [作者完整Godot](author-godot-all.json)、[最终核心上的4组](author-godot-v2.json) | 10套60组814断言；新4组47断言另在最终core-v2执行，DLL归属保留 |
| [作者Chrome初次失败](author-browser-initial-failure.json)、[修正文字预期后10项通过](author-browser-report-input.json) | 输入为真实CLI及queries4产物，未把合成错误报告称真实业务活动 |
| [Godot本人平台](godot-platform.png)、[原桥旧手记](godot-old-notes.png) | 实际原生窗口画面 |
| [桌面](report-desktop.png)、[390px](report-mobile.png)、[预算耗尽](report-query4.png) | 实际Chrome画面 |
| [最终作者覆盖](author-final-coverage.json)、[原整套运行](author-full-initial.json)、[展开报告](author-full-expanded.json) | 316 HTTP／180 Chrome覆盖；原整套false与专项通过分开，0跳过 |
| [默认入口初次错误](author-browser-default-initial-failure.json)、[缺报告错误](author-browser-default-missing-report.json)、[最终10项](author-browser-default-final.json)、[真实输入两组](author-browser-default-cli-inputs.json) | 方法名与实际报告导出两处测试接线修正，没有后续产品变更 |
| [最终核心13组](author-core-v2-full.json)、[最终Python10组](author-python-v2-full.json) | 真实默认基线、旧版本任务；完整组合中的原始结果 |
| [独立总表](qa-independent-summary.json)、[损坏存储](qa-core-v2-invalid-storage.json) | core-v2共7组；10种结构／事件损坏拒绝及原库保持 |
| [独立Godot界面／恢复](qa-godot-ui-recovery.json)、[旧未决](qa-godot-old-pending.json)、[初次驱动错误](qa-godot-initial-failure.json) | 4组，真实旧程序4动作×2断线8组合 |
| [独立Python实际CLI及后段失败](qa-python-cli-and-initial-failure.json)、[预算／政策复验](qa-python-budgets-and-policy.json)、[旧未决](qa-python-old-pending.json) | 只接收初次run已完成actual_cli；5组含真实503、查询预扣、8个旧任务恢复组合 |
| [独立Chrome](qa-web.json)、[首次退出检查错误](qa-web-initial-failure.json) | 独立驱动8项；实际CLI报告、坏政策、390px、无业务API请求 |
| [独立桌面](qa-report-desktop.png)、[独立查询预算手机页](qa-report-query4-mobile.png) | 协调者与QA分别检视的实际Chrome截图 |
| [源码核对](final-source-audit.json) | 产品冻结不变，两个测试接线差异列明 |
| [临时文件清理](cleanup-summary.json) | 完成套件自动回收临时二进制，原世界和结果保持；逻辑长度不冒充实际磁盘释放量 |

固定输入及故障探针不证明真人喜爱、现实独立控制主体、无限空间或长期经济。来源观察不是个人取得材料的证明；导入页面只核对报告自身一致性。
