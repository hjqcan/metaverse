# 事务与命令身份实验

日期：2026-10-25。实验：`foundation-transactions-v1`。状态：**本机实验通过，适用范围见下文**。

## 研究问题和方法

验证有限资源的制造在竞争、重复和进程退出时，能否保持资源、产物、事件与回执一致。固定配方为 **2 单位材料 → 1 件物品**；这是存储探针，不是后续平台配方。每个场景使用独立临时数据库，完成后只删除本次创建的目录。

负面对照先在事务外读取材料，两条线程通过 Barrier 确认都读完，再分别提交扣料与产物。候选方案每个操作用独立连接，先取得短写事务，再查回执、校验当前库存、条件更新、创建物品／事件／回执，最后提交。SQLite 的事务与 deferred 升级规则见[官方驱动说明](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions)。

## 实际结果

| 场景 | 输入／故障 | 观察结果 | 判定 |
|---|---|---|---|
| 错误实现负面对照 | 2 单位材料，2 个同时读取旧余额的请求 | 余额 0，物品 2，折算材料 4；余额虽非负仍增发 | 成功检出预期缺陷 |
| 有限资源竞争 | 10 单位材料，32 个命令 | 成功 5，拒绝 27，余额 0，物品／事件 5，回执 32 | 通过 |
| 同键重试及异参 | 同一命令并发提交 16 次，再改变数量 | 16 次得到相同成功结果，只产物 1／回执 1；异参返回冲突且无写入 | 通过 |
| 旧状态版本 | 成功后用新 ID 携带旧版本，再重试拒绝 | 返回并保持 VERSION_CONFLICT；无新增产物或扣料 | 通过 |
| 居民作用域 | 两居民使用相同 commandId | 两份独立回执，按各自命令各执行一次 | 通过 |
| 材料不足 | 只有 1 单位材料 | 完整拒绝，材料仍 1，物品／事件 0，拒绝回执 1 | 通过 |
| 扣料后异常 | debit 之后抛异常 | 事务回滚，回执为空；原 ID 重试后只执行一次 | 通过 |
| 提交前进程退出 | 子进程写完所有记录、commit 前直接退出，退出码 81 | 重开仍是原库存，无产物／事件／回执；原 ID 可执行 | 通过 |
| 提交后进程退出 | commit 后返回调用者前退出，退出码 82 | 重开已存在一套结果；原 ID、旧预期版本重试返回原成功结果 | 通过 |

原始结果：[transactions-v1.json](evidence/transactions-v1.json)。`passed: true` 在负面对照中表示**成功复现预期失败**，不是错误算法正确。程序在断言不满足时非零退出。

成功场景同时核对材料非负、材料＋产物折算值守恒、事件净额与余额一致、版本／产物／回执数量。没有只以返回 HTTP 成功或控制台文字判断结果；本探针根本没有 HTTP 层。

## 环境与复现

实测：Ubuntu 24.04.4 LTS，SDK 10.0.302，runtime 10.0.10，Microsoft.Data.Sqlite.Core 10.0.10，SQLitePCLRaw.bundle_e_sqlite3 3.0.5，`SELECT sqlite_version()` 为 **3.53.4**，WAL，`synchronous=FULL`。依赖的精确解析版本及内容哈希见 [packages.lock.json](../../../experiments/FoundationProbe/packages.lock.json)。源文件及证据校验值见 [manifest.json](evidence/manifest.json)。

在仓库根目录执行：

```bash
dotnet restore experiments/FoundationProbe/FoundationProbe.csproj --locked-mode
dotnet run --project experiments/FoundationProbe --no-restore -- --output .local/experiments/transactions-rerun.json
```

本轮使用已有本地 NuGet 缓存完成离线还原，没有下载依赖或升级系统：

```bash
dotnet restore experiments/FoundationProbe/FoundationProbe.csproj --locked-mode --source /home/wangjunfeng/.nuget/packages --ignore-failed-sources -p:NuGetAudit=false
```

离线关闭 NuGetAudit 仅为不请求外部审计服务，**不代表依赖安全审计通过**。复现输出写新文件，保留本轮原始证据；临时数据库由程序自行创建及清理。

## 能采用什么，不能推断什么

可以采用短事务、条件扣料、持久幂等回执及原命令查询这条实现路径。不能声称数据库事务自动解决任意规则套利：配方本身若不守恒，事务只会可靠地执行错误配方。

本实验的一库即一世界；ActorId 是调用参数，没有认证，因此“居民作用域”不证明身份防冒充。库存只有一个并发版本、即时制造、一种材料、没有回收。它不覆盖规则升级、资源转移、作业调度、多实例服务、授权视图、事件推送与 UI。进程直接退出绕过托管清理，但不等于主机断电、磁盘损坏或文件系统故障；32 个竞争请求也不是压测结果。

此处事务实现约 300 行用于检验假设；下一轮应按 [ITER-0001](../../proposals/ITER-0001-foundation.md) 建立真实入口，并保留这些故障场景作为回归依据。
