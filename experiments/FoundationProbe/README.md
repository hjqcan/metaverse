# FoundationProbe

隔离研究程序：一个配方、有限材料、SQLite 事务与持久命令回执。不是世界服务。

从仓库根目录运行：

```bash
dotnet restore experiments/FoundationProbe/FoundationProbe.csproj --locked-mode
dotnet run --project experiments/FoundationProbe --no-restore -- --output .local/experiments/transactions-rerun.json
```

需要 .NET 10 SDK。依赖锁定在 `packages.lock.json`；数据库只在本次新建的临时目录中创建并清理。失败断言导致非零退出。程序会启动两个自己的子进程，分别在事务提交前和提交后退出以检验恢复。

第一个场景是故意错误的对照：成功复制出物品才算该场景检出缺陷。后续场景验证候选事务模式。初始材料与配方参数固定，没有连接居民、网络服务、现有数据库或 LLM。

详见[结果和边界](../../docs/research/2026-10-25-foundation/03-experiment-results.md)。
