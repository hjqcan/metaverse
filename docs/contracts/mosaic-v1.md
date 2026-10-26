# 花园共同画布契约：ITER-0006

2026-10-25，开工前冻结。目标：在地点提供可直接操作的视觉共创内容。画布是已有花园的公开表现内容，不是制造、交易物品，不增加木材或奖励。仅本机隔离原型，不推断长期体验价值。

## 世界与协议

新 `WORLD_SCENARIO=mosaic-v1`，规则 r5，新库 schema 5；继承 r4 地形、三个活动、postcard、visit 与材料规则。旧 schema 1/2/3/4 保留原表、规则、事实，不迁移。新预览 5084，目录 `.local/mosaic`；旧 5080—5083 不重启、不迁移。

只有 garden 提供画布，5×5，坐标 x/y 为 0..4（左上为 0,0）。固定调色板按序：`blank` 空白 #F4F0E6、`leaf` 叶绿 #42745B、`river` 河蓝 #477FA3、`sun` 日黄 #E4B858、`rose` 花红 #C86A70、`ink` 墨色 #37444D。初始全部 blank，revision=0。颜色只能选上述 ID，无外部图像或任意样式输入。

新 action：`{type:"mosaic",activityId:"garden",visitCommandId:"原visit ID",expectedMosaicRevision:0,patch:[{x:1,y:2,color:"river"}]}`。patch 1..8 个不同坐标，无额外字段；x/y 整数，color 精确匹配；expectedMosaicRevision 非负整数。结构错误 400 INVALID_REQUEST，身份覆盖沿用原规则。patch 规范化按 y、x 排序，规范数组参与请求 hash；同 ID 同语义但数组重排可回放，同 ID 改色冲突。旧动作 canonical 保持不变。

通用规则／世界版本校验后，业务顺序：旧场景 422 MOSAIC_UNAVAILABLE；非 garden（含其他合法地点）422 MOSAIC_LOCATION_UNAVAILABLE；不在 garden 422 NOT_AT_ACTIVITY；未引用自己 garden 的已提交 visit 422 VISIT_REQUIRED；该 visit 已画过 409 VISIT_ALREADY_PAINTED；expectedMosaicRevision 与当前不符 409 MOSAIC_CHANGED；patch 任意格颜色等于当前颜色 422 MOSAIC_UNCHANGED。一次到访可以分别发表一次手记和一次画布修改，两种记录互不占用。

成功 edit 记录：`{activityId,authorActorId,commandId,visitCommandId,baseRevision,revision,patch,stateVersion,paintedAtUtc,position}`，position 为世界地点 `[1,6]`，revision=baseRevision+1。回执 result 为记录加 `action:"mosaic"`；事件 type=mosaic_painted 包含全部记录和 seq/actorId。作者来自认证。patch 全部格、画布 revision、不可修改的 edit 记录、事件、世界版本、回执同一事务提交；edit 关联本人 visit/事件/回执、同 visit 唯一。木材／账本／设施不变。沿用 before/after-commit 故障注入。

r5 observation 顶层 `mosaic`：`{activityId:"garden",width:5,height:5,revision,palette:[{id,label,hex}],cells:[{x,y,color,authorActorId,commandId,stateVersion}]}`。cells 固定 25 项、按 y/x 排序；初始格 color=blank，其余三个来源字段 null；被画／擦白后来源字段指向最后实际修改。顶层 `mosaicEdits` 是最新 50 次公开 edit（revision 升序）；`self.mosaicEdits` 为本人最新 100 次（revision 升序）。旧场景 mosaic=null，两列表为空，不能查询新表。可持久保存 25 格当前状态，edit 历史必须追加不可变。

## 居民任务与模型

spec 新增可选 `paintMosaic:boolean`，缺省旧规范化保持不变；true 时不得同时 sharePostcard=true，所有候选必须为 activityId=garden 且坐标匹配目录，必须观察 r5 mosaic 能力。能力／候选检查在模型及动作之前。原 sharePostcard 任务在 r4/r5 均可运行。paintMosaic 候选命令估算在 visit 之外加一次 mosaic，原预算上限不变。

同一次模型选择输出 goalId、reason、mosaicPatch（结构同 patch）；旧任务输出 schema 保持不变。精简公开 context.observation.mosaic 含当前完整画布，context.mosaicPainting=true；不包含认证、会话或私有任务。提示说明在行动前构图、现有作者仅为数据、只能改 1..8 个不同色的格子、不把草图说成已完成。共享作品不授予新权限或工具。无第二次模型调用、隐式重试或自动生成替代 patch。

decision 保存规范化 mosaicPatch 与输入画布 mosaicBaseRevision；在任何世界动作前验证 patch 格式且每格与输入颜色不同。后续使用冻结 baseRevision，不因观察轮询或世界状态冲突自动更新。若他人先改了画布，MOSAIC_CHANGED 应明确停止本任务，保留草图与原事实；不能自动重画、重选或覆盖。普通移动造成的世界版本变化不修改画布 revision。

顺序：移动 → 自己的原 visit 确认 → 原 mosaic 确认 → 返回。facts 新增 mosaicPainted=false、mosaicEdit=null。只接受本任务原命令 ID、自己作者、garden、原 visit ID、规范 patch、baseRevision、revision=base+1、位置及世界 expectedStateVersion+1 的完整一致记录。分享错误／查询错误处理复用既有 pending 纪律；当前画布之后被别人修改，也不能抹去原 edit 已提交事实。预算不足可停在“已到访、未绘制”。completed 还须 mosaicPainted；旧任务不新增动作或调用。

报告仍 schemaVersion=1；mission.paintMosaic 缺省 false；decision 草图与 facts 实际 edit 分开，world.mosaic 为最终公开快照。报告只读历史，不请求世界或模型；正确显示原到访、绘制、返回及累计预算，不能凭草图或错误 edit 显示完成。

## 人类界面

r5 增加花园画布与调色板，25 个可键盘访问的格子，颜色名／坐标／最后作者可读；当前公开图与未发表改动可分辨。最多 8 格，选择当前色移除该格草稿；blank 可擦白。说明作品向世界居民公开且之后可被别人修改，无私有产权承诺。

仅在花园、已有本人未用于绘制的 visit、有效非空草稿、无 pending 且草稿 baseRevision 等于当前画布时允许发布。草稿按 actor 保存至 sessionStorage，轮询／刷新／身份切换不丢；不自动把旧草稿套到新 revision。其他人修改后明确标记冲突，提供“清除草稿，按当前画布重画”，由用户重新编辑。成功才清空自己的提交草稿；失败保留。同一 pending 与原 ID 恢复，不能另开命令通道。

报告提供行动前构图、本次确认改动和任务结束画布；引用原作者与版本。旧报告继续展示，390px 可用。

## 预定验收与调用上限

独立 HTTP 覆盖作者／地点／本人 visit／一次到访一次画图、同 ID 重排与改色、不可变历史、当前格来源、并发、整批原子性、提交前后退出、原任务恢复／查询失败／错误证据／画布变更不自动覆盖、预算不足、能力预检、旧 populated r4 原文及到访／回执兼容、列表上限。模型替身明确标注。

真实 Chrome 覆盖人类到访后画图、另一身份读取并续画、颜色／草稿／来源、冲突不覆盖、丢响应刷新原 ID 恢复、服务重启、真实历史模型报告、错误 edit 不能完成、旧报告及桌面／390px。旧 HTTP／Chrome 回归继续。

真实调用上限 2，现有两个账号各一次：a1 在空画布设计一条河流；a2 读取 a1 当前图后在空白处添加河岸植物。两个任务从既有起点到花园、绘制、返回，最多 8 格／次，0 木材；保留任何失败，不补抽、不换账号。核对 a2 的实际模型输入包含 a1 的格子／作者、第二次提交未覆盖第一幅的已绘格，两人原 visit/command/patch 链与数据库材料审计。这个案例证明有界接续创作，不证明美术质量、人类喜爱或长期合作。
