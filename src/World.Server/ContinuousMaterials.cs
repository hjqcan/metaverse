using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record MaterialProductionPolicy(string Id, int Version, long AdoptedAtServiceMs,
    long AdoptedAtStateVersion, long AdoptedAtEventCursor, long GeneratedWoodAtAdoption, long ProductionPeriodAtAdoption);

internal static class ContinuousMaterialRules
{
    public const string PolicyId = "continuous-service-time-v1";
    public const string WorldSchema = """
        CREATE TABLE worlds(
          id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL, rules_version TEXT NOT NULL,
          state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
          issued_wood INTEGER NOT NULL CHECK(typeof(issued_wood)='integer' AND issued_wood>=12),
          depot_wood INTEGER NOT NULL CHECK(depot_wood=0), CHECK(scenario_id='wilderness-material-access-v1' AND rules_version='r10'));
        """;
    public const string SourceSchema = """
        CREATE TABLE material_source(
          id INTEGER PRIMARY KEY CHECK(id=1), active INTEGER NOT NULL CHECK(active IN(0,1)),
          service_ms INTEGER NOT NULL CHECK(typeof(service_ms)='integer' AND service_ms>=0), enabled_at_ms INTEGER, next_production_ms INTEGER,
          production_period INTEGER NOT NULL CHECK(typeof(production_period)='integer' AND production_period>=0),
          generated_wood INTEGER NOT NULL CHECK(typeof(generated_wood)='integer' AND generated_wood>=0),
          stock_wood INTEGER NOT NULL CHECK(typeof(stock_wood)='integer' AND stock_wood BETWEEN 0 AND 6),
          CHECK(stock_wood<=generated_wood), CHECK((active=0 AND enabled_at_ms IS NULL AND next_production_ms IS NULL) OR
            (active=1 AND typeof(enabled_at_ms)='integer' AND enabled_at_ms>=0 AND typeof(next_production_ms)='integer'
              AND next_production_ms=enabled_at_ms+(production_period+1)*10000)));
        """;
    public const string ScenarioTrigger = "CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;";
    public const string Schema = """
        CREATE TABLE material_source_policy(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), policy_id TEXT NOT NULL CHECK(policy_id='continuous-service-time-v1'),
          policy_version INTEGER NOT NULL CHECK(policy_version=1), instance_id TEXT NOT NULL REFERENCES world_instance(instance_id),
          adopted_service_ms INTEGER NOT NULL CHECK(adopted_service_ms>=0), state_version INTEGER NOT NULL CHECK(state_version>0),
          event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq), generated_at_adoption INTEGER NOT NULL CHECK(generated_at_adoption BETWEEN 0 AND 12),
          production_period_at_adoption INTEGER NOT NULL CHECK(production_period_at_adoption>=0));
        CREATE TRIGGER immutable_material_policy_update BEFORE UPDATE ON material_source_policy BEGIN SELECT RAISE(ABORT,'immutable material policy'); END;
        CREATE TRIGGER immutable_material_policy_delete BEFORE DELETE ON material_source_policy BEGIN SELECT RAISE(ABORT,'immutable material policy'); END;
        """;

    public static MaterialProductionPolicy? ReadPolicy(SqliteConnection c, SqliteTransaction t, string? instance)
    {
        if (Scalar(c, t, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='material_source_policy'") == 0) return null;
        // Storage11 is one explicit schema, not merely an upper version bound.
        // SQLite quotes names when it renames the newly rebuilt tables.
        static string Normalized(string sql) => string.Concat(sql.Where(ch => !char.IsWhiteSpace(ch) && ch != '"')).TrimEnd(';');
        foreach (var (name, expected) in new[] { ("worlds", WorldSchema), ("material_source", SourceSchema),
            ("material_source_policy", Schema[..Schema.IndexOf(';')]), ("immutable_scenario", ScenarioTrigger),
            ("immutable_material_policy_update", "CREATE TRIGGER immutable_material_policy_update BEFORE UPDATE ON material_source_policy BEGIN SELECT RAISE(ABORT,'immutable material policy'); END;"),
            ("immutable_material_policy_delete", "CREATE TRIGGER immutable_material_policy_delete BEFORE DELETE ON material_source_policy BEGIN SELECT RAISE(ABORT,'immutable material policy'); END;") })
        {
            using var schema = Command(c, t, "SELECT sql FROM sqlite_master WHERE name=$name", ("$name", name));
            if (schema.ExecuteScalar() is not string actual || Normalized(actual) != Normalized(expected))
                throw new InvalidOperationException("持续来源存储结构不受支持");
        }
        // SQLite INTEGER affinity still permits REAL values. GetInt64 truncates
        // them, so reject non-integer anchors before comparing original events.
        if (Scalar(c, t, """
            SELECT count(*) FROM material_source_policy WHERE typeof(singleton)!='integer' OR typeof(policy_version)!='integer'
              OR typeof(adopted_service_ms)!='integer' OR typeof(state_version)!='integer' OR typeof(event_seq)!='integer'
              OR typeof(generated_at_adoption)!='integer' OR typeof(production_period_at_adoption)!='integer'
              OR typeof(policy_id)!='text' OR typeof(instance_id)!='text'
            """) != 0)
            throw new InvalidOperationException("持续材料政策字段类型不匹配");
        using var command = Command(c, t, "SELECT singleton,policy_id,policy_version,instance_id,adopted_service_ms,state_version,event_seq,generated_at_adoption,production_period_at_adoption FROM material_source_policy");
        using var r = command.ExecuteReader();
        if (!r.Read() || r.GetInt64(0) != 1 || r.GetString(1) != PolicyId || r.GetInt64(2) != 1 || r.GetString(3) != instance)
            throw new InvalidOperationException("持续材料政策身份不匹配");
        var policy = new MaterialProductionPolicy(PolicyId, 1, r.GetInt64(4), r.GetInt64(5), r.GetInt64(6), r.GetInt64(7), r.GetInt64(8));
        if (r.Read()) throw new InvalidOperationException("持续材料政策不唯一");
        r.Close();
        using var eventCommand = Command(c, t, "SELECT event_json FROM events WHERE seq=$seq AND state_version=$state", ("$seq", policy.AdoptedAtEventCursor), ("$state", policy.AdoptedAtStateVersion));
        var raw = eventCommand.ExecuteScalar() as string ?? throw new InvalidOperationException("缺少原政策采用事件");
        using var json = JsonDocument.Parse(raw);
        var e = json.RootElement;
        if (e.GetProperty("type").GetString() != "continuousMaterialSourceAdopted" || e.GetProperty("worldInstanceId").GetString() != instance
            || e.GetProperty("sourceId").GetString() != MaterialSourceRules.SourceId || e.GetProperty("actorId").ValueKind != JsonValueKind.Null
            || e.GetProperty("commandId").ValueKind != JsonValueKind.Null || e.GetProperty("serviceMs").GetInt64() != policy.AdoptedAtServiceMs
            || e.GetProperty("seq").GetInt64() != policy.AdoptedAtEventCursor || e.GetProperty("stateVersion").GetInt64() != policy.AdoptedAtStateVersion
            || JsonSerializer.Deserialize<MaterialProductionPolicy>(e.GetProperty("productionPolicy"), Protocol.Json) != policy)
            throw new InvalidOperationException("原政策采用事件不匹配");
        return policy;
    }

    public static void ValidateState(SqliteConnection c, SqliteTransaction t, MaterialProductionPolicy? policy = null)
    {
        var s = MaterialSourceRules.Read(c, t);
        if (!s.Active || !s.EnabledAtServiceMs.HasValue || !s.NextProductionAtMs.HasValue
            || Scalar(c, t, """
                SELECT count(*) FROM material_source WHERE typeof(service_ms)!='integer' OR typeof(enabled_at_ms)!='integer'
                  OR typeof(next_production_ms)!='integer' OR typeof(production_period)!='integer'
                  OR typeof(generated_wood)!='integer' OR typeof(stock_wood)!='integer'
                """) != 0
            || s.ServiceMs < s.EnabledAtServiceMs || s.NextProductionAtMs != checked(s.EnabledAtServiceMs + (s.ProductionPeriod + 1) * MaterialSourceRules.IntervalMs)
            || s.NextProductionAtMs <= s.ServiceMs || s.GeneratedWood < 0 || s.StockWood < 0 || s.StockWood > 6 || s.StockWood > s.GeneratedWood)
            throw new InvalidOperationException("材料来源状态不一致");
        var generated = Scalar(c, t, "SELECT coalesce(sum(quantity),0) FROM material_production");
        var issued = Scalar(c, t, "SELECT issued_wood FROM worlds");
        var total = Scalar(c, t, "SELECT (SELECT coalesce(sum(wood),0) FROM residents)+(SELECT coalesce(sum(remaining_wood),0) FROM resource_nodes)+(SELECT coalesce(sum(embodied_wood),0) FROM entities)+(SELECT stock_wood FROM material_source)");
        if (generated != s.GeneratedWood || issued != checked(12 + generated) || total != issued
            || Scalar(c, t, "SELECT coalesce(max(production_period),0) FROM material_production") > s.ProductionPeriod
            || Scalar(c, t, "SELECT coalesce(sum(remaining),0) FROM material_reservations WHERE status='active'") > s.StockWood
            || Scalar(c, t, "SELECT count(*) FROM pragma_foreign_key_check") != 0)
            throw new InvalidOperationException("材料历史或守恒不一致");
        if (Scalar(c, t, """
            SELECT count(*) FROM material_production p LEFT JOIN events e ON e.seq=p.event_seq LEFT JOIN resource_ledger l ON l.event_seq=p.event_seq
            WHERE e.seq IS NULL OR l.event_seq IS NULL OR l.source_account!='ecological-input' OR l.destination_account!='source:wood-source-east'
              OR l.quantity!=p.quantity OR l.actor_id IS NOT NULL OR l.command_id IS NOT NULL
              OR json_extract(e.event_json,'$.type') IS NOT 'materialProduced' OR json_extract(e.event_json,'$.quantity') IS NOT p.quantity
              OR json_extract(e.event_json,'$.productionPeriod') IS NOT p.production_period OR json_extract(e.event_json,'$.serviceMs') IS NOT p.service_ms
              OR json_extract(e.event_json,'$.sourceId') IS NOT 'wood-source-east' OR json_extract(e.event_json,'$.seq') IS NOT e.seq
              OR json_extract(e.event_json,'$.stateVersion') IS NOT e.state_version
              OR json_type(e.event_json,'$.actorId') IS NOT 'null' OR json_type(e.event_json,'$.commandId') IS NOT 'null'
              OR p.service_ms IS NOT $enabled+p.production_period*10000 OR p.service_ms>$now
            """, ("$enabled", s.EnabledAtServiceMs), ("$now", s.ServiceMs)) != 0
            || Scalar(c, t, "SELECT count(*) FROM resource_ledger l WHERE source_account='ecological-input' AND NOT EXISTS(SELECT 1 FROM material_production p WHERE p.event_seq=l.event_seq)") != 0)
            throw new InvalidOperationException("生产账本与原事件不一致");
        if (policy is not null && (policy.AdoptedAtServiceMs > s.ServiceMs || policy.GeneratedWoodAtAdoption > s.GeneratedWood
            || policy.ProductionPeriodAtAdoption > s.ProductionPeriod || policy.AdoptedAtStateVersion > Scalar(c, t, "SELECT state_version FROM worlds")
            || Scalar(c, t, "SELECT coalesce(sum(quantity),0) FROM material_production WHERE production_period<=$period", ("$period", policy.ProductionPeriodAtAdoption)) != policy.GeneratedWoodAtAdoption))
            throw new InvalidOperationException("持续政策与历史生产进度不一致");
    }
}

internal sealed partial class WorldDatabase
{
    public bool AdoptContinuousMaterialSource(string expectedInstance)
    {
        if (!WorldInstance.Valid(expectedInstance)) throw new ArgumentException("必须指定原世界实例身份");
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var c = Open();
        // SQLite's documented table rebuild sequence: foreign-key mode is
        // connection-local and must change before BEGIN, never inside it.
        Run(c, null, "PRAGMA foreign_keys=OFF;");
        try
        {
            using var t = c.BeginTransaction(deferred: false);
            var storage = Scalar(c, t, "PRAGMA user_version");
            Scenario = ReadScenario(c, t, storage);
            if (!Scenario.SupportsMaterialAccess || WorldInstance.Read(c, t) != expectedInstance)
                throw new InvalidOperationException("持续政策只能在指定原材料实例采用");
            var previous = ContinuousMaterialRules.ReadPolicy(c, t, expectedInstance);
            if ((storage is 11 or 12) != (previous is not null)) throw new InvalidOperationException("持续政策与存储不一致");
            ContinuousMaterialRules.ValidateState(c, t, previous);
            EntityCanvasRules.ValidateStorage(c, t, expectedInstance, storage, previous);
            if (EntityNoteRules.ReadAdoption(c, t) is { } notes && (notes.InstanceId != expectedInstance || EntityNoteRules.ReadBridge(c, t, notes.EntityId) is null))
                throw new InvalidOperationException("原手记目标不匹配");
            if (previous is not null) return false;
            if (storage != 10) throw new InvalidOperationException("只支持原存储10采用");
            var source = MaterialSourceRules.Read(c, t);
            Run(c, t, ContinuousMaterialRules.WorldSchema.Replace("CREATE TABLE worlds(", "CREATE TABLE worlds_continuous_new("));
            Run(c, t, """
                INSERT INTO worlds_continuous_new SELECT * FROM worlds;
                DROP TABLE worlds;
                ALTER TABLE worlds_continuous_new RENAME TO worlds;
                """);
            Run(c, t, ContinuousMaterialRules.ScenarioTrigger);
            Run(c, t, ContinuousMaterialRules.SourceSchema.Replace("CREATE TABLE material_source(", "CREATE TABLE material_source_continuous_new("));
            Run(c, t, """
                INSERT INTO material_source_continuous_new SELECT * FROM material_source;
                DROP TABLE material_source;
                ALTER TABLE material_source_continuous_new RENAME TO material_source;
                """);
            Run(c, t, ContinuousMaterialRules.Schema);
            var version = checked(Scalar(c, t, "SELECT state_version FROM worlds") + 1);
            var seq = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
            var policy = new MaterialProductionPolicy(ContinuousMaterialRules.PolicyId, 1, source.ServiceMs, version, seq, source.GeneratedWood, source.ProductionPeriod);
            MaterialSourceRules.EnvironmentEvent(c, t, "continuousMaterialSourceAdopted", source.ServiceMs,
                ("worldInstanceId", expectedInstance), ("productionPolicy", policy));
            Run(c, t, "INSERT INTO material_source_policy VALUES(1,$id,1,$instance,$ms,$state,$seq,$generated,$period)",
                ("$id", policy.Id), ("$instance", expectedInstance), ("$ms", source.ServiceMs), ("$state", version), ("$seq", seq),
                ("$generated", source.GeneratedWood), ("$period", source.ProductionPeriod));
            Run(c, t, "PRAGMA user_version=11;");
            ContinuousMaterialRules.ValidateState(c, t, ContinuousMaterialRules.ReadPolicy(c, t, expectedInstance));
            var fault = configuration.FaultsEnabled ? Environment.GetEnvironmentVariable("WORLD_CONTINUOUS_ADOPTION_TEST_FAULT") : null;
            if (fault == "before-commit") Environment.Exit(85);
            t.Commit();
            if (fault == "after-commit") Environment.Exit(86);
            return true;
        }
        finally { Run(c, null, "PRAGMA foreign_keys=ON;"); }
    }
}
