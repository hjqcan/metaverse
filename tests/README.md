# 最小世界验收

当前 Godot 连续地图另外运行 `npm run test:continuous` 和 `npm run test:godot`。前者验证 r8 权威几何、限速、资源与恢复，后者使用真实 Godot / OpenGL 场景、键鼠输入和故障代理，证据在 `.local/iter0014/`；详见[客户端说明](../clients/godot/README.md)。以下旧场景验收继续保留。

完整普通回归（构建一次，并行执行隔离的 HTTP／Chrome 套件，**不会调用真实模型**）：

当前组合通过 **216 项 HTTP／SQLite、134 项 Chrome**，包括指定设施建设和世界实例任务恢复；结果见 [ITER-0017](../docs/iterations/ITER-0017-results.md)。Godot 专项单独运行，不计入这个总数。

```bash
npm ci --prefix tests/browser --ignore-scripts
npm test
# 只跑一类：npm run test:http 或 npm run test:browser
```

统一检查也包含原始采集任务、连续居民任务和对应报告页面。ITER-0015 基线的 178 项 HTTP／SQLite 与 126 项 Chrome 通过；连续任务单独运行 `python3 tests/continuous_mission_api.py`，报告单独运行 `node tests/browser/continuous-resident.mjs`，两者实际模型调用均为 0。证据和测试替身边界见 [ITER-0015](../docs/iterations/ITER-0015-results.md)。

指定建设任务另加入 `python3 tests/construction_mission_api.py`（13 项真实 HTTP／SQLite）和 `node tests/browser/construction-resident.mjs`（8 项 Chrome）。覆盖平台、指定桥梁、后来者复用、原建造中断恢复与错误回执、权限/占地/预算、冻结目标、建成后到访及只读报告；固定策略或明确测试替身，模型调用 0。

实例任务恢复运行 `python3 tests/instance_mission_api.py`（5 项真实 HTTP／SQLite）：同地址换库不重放、同库迁址原请求恢复、legacy 任务不得收养新实例、损坏绑定不降级、已完成报告不联网。统一入口同时运行服务端的 `continuous_api.py` 和 `world_instance_api.py`；现有预览库不参与这些隔离检查。

需要 .NET 10 SDK、Python 3、Node.js 和本机 Chrome。统一结果与各套件日志保存在 `.local/checks/`；每个套件继续保留自身原始证据和独立服务目录。依赖安装不会自动下载浏览器，`CHROME_PATH` 可指定现有 Chrome。下列单套命令仍可独立运行。

先构建服务：

```bash
dotnet restore src/World.Server/World.Server.csproj --locked-mode
dotnet build src/World.Server/World.Server.csproj --no-restore
python3 tests/foundation_api.py
```

HTTP 验收只使用每个场景自行创建的服务进程、随机 loopback 端口和 `.local/iter0001/api/` 数据目录。覆盖正常规则、身份、竞争、重启、幂等、异常和进程退出；服务停止后，验收器只读核对账本与实际余额。结果、日志和轨迹留在本轮独立目录；包含访问凭据的目录不得提交。

固定居民可独立对正在运行的世界行动：

```bash
python3 scripts/foundation_agent.py --url http://127.0.0.1:5080 --access-file .local/world/access.json --actor a2
```

策略是固定 BFS，只经世界 API 移动，最多 100 个意图、10 分钟，无模型调用。方向选择顺序固定；世界版本冲突后重新观察，网络重试保留原意图 ID。

真实浏览器验收：

```bash
npm ci --prefix tests/browser --ignore-scripts
node tests/browser/foundation.mjs
```

需要本机 Google Chrome，默认路径 `/usr/bin/google-chrome`，可用 `CHROME_PATH` 指定。测试使用独立无痕浏览器上下文，自动创建及关闭专用服务；证据在 `.local/iter0001/browser/`。它实际点击地图及按钮，执行移动／领料／建造，检查丢响应、未送达、原 ID 重试、刷新、断线、服务重启和窄屏布局。所有世界响应来自实际服务，仅在故障场景拦截或丢弃网络请求／响应。

本轮结果以 `docs/iterations/ITER-0001-results.md` 为准。测试成功不等于长期经济、多人容量或公共上线验收。

## ITER-0002 两地通行

构建服务后执行：

```bash
python3 tests/passage_api.py
node tests/browser/passage.mjs
```

专用实例使用 `WORLD_SCENARIO=passage-v1`，目录为 `.local/iter0002/api/` 和 `.local/iter0002/browser/`；不会修改当前预览。13 项 HTTP 包含原子桥段、竞争／幂等、提交前后退出、旧库 fixture 兼容、策略对照和居民恢复原往返起点。8 项真实 Chrome 包含实际建桥通行及丢建造响应后的刷新查询。

`fixtures/foundation-v1-populated.sql` 来自未改动的 ITER-0001 二进制，带一个平台、余额和历史回执；仅会话哈希替换为公开测试字符串 fixture-a1 / fixture-a2，并固定未来到期时间。测试导入隔离数据库，验证新程序启动后逻辑 dump 不变和旧接口继续可用，不触碰原预览库。

旧套件继续运行以检查回归。若当前 shell 设置过 `WORLD_SCENARIO`，用 `env -u WORLD_SCENARIO python3 tests/foundation_api.py` 和 `env -u WORLD_SCENARIO node tests/browser/foundation.mjs`。结果及修订前失败记录见 [ITER-0002 报告](../docs/iterations/ITER-0002-results.md)。

## ITER-0003 持久任务与模型选择

```bash
python3 tests/resident_mission_api.py
node tests/browser/resident.mjs
```

14 项 HTTP 检查使用实际世界服务和明确标注的决策测试替身，不调用模型。覆盖原任务恢复、服务／居民进程退出、互斥、累计预算、身份绑定、非法选择、模型失败及查询错误。8 项 Chrome 检查使用仓库保存的两份真实 GPT-6 报告和 HTTP 用例产生的暂停／失败报告；恶意输入及缺失默认文件是明确的界面扰动，不计为模型运行。两套检查均在 `.local/iter0003/` 下自行创建与关闭专用服务。

以下是独立的真实模型验收，每次执行会使用两个绑定账号各调用一次 GPT-6；不包含在默认检查中：

```bash
python3 tests/resident_live.py --builder-account newton-ming --traveler-account hjqcan
```

它创建新的通行世界，执行建设与零劳动游玩任务，然后只读核对 SQLite 材料账并关闭服务。候选目标由模型选择，因此有效但不符合本轮预设目标的选择也可能使此验收失败；不会偷偷换目标或重试。原始状态及账号调用元数据保存在被忽略的 `.local/iter0003/live/`。当前实际结果见 [ITER-0003 报告](../docs/iterations/ITER-0003-results.md)。

## ITER-0004 地点活动与选择对照

```bash
python3 tests/activities_api.py
node tests/browser/activities.mjs
```

15 项 HTTP 覆盖目录与身份、visit 事务／幂等／并发、提交前后进程退出、到达但未到访、原任务恢复、旧到访不可复用、目录绑定、固定选择、旧 r2 数据及最近 100 条到访。决策来源明确为测试替身或固定程序，外部模型调用为 0。10 项真实 Chrome 使用实际服务，检查人类到访、版本冲突、丢响应后的原 ID 恢复、重启、三类完成事实、真实对照报告及 390px 布局；页面不为查看报告请求世界 API。目录分别为 `.local/iter0004/api/` 和 `.local/iter0004/browser/`，全部服务由验收脚本创建并关闭。

`fixtures/passage-v2-populated.sql` 导出自已结束的 ITER-0003 实际通行世界，包含两段桥、余额、事件和回执。会话哈希替换为公开测试字符串 `fixture-r2-a1` / `fixture-r2-a2`，到期时间固定；保留 `PRAGMA user_version=2`。兼容测试验证新服务启动不改变该旧库的逻辑内容。首次导出遗漏版本 pragma 的失败单独保存，不计为产品失败。

四组真实模型／固定成本对照是另一个显式入口，**每次执行会实际调用 GPT-6 四次**，不包含在上面的常规检查中：

```bash
python3 tests/activity_comparison.py --account-one newton-ming --account-two hjqcan
```

每例创建两个等价初始 r3 世界，冻结目的、目标和预算，最多一次模型选择；不重试、不换账号补抽。八次任务分别核对实际到访、返回、数据库记录与材料守恒，结束后关闭服务。原始证据在 `.local/iter0004/comparison/`。本轮通过总数为 59 项 HTTP、36 项真实 Chrome，另有四次真实选择和八次旅程；详见 [ITER-0004 报告](../docs/iterations/ITER-0004-results.md)。

## ITER-0005 地点共同手记

```bash
python3 tests/postcards_api.py
node tests/browser/postcards.mjs
```

17 项 HTTP 使用真实 r4 服务和显式决策测试替身，覆盖现场／到访／作者约束、原 ID 幂等和改文冲突、并发、提交前后退出、Unicode 标量边界、公开与自己手记数量上限、原任务恢复、旧事实不能结算新任务、预算不足、错误回执及能力验证先于模型。12 项 Chrome 检查实际人类发布、另一居民阅读、按地点筛选、文字注入按原文显示、草稿在轮询／刷新／身份与地点切换时保留、版本冲突、丢响应后的原 ID 恢复、服务重启、真实两居民报告与伪完成拒绝、旧报告及 390px 布局。两套外部模型调用均为 0，目录分别在 `.local/iter0005/api/` 和 `.local/iter0005/browser/`，测试服务自动关闭。

`fixtures/activities-v3-populated.sql` 来自已结束的 ITER-0004 全景模型世界，含两段桥、一次到访、余额及原事件／回执。保留 `PRAGMA user_version=3`，会话哈希替换为公开测试字符串 `fixture-r3-a1` / `fixture-r3-a2` 并固定未来到期时间。隔离导入后验证新服务启动不改旧库逻辑内容。

真实模型验收另有显式入口，**每次执行会实际调用 GPT-6 两次**：

```bash
python3 tests/postcards_live.py --account-one newton-ming --account-two hjqcan
```

它创建同一个独立 r4 世界，让 a1 先留言返回，再让 a2 的决策上下文读取 a1 公开原文、起草回应、到访分享并返回。两份任务在 `examples/postcards/` 冻结，每个最多一次调用，无补抽。记录实际输入、草稿、分享链、返回和材料守恒，结束后关闭服务。原始证据在 `.local/iter0005/live/`；当前两次实际运行通过。与旧套件合计 76 项 HTTP、48 项真实 Chrome，通过率不证明内容的长期体验价值；详见 [ITER-0005 报告](../docs/iterations/ITER-0005-results.md)。

## ITER-0006 花园共同画布

```bash
python3 tests/mosaic_api.py
node tests/browser/mosaic.mjs
```

17 项 HTTP 使用实际 r5 服务、SQLite 和显式模型决策替身，覆盖本人到访／作者／地点、每次到访一个批次、原 ID 数组重排回放与改色冲突、全部格原子提交、并发与版本冲突、提交前后真实进程退出、任务暂停与原 ID 恢复、错误证据和查询失败、预算仅够到访、过期草图停止、公开／自己历史上限、原修改被覆盖后仍是完成事实，以及旧 r4 数据和 r5 手记兼容。12 项 Chrome 覆盖实际人类绘制与另一身份接续、键盘和调色板、8 格上限、草图隔离与保留、真实世界／画布冲突、丢响应刷新恢复、重启、实际历史报告、伪完成拒绝、旧报告及 390px 布局。模型调用为 0；证据分别在 `.local/iter0006/api/`、`.local/iter0006/browser/`，测试服务自动关闭。

`fixtures/postcards-v4-populated.sql` 来自已结束的 ITER-0005 两居民真实手记世界，保留两条到访、两篇原文、余额及原事件／回执，`PRAGMA user_version=4` 不变。仅会话哈希换成公开测试值 `fixture-r4-a1` / `fixture-r4-a2` 并固定未来到期时间。隔离导入后检查新服务启动不改变旧库逻辑内容，原预览库不参与兼容试验。

真实模型验收另有显式入口，**每次执行会实际调用 GPT-6 两次**：

```bash
python3 tests/mosaic_live.py --account-one newton-ming --account-two hjqcan
```

它创建独立 r5 世界，按 `examples/mosaic/` 两份冻结任务依次构图、到访、绘制、返回；每位仅一次模型调用，不补抽、不重试生成。第二位的实际输入必须含第一位已提交格子；核对连续河流、在空白格添花草、保留原图及作者、原到访／绘制链、返回与数据库材料守恒。结束后关闭服务，证据在 `.local/iter0006/live/`。本轮两次通过，连同回归共 93 项 HTTP、60 项真实 Chrome；详见 [ITER-0006 报告](../docs/iterations/ITER-0006-results.md)。

## ITER-0007 画布协商修改

```bash
python3 tests/consent_api.py
node tests/browser/consent.mjs
```

19 项 HTTP 使用真实 r6 服务与 SQLite，模型选择为显式测试替身。覆盖他人来源强制协商（含擦白）、服务器推导目标、提议不改图、本人现场到访、权限和一次终态、接受原子性、拒绝及过期、并发、接受提交前后真实退出、原任务恢复／假回执／查询失败、普通世界版本冲突冻结内容重试、历史限量与旧 r5 规则。11 项 Chrome 检查实际两身份提议与审阅、作者及事件文案、拒绝／过期、草稿／丢响应恢复、重启、真实历史报告、假证据与旧报告、390px。两套模型调用为 0，证据在 `.local/iter0007/api/` 与 `.local/iter0007/browser/`，服务自动关闭。

`fixtures/mosaic-v5-populated.sql` 来自已结束的 ITER-0006 两居民世界，保留两条修改、画布及原到访／回执／事件。会话哈希替换为公开 `fixture-r5-a1` / `fixture-r5-a2` 并固定到期时间，保留 `user_version=5`。隔离导入验证新程序启动不改旧库逻辑内容，原 r5 仍可直接覆盖其他作者。

本轮 HTTP 分两批执行，初次任务第 15 项误读状态字段，修正测试路径后单项复核通过；汇总 19 个不同用例。首次 Chrome 漏测事件文案，视觉复核发现作者／决定投影遗漏；修复后补断言并重跑协商及基础界面。初次记录和截图保留，详见 [ITER-0007 报告](../docs/iterations/ITER-0007-results.md)。

以下独立入口**每次实际调用 GPT-6 两次**，不属于普通回归：

```bash
python3 tests/consent_live.py --account-one newton-ming --account-two hjqcan
```

它用程序通过正常 HTTP 让 a1 种入三格河流并返回（明确不是模型作品），再让 a2 提议改一个端点，a1 独立选择同意或拒绝；均只调用一次，没有补抽。按实际决定核对原提议输入、原命令链、最终格子来源、双方返回与材料／数据库。若提议未成功，不启动第二次调用。结束后停服，证据保存在 `.local/iter0007/live/`。静态报告页面读取已完成会话，无模型或世界请求。最新合计 112 项 HTTP、71 项 Chrome，不含 worker 自检和两次真实调用。

## ITER-0008 完整提议收件箱

```bash
python3 tests/inbox_api.py
node tests/browser/inbox.mjs
```

17 项 HTTP 使用实际 r6 服务与 SQLite，覆盖最近 50／本人 100 条之外的原待办、认证范围、完整计数、状态／游标、新插入与审阅变化、严格查询、GET 逻辑库不变、旧 populated r6 与 r1—r5、原引用详情进入新任务、错误绑定先于模型、详情较新时刷新观察、旧服务回退及原任务恢复。模型选择是明确测试替身。13 项真实 Chrome 使用实际服务生成程序历史，覆盖默认待办、分页、输入焦点与选区、503 保留内容、迟到筛选／身份响应、到访入口、旧提议接受、旧服务限定列表、丢响应恢复、重启、真实历史报告及 390px。两套模型调用 0；证据在 `.local/iter0008/api/` 和 `.local/iter0008/browser/`，测试服务自动关闭。

`fixtures/consent-v6-populated.sql` 来自已结束的 ITER-0007 实际会话，保留原三格河流、端点接受后的画布、提议、审阅、到访／回执／事件；session 哈希替换为公开 `fixture-r6-a1` / `fixture-r6-a2` 并固定到期时间，保留 `user_version=6`。测试验证无 schema 迁移及逻辑内容变动。

新 HTTP 首次两项断言误把命令回执 `action` 字段套到详情，按冻结契约修正后全过。旧协商 Chrome 显式选择 all/all，等待新增独立列表完成，已处理按钮检查不可见而不是节点不存在，以兼容稳定节点复用。初次失败均保留，见 [ITER-0008 报告](../docs/iterations/ITER-0008-results.md)。合计 129 项 HTTP、84 项 Chrome，不包含 worker 自检和真实模型调用。

以下独立入口**每次真实调用 GPT-6 两次**：

```bash
python3 tests/inbox_live.py --account-one newton-ming --account-two hjqcan
```

沿用 `examples/consent/` 的有界目的，在隔离世界先以正常 HTTP 种入三格河流，再让 a2 一次真实调用发表提议并返回。程序插入并拒绝 51 条新提议（含往返 222 条命令），使原待办退出最近 50 条且不改图。a1 由完整收件箱找到原引用，详情实际进入一次模型输入，独立接受或拒绝并返回。明确区分程序历史、模型决定与世界事实，无补抽；结束后停服，证据在 `.local/iter0008/live/`。新本机预览 `bash scripts/run_inbox.sh` 使用 5086 / `.local/inbox/`，与已结束真实会话分开。

## ITER-0009 当代入驻导览

```bash
python3 tests/entry_guide_api.py
node tests/browser/entry.mjs
```

9 项 HTTP 使用实际服务与 SQLite，覆盖无桥／半通路／两段桥、后来者首次观察后实际复用通路与到访返回、本人位置和零步路线、公共木材耗尽后仍可零材料到访写手记、导览读取及重启不改逻辑库、r1—r5 与旧 populated r2、公开模型输入白名单及旧任务兼容。10 项 Chrome 覆盖同一通路在人类界面的真实操作、只选地点不行动、材料限制、断线暂停、身份切换、异常导览、旧服务回退、重启与 390px。固定程序和决策测试替身均明确标记，真实模型调用为 0。

证据在 `.local/iter0009/api/` 与 `.local/iter0009/browser/`，测试服务自动关闭；合计 138 项 HTTP、94 项 Chrome。初次任务输入测试缺少替身元数据、随后预算字段断言路径错误，以及首次页面缺少内边距均保留记录，详见 [ITER-0009 报告](../docs/iterations/ITER-0009-results.md)。新本机预览用 `bash scripts/run_entry.sh`，5087 / `.local/entry/`；沿用 r6，不升级 schema 或修改材料规则。

## ITER-0010 原始开局与树木采集

```bash
python3 tests/wilderness_api.py
node tests/browser/wilderness.mjs
```

16 项 HTTP／SQLite 验证分散零库存、无公共领料、有限树木与采空、距离与身份、原命令并发／回放、事务回滚与提交前后进程退出、最后一份木材竞争、采集后造桥及另一居民复用、重启不再生、导览障碍、公开输入、旧库兼容和无场景参数时的新世界默认值。每例停服后独立核对自然储量、库存、实体和材料账。11 项真实 Chrome 验证选树、砍取、材料变化、真实搭建、分散身份、丢响应刷新恢复、错误节点回执保留原命令、断线停止、重启与 390px。全部真实模型调用0。

证据在 `.local/iter0010/`；初次 Chrome 异步断言过早读库存，完整运行新增默认场景用例曾复用同一测试目录，这两项测试问题保留原记录，修正后复验。当前汇总 154 项 HTTP、105 项 Chrome，详见 [ITER-0010 报告](../docs/iterations/ITER-0010-results.md)。历史 foundation 套件显式指定原场景；默认新服务和 `npm start` 采用原始开局，已有数据库仍按原场景读取。

## Godot 原生客户端

`dotnet build src/World.Server/World.Server.csproj --no-restore` 后，运行 `GODOT_BIN=/path/to/godot npm run test:godot`。需要 Godot 4.7.2 和 Linux `xvfb-run`，当前连续地图的结果及截图保存在 `.local/iter0014/godot/`（ITER-0011 的历史证据仍保留）。此入口独立于不要求安装游戏引擎的 `npm test`，不能把普通 Chrome 回归写成 Godot 验收。

真实 Godot OpenGL 渲染、实际场景鼠标／键盘输入、隔离 .NET / SQLite 服务及故障代理验证采集、搭建、跨岸复用、身份、状态冲突、错误回执、读失败、丢响应与客户端／服务重启。所有测试子进程和代理结束时停止，模型调用0；仅无头导入不算视觉验证。


## ITER-0018 实例与原命令恢复

`python3 tests/world_instance_api.py` 为8项实际 HTTP / SQLite 检查；`python3 tests/instance_mission_api.py` 为5项任务持久绑定检查，两者已加入 `npm test` 的普通回归。当前完整组合为216项 HTTP、134项 Chrome，全部外部模型调用0。作者自测、独立反例复验与已有预览状态见 [ITER-0018 报告](../docs/iterations/ITER-0018-results.md)。

`npm run test:godot` 依次执行共享记录（6场景、400断言）、实例恢复（9组、27断言）、连续场景（9组、56断言）与导航（5组、42断言）。前两套使用真实无头 Godot 进程；后两套使用真实 OpenGL 渲染和鼠标／键盘输入。服务均在隔离目录和随机端口运行；实际身份及数据库核对是过桥验收的一部分，不能只根据画面位置判定另一居民完成。

实例用例包含同地址换库、原世界迁址与会话轮换、旧格式和损坏记录、不制造业务回执的前置条件失败；任务用例还保留原起点、目标与累计预算。未更改已有预览数据库，旧库升级试验使用独立的旧程序建库。
