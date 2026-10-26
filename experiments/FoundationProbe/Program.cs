using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;

// Research probe only: one database = one world; one recipe consumes 2 units per item.
// There is deliberately no network service, authentication, real agent, or world engine.
internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    private static readonly List<object> Results = [];
    private sealed record Intent(string ActorId, string CommandId, int Quantity = 1, long? ExpectedVersion = null);
    private sealed record Receipt(string Code, long StockVersion, long RemainingUnits);
    private sealed record Snapshot(long Units, long Version, long Items, long Events, long Receipts, long Delta);

    private static async Task<int> Main(string[] args)
    {
        SQLitePCL.Batteries.Init();
        if (args.Length == 3 && args[0] == "--crash-child")
        {
            Execute(args[1], new("alice", "crash-command", ExpectedVersion: 0), args[2]);
            return 99; // The injected termination must occur before this point.
        }
        var root = Path.Combine(Path.GetTempPath(), "metaverse-foundation-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var negative = CreateWorld(root, "negative", 2);
            using (var barrier = new Barrier(2))
            {
                await Task.WhenAll(Enumerable.Range(0, 2).Select(i => Task.Factory.StartNew(() =>
                {
                    using var connection = Open(negative);
                    var staleUnits = Scalar(connection, null, "SELECT units FROM stock");
                    barrier.SignalAndWait(); // Both read 2 before either transaction begins.
                    using var transaction = connection.BeginTransaction(deferred: false);
                    Run(connection, transaction, "UPDATE stock SET units=$units, version=version+1", ("$units", staleUnits - 2));
                    Run(connection, transaction, "INSERT INTO items(actor_id, command_id, ordinal) VALUES('alice',$id,0)", ("$id", "bad-" + i));
                    transaction.Commit();
                }, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default)));
            }
            var bad = Read(negative);
            Check(bad.Units == 0 && bad.Items == 2 && bad.Units + 2 * bad.Items > 2, "negative control must expose inflation");
            Results.Add(new { scenario = "unsafe_read_then_write", passed = true, expectedInvariantViolation = true,
                initialUnits = 2, final = bad, accountedUnits = bad.Units + 2 * bad.Items });

            var contention = CreateWorld(root, "contention", 10);
            var replies = await Task.WhenAll(Enumerable.Range(0, 32).Select(i => Task.Run(() => Execute(contention, new("alice", "craft-" + i)))));
            var contested = Read(contention);
            Check(replies.Count(x => x.Code == "APPLIED") == 5 && replies.Count(x => x.Code == "INSUFFICIENT_RESOURCE") == 27,
                "32 writers must produce exactly 5 items from 10 units");
            VerifyConservation(contested, 10, 5, 32);
            Results.Add(new { scenario = "concurrent_finite_stock", passed = true, callers = 32, applied = 5, rejected = 27, final = contested });

            var duplicates = CreateWorld(root, "duplicates", 10);
            var duplicateIntent = new Intent("alice", "same-command", ExpectedVersion: 0);
            var duplicateReplies = await Task.WhenAll(Enumerable.Range(0, 16).Select(_ => Task.Run(() => Execute(duplicates, duplicateIntent))));
            Check(duplicateReplies.All(x => x == duplicateReplies[0]) && duplicateReplies[0].Code == "APPLIED", "duplicate returns original receipt before version check");
            var duplicateState = Read(duplicates);
            VerifyConservation(duplicateState, 10, 1, 1);
            var altered = Execute(duplicates, duplicateIntent with { Quantity = 2 });
            Check(altered.Code == "IDEMPOTENCY_CONFLICT" && Read(duplicates) == duplicateState, "same key different request must not change state");
            Results.Add(new { scenario = "duplicates_and_payload_conflict", passed = true, callers = 16, identicalResults = true, alteredPayloadCode = altered.Code, final = duplicateState });

            var stale = Execute(duplicates, new("alice", "stale-command", ExpectedVersion: 0));
            Check(stale.Code == "VERSION_CONFLICT", "new stale command must conflict");
            Check(Execute(duplicates, new("alice", "stale-command", ExpectedVersion: 0)) == stale, "rejected receipt must be stable");
            VerifyConservation(Read(duplicates), 10, 1, 2);
            Results.Add(new { scenario = "stale_version", passed = true, result = stale, final = Read(duplicates) });

            var actorScope = CreateWorld(root, "actor-scope", 4);
            Check(Execute(actorScope, new("alice", "shared-id")).Code == "APPLIED", "alice command");
            Check(Execute(actorScope, new("bob", "shared-id")).Code == "APPLIED", "bob owns a separate idempotency scope");
            VerifyConservation(Read(actorScope), 4, 2, 2);
            Results.Add(new { scenario = "actor_scoped_command_identity", passed = true, final = Read(actorScope) });

            var insufficient = CreateWorld(root, "insufficient", 1);
            var denied = Execute(insufficient, new("alice", "too-poor"));
            Check(denied.Code == "INSUFFICIENT_RESOURCE", "insufficient request must fail");
            VerifyConservation(Read(insufficient), 1, 0, 1);
            Results.Add(new { scenario = "insufficient_resource", passed = true, final = Read(insufficient) });

            var rollback = CreateWorld(root, "rollback", 2);
            try
            {
                Execute(rollback, new("alice", "throw-command"), "throw-after-debit");
                throw new Exception("fault injection did not run");
            }
            catch (InjectedFailure) { }
            VerifyConservation(Read(rollback), 2, 0, 0);
            var retry = Execute(rollback, new("alice", "throw-command"));
            Check(retry.Code == "APPLIED", "rolled-back command can be retried");
            VerifyConservation(Read(rollback), 2, 1, 1);
            Results.Add(new { scenario = "exception_after_debit", passed = true, final = Read(rollback) });

            foreach (var point in new[] { "before-commit", "after-commit" })
            {
                var crash = CreateWorld(root, point, 2);
                var exitCode = await CrashChild(crash, point);
                Check(exitCode == (point == "before-commit" ? 81 : 82), "child reached exact crash point");
                var recovered = Read(crash);
                VerifyConservation(recovered, 2, point == "before-commit" ? 0 : 1, point == "before-commit" ? 0 : 1);
                var recoveredReply = Execute(crash, new("alice", "crash-command", ExpectedVersion: 0));
                Check(recoveredReply.Code == "APPLIED", "same command resolves after child exit");
                VerifyConservation(Read(crash), 2, 1, 1);
                Results.Add(new { scenario = "process_exit_" + point.Replace('-', '_'), passed = true, exitCode, beforeRetry = recovered, afterRetry = Read(crash) });
            }

            using var versionConnection = Open(contention);
            using var versionCommand = versionConnection.CreateCommand();
            versionCommand.CommandText = "SELECT sqlite_version()";
            var report = new
            {
                experiment = "foundation-transactions-v1", recordedAtUtc = DateTimeOffset.UtcNow,
                runtime = RuntimeInformation.FrameworkDescription, os = RuntimeInformation.OSDescription,
                sqliteVersion = (string)versionCommand.ExecuteScalar()!,
                providerVersion = typeof(SqliteConnection).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                journalMode = "wal", synchronous = "FULL", scenarios = Results, passed = true,
                limits = new[] { "Local process and SQLite only; no HTTP/auth/client/LLM integration", "Process exit is not host power-loss testing", "No performance SLA or long-running economy claim" }
            };
            var output = JsonSerializer.Serialize(report, Json);
            if (args.Length == 2 && args[0] == "--output")
            {
                var outputPath = Path.GetFullPath(args[1]);
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
                await File.WriteAllTextAsync(outputPath, output + Environment.NewLine);
            }
            Console.WriteLine(output);
            return 0;
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    private static string CreateWorld(string root, string name, int units)
    {
        var path = Path.Combine(root, name + ".db");
        using var connection = Open(path);
        Run(connection, null, "PRAGMA journal_mode=WAL;");
        Run(connection, null, """
            CREATE TABLE stock(id INTEGER PRIMARY KEY CHECK(id=1), units INTEGER NOT NULL CHECK(units>=0), version INTEGER NOT NULL);
            CREATE TABLE items(id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, command_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                UNIQUE(actor_id,command_id,ordinal));
            CREATE TABLE events(id INTEGER PRIMARY KEY, actor_id TEXT NOT NULL, command_id TEXT NOT NULL, delta INTEGER NOT NULL,
                UNIQUE(actor_id,command_id));
            CREATE TABLE receipts(actor_id TEXT NOT NULL, command_id TEXT NOT NULL, request_hash TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(actor_id,command_id));
            INSERT INTO stock VALUES(1,$units,0);
            """, ("$units", units));
        return path;
    }

    private static Receipt Execute(string path, Intent intent, string? fault = null)
    {
        if (intent.Quantity is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(intent));
        // Typed fixed-order serialization for this probe only; production must canonicalize the versioned API schema.
        var requestHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(intent))));
        using var connection = Open(path);
        using var transaction = connection.BeginTransaction(deferred: false);
        using (var previous = Command(connection, transaction,
            "SELECT request_hash,result_json FROM receipts WHERE actor_id=$actor AND command_id=$id", ("$actor", intent.ActorId), ("$id", intent.CommandId)))
        using (var reader = previous.ExecuteReader())
        {
            if (reader.Read())
            {
                var result = JsonSerializer.Deserialize<Receipt>(reader.GetString(1))!;
                return reader.GetString(0) == requestHash ? result : result with { Code = "IDEMPOTENCY_CONFLICT" };
            }
        }
        var units = Scalar(connection, transaction, "SELECT units FROM stock");
        var version = Scalar(connection, transaction, "SELECT version FROM stock");
        var cost = checked(intent.Quantity * 2);
        var code = intent.ExpectedVersion is not null && intent.ExpectedVersion != version ? "VERSION_CONFLICT"
            : units < cost ? "INSUFFICIENT_RESOURCE" : "APPLIED";
        if (code == "APPLIED")
        {
            var changed = Run(connection, transaction,
                "UPDATE stock SET units=units-$cost,version=version+1 WHERE id=1 AND units >= $cost AND version=$version", ("$cost", cost), ("$version", version));
            Check(changed == 1, "guarded debit changed one row");
            if (fault == "throw-after-debit") throw new InjectedFailure();
            for (var i = 0; i < intent.Quantity; i++)
                Run(connection, transaction, "INSERT INTO items(actor_id,command_id,ordinal) VALUES($actor,$id,$ordinal)",
                    ("$actor", intent.ActorId), ("$id", intent.CommandId), ("$ordinal", i));
            Run(connection, transaction, "INSERT INTO events(actor_id,command_id,delta) VALUES($actor,$id,$delta)",
                ("$actor", intent.ActorId), ("$id", intent.CommandId), ("$delta", -cost));
            units -= cost;
            version++;
        }
        var receipt = new Receipt(code, version, units);
        Run(connection, transaction, "INSERT INTO receipts VALUES($actor,$id,$hash,$result)",
            ("$actor", intent.ActorId), ("$id", intent.CommandId), ("$hash", requestHash), ("$result", JsonSerializer.Serialize(receipt)));
        if (fault == "before-commit") Environment.Exit(81);
        transaction.Commit();
        if (fault == "after-commit") Environment.Exit(82);
        return receipt;
    }

    private static async Task<int> CrashChild(string path, string point)
    {
        var start = new ProcessStartInfo("dotnet") { UseShellExecute = false, RedirectStandardError = true, RedirectStandardOutput = true };
        foreach (var arg in new[] { Assembly.GetExecutingAssembly().Location, "--crash-child", path, point }) start.ArgumentList.Add(arg);
        using var process = Process.Start(start) ?? throw new Exception("cannot start fault-injection child");
        var stderr = process.StandardError.ReadToEndAsync();
        var stdout = process.StandardOutput.ReadToEndAsync();
        await process.WaitForExitAsync();
        if (process.ExitCode is not (81 or 82)) throw new Exception($"Unexpected child exit {process.ExitCode}: {await stderr} {await stdout}");
        return process.ExitCode;
    }

    private static Snapshot Read(string path)
    {
        using var connection = Open(path);
        using var transaction = connection.BeginTransaction(deferred: true);
        return new Snapshot(Scalar(connection, transaction, "SELECT units FROM stock"), Scalar(connection, transaction, "SELECT version FROM stock"),
            Scalar(connection, transaction, "SELECT count(*) FROM items"), Scalar(connection, transaction, "SELECT count(*) FROM events"),
            Scalar(connection, transaction, "SELECT count(*) FROM receipts"), Scalar(connection, transaction, "SELECT coalesce(sum(delta),0) FROM events"));
    }

    private static void VerifyConservation(Snapshot state, long initial, long items, long receipts)
    {
        Check(state.Units >= 0 && state.Items == items && state.Version == items && state.Events == items && state.Receipts == receipts
            && state.Units + 2 * state.Items == initial && initial + state.Delta == state.Units, "conservation/state/event/receipt checks");
    }

    private static SqliteConnection Open(string path)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Pooling = false, DefaultTimeout = 15 }.ToString());
        connection.Open();
        Run(connection, null, "PRAGMA synchronous=FULL;");
        return connection;
    }

    private static SqliteCommand Command(SqliteConnection connection, SqliteTransaction? transaction, string sql, params (string Name, object Value)[] values)
    {
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        foreach (var (name, value) in values) command.Parameters.AddWithValue(name, value);
        return command;
    }

    private static int Run(SqliteConnection connection, SqliteTransaction? transaction, string sql, params (string Name, object Value)[] values)
    {
        using var command = Command(connection, transaction, sql, values);
        return command.ExecuteNonQuery();
    }

    private static long Scalar(SqliteConnection connection, SqliteTransaction? transaction, string sql)
    {
        using var command = Command(connection, transaction, sql);
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception("Assertion failed: " + message);
    }
    private sealed class InjectedFailure : Exception;
}
