using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

// Separate from rules/storage versions. Existing worlds remain explicitly unbound.
internal static class WorldInstance
{
    public const string Header = "World-Instance-Id";

    public static bool Valid(string value) => value.Length == 34 && value.StartsWith("w_", StringComparison.Ordinal)
        && value.AsSpan(2).IndexOfAnyExcept("0123456789abcdef") < 0;

    public static void Create(SqliteConnection connection, SqliteTransaction transaction)
    {
        Run(connection, transaction, """
            CREATE TABLE world_instance(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              instance_id TEXT NOT NULL UNIQUE,
              binding_version INTEGER NOT NULL CHECK(binding_version=1)
            );
            CREATE TRIGGER immutable_world_instance_update BEFORE UPDATE ON world_instance
              BEGIN SELECT RAISE(ABORT,'immutable world instance'); END;
            CREATE TRIGGER immutable_world_instance_delete BEFORE DELETE ON world_instance
              BEGIN SELECT RAISE(ABORT,'immutable world instance'); END;
            INSERT INTO world_instance(singleton,instance_id,binding_version) VALUES(1,$instance,1);
            """, ("$instance", "w_" + Guid.NewGuid().ToString("N")));
    }

    public static string? Read(SqliteConnection connection, SqliteTransaction transaction)
    {
        if (Scalar(connection, transaction, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='world_instance'") == 0)
            return null;
        using var command = Command(connection, transaction, "SELECT singleton,instance_id,binding_version FROM world_instance");
        using var reader = command.ExecuteReader();
        if (!reader.Read() || reader.GetInt64(0) != 1 || reader.GetInt64(2) != 1 || !Valid(reader.GetString(1)))
            throw new InvalidOperationException("世界实例元数据损坏或不受支持");
        var instance = reader.GetString(1);
        if (reader.Read()) throw new InvalidOperationException("世界实例元数据不唯一");
        return instance;
    }

    public static string? Require(SqliteConnection connection, SqliteTransaction transaction, string? expected, bool required = false)
    {
        var instance = Read(connection, transaction);
        if (expected is not null && instance is null)
            throw new RequestFailure(428, "WORLD_INSTANCE_UNAVAILABLE", "当前世界没有实例绑定能力");
        if (instance is not null && expected is null && required)
            throw new RequestFailure(428, "WORLD_INSTANCE_REQUIRED", "此世界要求实例绑定，请使用支持它的客户端", instance);
        if (expected is not null && expected != instance)
            throw new RequestFailure(412, "WORLD_INSTANCE_MISMATCH", "连接已指向另一个世界，原动作仍须在原世界确认", instance);
        return instance;
    }

    public static string? ReadHeader(HttpRequest request)
    {
        if (!request.Headers.TryGetValue(Header, out var values)) return null;
        if (values.Count != 1 || values[0] is not { } value || !Valid(value))
            throw new RequestFailure(400, "INVALID_WORLD_INSTANCE", "世界实例头必须是唯一有效的实例 ID");
        return value;
    }
}
