using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace World.Server;

internal sealed record SessionAccess(string Token, string SessionId, string ExpiresAtUtc);

internal sealed partial class WorldDatabase(ServerConfiguration configuration)
{
    public string Path { get; } = System.IO.Path.Combine(configuration.DataDirectory, "world.db");
    public WorldScenario Scenario { get; private set; } = null!;
    public string? InstanceId { get; private set; }
    public MaterialProductionPolicy? ProductionPolicy { get; private set; }

    public SqliteConnection Open(bool existingOnly = true)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = Path, Mode = existingOnly ? SqliteOpenMode.ReadWrite : SqliteOpenMode.ReadWriteCreate,
            Pooling = false, DefaultTimeout = 5
        }.ToString());
        try
        {
            connection.Open();
            Run(connection, null, "PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;");
            return connection;
        }
        catch { connection.Dispose(); throw; }
    }

    public string SqliteVersion()
    {
        using var connection = Open();
        using var command = Command(connection, null, "SELECT sqlite_version()");
        return (string)command.ExecuteScalar()!;
    }

    public void ReloadMaterialPolicy(SqliteConnection connection, SqliteTransaction transaction)
    {
        var storage = Scalar(connection, transaction, "PRAGMA user_version");
        var current = ReadScenario(connection, transaction, storage);
        if (current != Scenario || !current.SupportsMaterialAccess || WorldInstance.Read(connection, transaction) != InstanceId)
            throw new InvalidOperationException("计时锁内的原世界身份不一致");
        ProductionPolicy = ContinuousMaterialRules.ReadPolicy(connection, transaction, InstanceId);
        if ((storage is 11 or 12) != (ProductionPolicy is not null))
            throw new InvalidOperationException("计时锁内的持续政策与存储不一致");
        if (ProductionPolicy is not null) ContinuousMaterialRules.ValidateState(connection, transaction, ProductionPolicy);
        EntityCanvasRules.ValidateStorage(connection, transaction, InstanceId, storage, ProductionPolicy);
    }

    public void Initialize()
    {
        Directory.CreateDirectory(configuration.DataDirectory);
        using var connection = Open(existingOnly: false);
        Run(connection, null, "PRAGMA journal_mode=WAL;");
        using var transaction = connection.BeginTransaction(deferred: false);
        var schemaVersion = Scalar(connection, transaction, "PRAGMA user_version");
        if (schemaVersion != 0)
        {
            Scenario = ReadScenario(connection, transaction, schemaVersion);
            InstanceId = WorldInstance.Read(connection, transaction);
            if (Scenario.SupportsTransfer && InstanceId is null)
                throw new InvalidOperationException("合作世界缺少实例身份，拒绝作为旧世界运行");
            if (EntityNoteRules.ReadAdoption(connection, transaction) is { } notes &&
                (!Scenario.SupportsMaterialAccess || notes.InstanceId != InstanceId))
                throw new InvalidOperationException("手记能力不属于这个世界实例");
            ProductionPolicy = ContinuousMaterialRules.ReadPolicy(connection, transaction, InstanceId);
            if ((schemaVersion is 11 or 12) != (ProductionPolicy is not null))
                throw new InvalidOperationException("存储版本与持续材料政策不一致");
            if (ProductionPolicy is not null) ContinuousMaterialRules.ValidateState(connection, transaction, ProductionPolicy);
            EntityCanvasRules.ValidateStorage(connection, transaction, InstanceId, schemaVersion, ProductionPolicy);
            transaction.Commit();
            return;
        }

        Scenario = configuration.RequestedScenario ?? WorldScenario.Wilderness;
        Run(connection, transaction, Scenario.SupportsMaterialAccess ? SchemaV10 : Scenario.SupportsTransfer ? SchemaV9 : Scenario.SupportsContinuous ? SchemaV8 : Scenario.SupportsGathering ? SchemaV7 : Scenario.SupportsMosaicConsent ? SchemaV6 : Scenario.SupportsMosaic ? SchemaV5 : Scenario.SupportsPostcards ? SchemaV4 : Scenario.SupportsActivities ? SchemaV3 : SchemaV2);
        if (Scenario.SupportsContinuous) WorldInstance.Create(connection, transaction);
        InstanceId = WorldInstance.Read(connection, transaction);
        Run(connection, transaction, """
            INSERT INTO worlds(id,scenario_id,rules_version,state_version,issued_wood,depot_wood) VALUES($world,$scenario,$rules,0,12,$depot);
            INSERT INTO residents(world_id,actor_id,operator_id,x,y,wood) VALUES($world,'a1','local-operator',$a1x,$a1y,0),($world,'a2',$a2operator,$a2x,$a2y,0);
            INSERT INTO recipes(id,definition_id,definition_version,rules_version,wood_cost) VALUES('platform.v1','platform',1,$rules,3);
            """, ("$world", Protocol.WorldId), ("$scenario", Scenario.Id), ("$rules", Scenario.RulesVersion),
            ("$a2operator", Scenario.SupportsMaterialAccess ? "declared-late" : "local-operator"),
            ("$a1x", Scenario.SupportsContinuous ? 5 : 1), ("$a1y", Scenario.SupportsContinuous ? 7 : 1), ("$depot", Scenario.SupportsGathering ? 0 : 12), ("$a2x", Scenario.SupportsContinuous ? 26 : Scenario.SupportsGathering ? 6 : 1), ("$a2y", Scenario.SupportsContinuous ? 17 : Scenario.SupportsGathering ? 6 : 2));
        if (Scenario.SupportsMaterialAccess)
            Run(connection, transaction, "INSERT INTO residents(world_id,actor_id,operator_id,x,y,wood) VALUES($world,'a1_alias','local-operator',5,7,0),($world,'a3','declared-third',27,10,0)", ("$world", Protocol.WorldId));
        if (Scenario.SupportsRecipe("bridge.v1"))
            Run(connection, transaction, """
                INSERT INTO recipes(id,definition_id,definition_version,rules_version,wood_cost) VALUES('bridge.v1','bridge',1,$rules,$bridgeCost)
                """, ("$rules", Scenario.RulesVersion), ("$bridgeCost", Scenario.SupportsContinuous ? 6 : 3));
        if (Scenario.SupportsGathering)
            foreach (var tree in Scenario.SupportsContinuous ? ContinuousWorld.Trees : WorldScenario.InitialTrees)
                Run(connection, transaction, """
                    INSERT INTO resource_nodes(world_id,node_id,kind,x,y,initial_wood,remaining_wood)
                    VALUES($world,$node,$kind,$x,$y,$wood,$wood)
                    """, ("$world", Protocol.WorldId), ("$node", tree.NodeId), ("$kind", tree.Kind),
                    ("$x", tree.Position[0]), ("$y", tree.Position[1]), ("$wood", tree.InitialWood));
        if (Scenario.SupportsMosaic)
        {
            Run(connection, transaction, "INSERT INTO mosaics(world_id,activity_id,revision) VALUES($world,'garden',0)",
                ("$world", Protocol.WorldId));
            for (var y = 0; y < 5; y++)
                for (var x = 0; x < 5; x++)
                    Run(connection, transaction, """
                        INSERT INTO mosaic_cells(world_id,activity_id,x,y,color) VALUES($world,'garden',$x,$y,'blank')
                        """, ("$world", Protocol.WorldId), ("$x", x), ("$y", y));
        }
        var seed = JsonSerializer.Serialize(new { seq = 1, stateVersion = 0, commandId = (string?)null,
            actorId = (string?)null, type = "worldSeeded", quantity = 12,
            source = Scenario.SupportsMaterialAccess ? "ITER-0022 initial wild wood" : Scenario.SupportsTransfer ? "ITER-0020 initial wild wood" : Scenario.SupportsContinuous ? "ITER-0014 initial wild wood" : Scenario.SupportsGathering ? "ITER-0010 initial wild wood" : Scenario == WorldScenario.Foundation ? "ITER-0001 initial allocation" :
                Scenario.SupportsMosaicConsent ? "ITER-0007 initial allocation" :
                Scenario.SupportsMosaic ? "ITER-0006 initial allocation" :
                Scenario.SupportsPostcards ? "ITER-0005 initial allocation" :
                Scenario.SupportsActivities ? "ITER-0004 initial allocation" : "ITER-0002 initial allocation" }, Protocol.Json);
        Run(connection, transaction, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES(1,$world,0,$event)",
            ("$world", Protocol.WorldId), ("$event", seed));
        Run(connection, transaction, """
            INSERT INTO resource_ledger(world_id,event_seq,command_id,actor_id,source_account,destination_account,quantity)
            VALUES($world,1,NULL,NULL,'initial-issuance',$destination,12)
            """, ("$world", Protocol.WorldId), ("$destination", Scenario.SupportsGathering ? "wild-wood" : "depot"));
        var sessions = new Dictionary<string, SessionAccess>
        {
            ["a1"] = NewSession(connection, transaction, "a1", 86400),
            ["a2"] = NewSession(connection, transaction, "a2", 86400)
        };
        if (Scenario.SupportsMaterialAccess)
            foreach (var actor in new[] { "a1_alias", "a3" }) sessions[actor] = NewSession(connection, transaction, actor, 86400);
        var accessPath = System.IO.Path.Combine(configuration.DataDirectory, "access.json");
        if (File.Exists(accessPath)) throw new InvalidOperationException("新世界目录已有 access.json，拒绝覆盖凭据");
        var temporaryPath = accessPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        WriteSecret(temporaryPath, new { worldId = Protocol.WorldId, sessions });
        try
        {
            transaction.Commit();
            File.Move(temporaryPath, accessPath, overwrite: false);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
        // Existing databases never create access.json or revive sessions. If initial file delivery is
        // interrupted after commit, the offline issue-session command provides explicit recovery.
    }

    private WorldScenario ReadScenario(SqliteConnection connection, SqliteTransaction transaction, long schemaVersion)
    {
        if (schemaVersion is not (1 or 2 or 3 or 4 or 5 or 6 or 7 or 8 or 9 or 10 or 11 or 12)) throw new InvalidOperationException("不支持的数据库版本");
        // v1 predates scenario persistence and is always the original world. Do not migrate it,
        // rewrite historical objects/receipts, or infer a different world from environment values.
        using var command = Command(connection, transaction, schemaVersion == 1
            ? "SELECT id,'foundation-v1',rules_version FROM worlds"
            : "SELECT id,scenario_id,rules_version FROM worlds");
        using var reader = command.ExecuteReader();
        if (!reader.Read() || reader.GetString(0) != Protocol.WorldId)
            throw new InvalidOperationException("数据库不属于 foundation-01");
        var scenario = WorldScenario.FromId(reader.GetString(1));
        if (reader.GetString(2) != scenario.RulesVersion || reader.Read())
            throw new InvalidOperationException("数据库场景或规则版本不匹配");
        if (schemaVersion != scenario.StorageVersion && !(schemaVersion == 1 && scenario == WorldScenario.Foundation)
            && !(schemaVersion is 11 or 12 && scenario == WorldScenario.MaterialAccess))
            throw new InvalidOperationException("数据库场景与存储版本不匹配");
        if (configuration.RequestedScenario is not null && configuration.RequestedScenario != scenario)
            throw new InvalidOperationException("WORLD_SCENARIO 与数据库已存场景不一致，拒绝切换世界");
        return scenario;
    }

    public Identity Authenticate(string tokenHash, SqliteConnection connection, SqliteTransaction? transaction)
    {
        using var command = Command(connection, transaction, """
            SELECT r.operator_id,s.actor_id,s.session_id
            FROM sessions s JOIN residents r ON r.world_id=s.world_id AND r.actor_id=s.actor_id
            WHERE s.token_hash=$hash AND s.world_id=$world AND s.revoked=0 AND s.expires_at_ms>$now
            """, ("$hash", tokenHash), ("$world", Protocol.WorldId), ("$now", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()));
        using var reader = command.ExecuteReader();
        if (!reader.Read()) throw new RequestFailure(401, "UNAUTHORIZED", "会话无效、已过期或已撤销");
        return new(reader.GetString(0), reader.GetString(1), reader.GetString(2));
    }

    public Identity Authenticate(string tokenHash)
    {
        using var connection = Open();
        return Authenticate(tokenHash, connection, null);
    }

    public void IssueSession(string actor, long ttlSeconds, string output)
    {
        if (!Protocol.ValidCommandId(actor)) throw new ArgumentException("actor 格式无效");
        // Validate expiry and output before touching the current session.
        _ = DateTimeOffset.UtcNow.AddSeconds(ttlSeconds);
        output = System.IO.Path.GetFullPath(output);
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(output)!);
        var temporaryPath = output + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction(deferred: false);
            Scenario = ReadScenario(connection, transaction, Scalar(connection, transaction, "PRAGMA user_version"));
            _ = WorldInstance.Read(connection, transaction);
            if (Scalar(connection, transaction, "SELECT count(*) FROM residents WHERE actor_id=$actor", ("$actor", actor)) != 1)
                throw new ArgumentException("actor 不在原世界名册中");
            Run(connection, transaction, "UPDATE sessions SET revoked=1 WHERE world_id=$world AND actor_id=$actor AND revoked=0",
                ("$world", Protocol.WorldId), ("$actor", actor));
            var session = NewSession(connection, transaction, actor, ttlSeconds);
            WriteSecret(temporaryPath, session);
            transaction.Commit();
            File.Move(temporaryPath, output, overwrite: true);
        }
        finally { if (File.Exists(temporaryPath)) File.Delete(temporaryPath); }
    }

    public bool EnableMaterialSource(string expectedInstance)
    {
        if (!WorldInstance.Valid(expectedInstance)) throw new ArgumentException("必须指定原世界实例身份");
        // Opening an existing database first avoids creating a candidate as a side effect.
        using var connection = Open();
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var transaction = connection.BeginTransaction(deferred: false);
        Scenario = ReadScenario(connection, transaction, Scalar(connection, transaction, "PRAGMA user_version"));
        if (!Scenario.SupportsMaterialAccess) throw new InvalidOperationException("只有r10候选支持开启材料来源");
        if (WorldInstance.Read(connection, transaction) != expectedInstance) throw new ArgumentException("实例身份不匹配");
        var source = MaterialSourceRules.Read(connection, transaction);
        if (source.Active) return false;
        Run(connection, transaction, "UPDATE material_source SET active=1,enabled_at_ms=service_ms,next_production_ms=$next WHERE id=1", ("$next", checked(source.ServiceMs + MaterialSourceRules.IntervalMs)));
        MaterialSourceRules.EnvironmentEvent(connection, transaction, "materialSourceEnabled", source.ServiceMs,
            ("inputBudget", MaterialSourceRules.InputBudget), ("capacity", MaterialSourceRules.Capacity),
            ("productionIntervalMs", MaterialSourceRules.IntervalMs), ("reservationQuantity", MaterialSourceRules.Quantity),
            ("leaseMs", MaterialSourceRules.LeaseMs), ("position", MaterialSourceRules.Position), ("buildExclusion", MaterialSourceRules.BuildExclusion));
        transaction.Commit();
        return true;
    }

    private static SessionAccess NewSession(SqliteConnection connection, SqliteTransaction transaction, string actor, long ttlSeconds)
    {
        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var sessionId = "s" + Guid.NewGuid().ToString("N");
        var expires = DateTimeOffset.UtcNow.AddSeconds(ttlSeconds);
        Run(connection, transaction, """
            INSERT INTO sessions(session_id,world_id,actor_id,token_hash,expires_at_ms,revoked)
            VALUES($id,$world,$actor,$hash,$expires,0)
            """, ("$id", sessionId), ("$world", Protocol.WorldId), ("$actor", actor), ("$hash", Protocol.Hash(token)),
            ("$expires", expires.ToUnixTimeMilliseconds()));
        return new(token, sessionId, expires.ToString("O"));
    }

    private static void WriteSecret(string path, object contents)
    {
        var options = new FileStreamOptions { Mode = FileMode.CreateNew, Access = FileAccess.Write, Share = FileShare.None };
        if (!OperatingSystem.IsWindows()) options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        using var stream = new FileStream(path, options);
        JsonSerializer.Serialize(stream, contents, Protocol.Json);
        stream.Flush(flushToDisk: true);
    }

    public static SqliteCommand Command(SqliteConnection connection, SqliteTransaction? transaction, string sql,
        params (string Name, object? Value)[] values)
    {
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        foreach (var (name, value) in values) command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return command;
    }

    public static int Run(SqliteConnection connection, SqliteTransaction? transaction, string sql, params (string Name, object? Value)[] values)
    {
        using var command = Command(connection, transaction, sql, values);
        return command.ExecuteNonQuery();
    }

    public static long Scalar(SqliteConnection connection, SqliteTransaction? transaction, string sql, params (string Name, object? Value)[] values)
    {
        using var command = Command(connection, transaction, sql, values);
        return Convert.ToInt64(command.ExecuteScalar());
    }

    private const string SchemaV2 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
          CHECK((scenario_id='foundation-v1' AND rules_version='r1') OR (scenario_id='passage-v1' AND rules_version='r2')));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        """ + SharedSchema + "\nPRAGMA user_version=2;";

    private const string SchemaV3 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
          CHECK(scenario_id='activities-v1' AND rules_version='r3'));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        """ + SharedSchema + VisitsSchema + "\nPRAGMA user_version=3;";

    private const string SchemaV4 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
          CHECK(scenario_id='postcards-v1' AND rules_version='r4'));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        """ + SharedSchema + VisitsSchema + PostcardsSchema + "\nPRAGMA user_version=4;";

    private const string SchemaV5 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
          CHECK(scenario_id='mosaic-v1' AND rules_version='r5'));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        """ + SharedSchema + VisitsSchema + PostcardsSchema + MosaicSchema + "\nPRAGMA user_version=5;";

    private const string SchemaV6 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
          CHECK(scenario_id='consent-v1' AND rules_version='r6'));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        """ + SharedSchema + VisitsSchema + PostcardsSchema + MosaicSchema + MosaicConsentSchema + "\nPRAGMA user_version=6;";

    private const string SchemaV7 = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
          rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood=0),
          CHECK(scenario_id='wilderness-v1' AND rules_version='r7'));
        CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
          BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
        CREATE TABLE resource_nodes(
          world_id TEXT NOT NULL REFERENCES worlds(id), node_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind='tree'),
          x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
          initial_wood INTEGER NOT NULL CHECK(initial_wood=3),
          remaining_wood INTEGER NOT NULL CHECK(typeof(remaining_wood)='integer' AND remaining_wood BETWEEN 0 AND initial_wood),
          PRIMARY KEY(world_id,node_id), UNIQUE(world_id,x,y), CHECK(x NOT IN(4,5) AND NOT(x=3 AND y<=2)));
        CREATE TRIGGER immutable_resource_definition BEFORE UPDATE OF world_id,node_id,kind,x,y,initial_wood ON resource_nodes
          BEGIN SELECT RAISE(ABORT,'immutable resource definition'); END;
        CREATE TRIGGER immutable_resource_delete BEFORE DELETE ON resource_nodes
          BEGIN SELECT RAISE(ABORT,'immutable resource definition'); END;
        """ + SharedSchema + VisitsSchema + "\nPRAGMA user_version=7;";

    private static readonly string SchemaV8 = SchemaV7
        .Replace("'wilderness-v1'", "'wilderness-continuous-v1'").Replace("'r7'", "'r8'")
        .Replace("x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7)", "x REAL NOT NULL CHECK(x BETWEEN 0 AND 32)")
        .Replace("y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7)", "y REAL NOT NULL CHECK(y BETWEEN 0 AND 24)")
        .Replace(", CHECK(x NOT IN(4,5) AND NOT(x=3 AND y<=2))", "")
        .Replace(", CHECK(NOT(x=3 AND y<=2))", "")
        .Replace("embodied_wood=3", "embodied_wood IN(3,6)")
        .Replace("PRAGMA user_version=7;", "ALTER TABLE residents ADD COLUMN last_walk_ms INTEGER NOT NULL DEFAULT 0; ALTER TABLE residents ADD COLUMN walk_credit REAL NOT NULL DEFAULT 0.6; PRAGMA user_version=8;");

    private static readonly string SchemaV9 = SchemaV8
        .Replace("'wilderness-continuous-v1'", "'wilderness-cooperation-v1'").Replace("'r8'", "'r9'")
        .Replace("PRAGMA user_version=8;", "PRAGMA user_version=9;");

    private static readonly string SchemaV10 = SchemaV9
        .Replace("'wilderness-cooperation-v1'", "'wilderness-material-access-v1'").Replace("'r9'", "'r10'")
        .Replace("CHECK(issued_wood=12)", "CHECK(typeof(issued_wood)='integer' AND issued_wood BETWEEN 12 AND 24)")
        .Replace("PRAGMA user_version=9;", "PRAGMA user_version=10;") + MaterialSourceRules.Schema;

    private const string MosaicSchema = """

        CREATE TABLE mosaics(
          world_id TEXT NOT NULL REFERENCES worlds(id), activity_id TEXT NOT NULL CHECK(activity_id='garden'),
          revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0),
          PRIMARY KEY(world_id,activity_id));
        CREATE TABLE mosaic_edits(
          world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
          author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
          base_revision INTEGER NOT NULL CHECK(typeof(base_revision)='integer' AND base_revision>=0),
          revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision=base_revision+1),
          patch_json TEXT NOT NULL CHECK(json_valid(patch_json) AND json_type(patch_json)='array' AND json_array_length(patch_json) BETWEEN 1 AND 8),
          state_version INTEGER NOT NULL, painted_at_utc TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6),
          PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
          UNIQUE(world_id,activity_id,revision), UNIQUE(world_id,author_actor_id,visit_command_id),
          FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
          FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
        CREATE INDEX recent_mosaic_edits_by_author ON mosaic_edits(world_id,author_actor_id,revision);
        CREATE TRIGGER immutable_mosaic_edit_update BEFORE UPDATE ON mosaic_edits BEGIN SELECT RAISE(ABORT,'immutable mosaic edit'); END;
        CREATE TRIGGER immutable_mosaic_edit_delete BEFORE DELETE ON mosaic_edits BEGIN SELECT RAISE(ABORT,'immutable mosaic edit'); END;
        CREATE TABLE mosaic_cells(
          world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
          x INTEGER NOT NULL CHECK(typeof(x)='integer' AND x BETWEEN 0 AND 4),
          y INTEGER NOT NULL CHECK(typeof(y)='integer' AND y BETWEEN 0 AND 4),
          color TEXT NOT NULL CHECK(color IN('blank','leaf','river','sun','rose','ink')),
          author_actor_id TEXT, command_id TEXT, state_version INTEGER,
          PRIMARY KEY(world_id,activity_id,x,y),
          CHECK((color='blank' AND author_actor_id IS NULL AND command_id IS NULL AND state_version IS NULL) OR
                (author_actor_id IS NOT NULL AND command_id IS NOT NULL AND state_version IS NOT NULL)),
          FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
          FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES mosaic_edits(world_id,author_actor_id,command_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED);
        """;

    private const string MosaicConsentSchema = """

        CREATE TABLE mosaic_proposals(
          world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
          author_actor_id TEXT NOT NULL, target_actor_id TEXT NOT NULL CHECK(target_actor_id<>author_actor_id),
          command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
          base_revision INTEGER NOT NULL CHECK(typeof(base_revision)='integer' AND base_revision>=0),
          patch_json TEXT NOT NULL CHECK(json_valid(patch_json) AND json_type(patch_json)='array' AND json_array_length(patch_json) BETWEEN 1 AND 8),
          text TEXT NOT NULL, state_version INTEGER NOT NULL, proposed_at_utc TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6),
          PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
          UNIQUE(world_id,author_actor_id,visit_command_id),
          UNIQUE(world_id,author_actor_id,command_id,target_actor_id),
          FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
          FOREIGN KEY(world_id,target_actor_id) REFERENCES residents(world_id,actor_id),
          FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
        CREATE INDEX recent_mosaic_proposals_by_author ON mosaic_proposals(world_id,author_actor_id,state_version);
        CREATE TRIGGER immutable_mosaic_proposal_update BEFORE UPDATE ON mosaic_proposals BEGIN SELECT RAISE(ABORT,'immutable mosaic proposal'); END;
        CREATE TRIGGER immutable_mosaic_proposal_delete BEFORE DELETE ON mosaic_proposals BEGIN SELECT RAISE(ABORT,'immutable mosaic proposal'); END;
        CREATE TABLE mosaic_reviews(
          world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
          author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
          proposal_actor_id TEXT NOT NULL, proposal_command_id TEXT NOT NULL,
          decision TEXT NOT NULL CHECK(decision IN('accept','reject')), text TEXT NOT NULL,
          state_version INTEGER NOT NULL, reviewed_at_utc TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6), edit_command_id TEXT,
          CHECK((decision='accept' AND edit_command_id IS NOT NULL AND edit_command_id=command_id) OR
                (decision='reject' AND edit_command_id IS NULL)),
          PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
          UNIQUE(world_id,proposal_actor_id,proposal_command_id),
          FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
          FOREIGN KEY(world_id,proposal_actor_id,proposal_command_id,author_actor_id)
            REFERENCES mosaic_proposals(world_id,author_actor_id,command_id,target_actor_id),
          FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
          FOREIGN KEY(world_id,author_actor_id,edit_command_id) REFERENCES mosaic_edits(world_id,author_actor_id,command_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
        CREATE INDEX recent_mosaic_reviews_by_author ON mosaic_reviews(world_id,author_actor_id,state_version);
        CREATE TRIGGER immutable_mosaic_review_update BEFORE UPDATE ON mosaic_reviews BEGIN SELECT RAISE(ABORT,'immutable mosaic review'); END;
        CREATE TRIGGER immutable_mosaic_review_delete BEFORE DELETE ON mosaic_reviews BEGIN SELECT RAISE(ABORT,'immutable mosaic review'); END;
        """;

    private const string PostcardsSchema = """

        CREATE TABLE postcards(
          world_id TEXT NOT NULL, author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
          visit_command_id TEXT NOT NULL, activity_id TEXT NOT NULL, text TEXT NOT NULL,
          state_version INTEGER NOT NULL, shared_at_utc TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
          PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
          UNIQUE(world_id,author_actor_id,visit_command_id),
          FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
        CREATE INDEX recent_postcards_by_author ON postcards(world_id,author_actor_id,state_version);
        CREATE TRIGGER immutable_postcard_update BEFORE UPDATE ON postcards BEGIN SELECT RAISE(ABORT,'immutable postcard'); END;
        CREATE TRIGGER immutable_postcard_delete BEFORE DELETE ON postcards BEGIN SELECT RAISE(ABORT,'immutable postcard'); END;
        """;

    private const string VisitsSchema = """

        CREATE TABLE visits(
          world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
          activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
          visited_at_utc TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
          PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
          FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
          FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
          FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
        CREATE INDEX recent_visits ON visits(world_id,actor_id,state_version);
        CREATE TRIGGER immutable_visit_update BEFORE UPDATE ON visits BEGIN SELECT RAISE(ABORT,'immutable visit'); END;
        CREATE TRIGGER immutable_visit_delete BEFORE DELETE ON visits BEGIN SELECT RAISE(ABORT,'immutable visit'); END;
        """;

    private const string SharedSchema = """
        CREATE TABLE residents(
          world_id TEXT NOT NULL REFERENCES worlds(id), actor_id TEXT NOT NULL, operator_id TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
          wood INTEGER NOT NULL CHECK(wood BETWEEN 0 AND 12), PRIMARY KEY(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
        CREATE TABLE sessions(
          session_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, actor_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
          expires_at_ms INTEGER NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN(0,1)),
          FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
        CREATE UNIQUE INDEX one_session_per_actor ON sessions(world_id,actor_id) WHERE revoked=0;
        CREATE TABLE recipes(
          id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
          rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
        CREATE TRIGGER immutable_recipe_update BEFORE UPDATE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
        CREATE TRIGGER immutable_recipe_delete BEFORE DELETE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
        CREATE TABLE entities(
          entity_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL,
          recipe_id TEXT NOT NULL REFERENCES recipes(id), definition_id TEXT NOT NULL,
          definition_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
          x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
          embodied_wood INTEGER NOT NULL CHECK(embodied_wood=3), UNIQUE(world_id,x,y),
          FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
        CREATE TABLE events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
          state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
        CREATE TABLE resource_ledger(
          id INTEGER PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
          command_id TEXT, actor_id TEXT, source_account TEXT NOT NULL, destination_account TEXT NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 12));
        CREATE TABLE receipts(
          world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
          request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
          PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
        CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
        CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
        CREATE TRIGGER immutable_ledger_update BEFORE UPDATE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
        CREATE TRIGGER immutable_ledger_delete BEFORE DELETE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
        CREATE TRIGGER immutable_receipt_update BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
        CREATE TRIGGER immutable_receipt_delete BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
        """;
}
