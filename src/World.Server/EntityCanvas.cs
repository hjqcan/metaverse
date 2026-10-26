using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record EntityCanvasState(string EntityId, string WorldInstanceId, long StateVersion, long EventCursor, long Revision);
internal sealed record EntityCanvasCell(long X, long Y, string Color, string? AuthorActorId, string? CommandId, long? StateVersion);
internal sealed record EntityCanvasEdit(string EntityId, string AuthorActorId, string OperatorId, string CommandId,
    long BaseRevision, long Revision, MosaicPatchCell[] Patch, long StateVersion, long EventCursor,
    string PaintedAtUtc, double[] Position, long InventoryWood)
{
    public int CapabilityVersion => 1;
}

internal static class EntityCanvasRules
{
    public const string Capability = "entity-canvas-v1", PaintRule = "unowned-or-author-v1";
    public const double Reach = 1.6;
    public const int Size = 5, MaxPatchCells = 8, RecentLimit = 50;
    public static readonly (string Name, string Sql)[] Schema =
    [
        ("entity_canvas", """
            CREATE TABLE entity_canvas(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), capability TEXT NOT NULL CHECK(capability='entity-canvas-v1'),
              version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version=1),
              entity_id TEXT NOT NULL UNIQUE REFERENCES entities(entity_id), instance_id TEXT NOT NULL REFERENCES world_instance(instance_id),
              state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>0),
              event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
              revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0))
            """),
        ("entity_canvas_edits", """
            CREATE TABLE entity_canvas_edits(
              entity_id TEXT NOT NULL REFERENCES entity_canvas(entity_id), world_id TEXT NOT NULL REFERENCES worlds(id),
              author_actor_id TEXT NOT NULL, operator_id TEXT NOT NULL, command_id TEXT NOT NULL,
              base_revision INTEGER NOT NULL CHECK(typeof(base_revision)='integer' AND base_revision>=0),
              revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision=base_revision+1),
              patch_json TEXT NOT NULL CHECK(json_valid(patch_json)),
              state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>0),
              event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq) DEFERRABLE INITIALLY DEFERRED,
              painted_at_utc TEXT NOT NULL, x REAL NOT NULL, y REAL NOT NULL,
              inventory_wood INTEGER NOT NULL CHECK(typeof(inventory_wood)='integer' AND inventory_wood BETWEEN 0 AND 12),
              PRIMARY KEY(entity_id,author_actor_id,command_id), UNIQUE(entity_id,revision),
              FOREIGN KEY(world_id,author_actor_id) REFERENCES residents(world_id,actor_id))
            """),
        ("entity_canvas_cells", """
            CREATE TABLE entity_canvas_cells(
              entity_id TEXT NOT NULL REFERENCES entity_canvas(entity_id),
              x INTEGER NOT NULL CHECK(typeof(x)='integer' AND x BETWEEN 0 AND 4),
              y INTEGER NOT NULL CHECK(typeof(y)='integer' AND y BETWEEN 0 AND 4),
              color TEXT NOT NULL CHECK(color IN('blank','leaf','river','sun','rose','ink')),
              author_actor_id TEXT, command_id TEXT, state_version INTEGER,
              PRIMARY KEY(entity_id,x,y),
              FOREIGN KEY(entity_id,author_actor_id,command_id) REFERENCES entity_canvas_edits(entity_id,author_actor_id,command_id),
              CHECK((author_actor_id IS NULL AND command_id IS NULL AND state_version IS NULL AND color='blank') OR
                (author_actor_id IS NOT NULL AND command_id IS NOT NULL AND typeof(state_version)='integer' AND state_version>0)))
            """),
        ("immutable_canvas_adoption_update", "CREATE TRIGGER immutable_canvas_adoption_update BEFORE UPDATE OF singleton,capability,version,entity_id,instance_id,state_version,event_seq ON entity_canvas BEGIN SELECT RAISE(ABORT,'immutable canvas adoption'); END;"),
        ("immutable_canvas_adoption_delete", "CREATE TRIGGER immutable_canvas_adoption_delete BEFORE DELETE ON entity_canvas BEGIN SELECT RAISE(ABORT,'immutable canvas adoption'); END;"),
        ("immutable_canvas_edit_update", "CREATE TRIGGER immutable_canvas_edit_update BEFORE UPDATE ON entity_canvas_edits BEGIN SELECT RAISE(ABORT,'immutable canvas edit'); END;"),
        ("immutable_canvas_edit_delete", "CREATE TRIGGER immutable_canvas_edit_delete BEFORE DELETE ON entity_canvas_edits BEGIN SELECT RAISE(ABORT,'immutable canvas edit'); END;")
    ];

    private static long Integer(SqliteDataReader reader, int ordinal) => reader.GetValue(ordinal) is long value
        ? value : throw new InvalidOperationException("地画整数字段的实际存储类型无效");

    public static EntityCanvasState? Read(SqliteConnection c, SqliteTransaction t)
    {
        var tables = Scalar(c, t, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN('entity_canvas','entity_canvas_edits','entity_canvas_cells')");
        if (tables == 0) return null;
        if (tables != 3) throw new InvalidOperationException("地画存储不完整");
        using var command = Command(c, t, "SELECT singleton,capability,version,entity_id,instance_id,state_version,event_seq,revision FROM entity_canvas");
        using var r = command.ExecuteReader();
        if (!r.Read() || Integer(r, 0) != 1 || r.GetString(1) != Capability || Integer(r, 2) != 1)
            throw new InvalidOperationException("地画采用元数据不受支持");
        var state = new EntityCanvasState(r.GetString(3), r.GetString(4), Integer(r, 5), Integer(r, 6), Integer(r, 7));
        if (r.Read()) throw new InvalidOperationException("地画采用记录不唯一");
        return state;
    }

    public static NaturalStructure? Target(SqliteConnection c, SqliteTransaction t, string id)
    {
        using var q = Command(c, t, """
            SELECT entity_id,definition_id,definition_version,rules_version,owner_actor_id,x,y,embodied_wood FROM entities
            WHERE entity_id=$id AND world_id=$world AND definition_id='platform' AND definition_version=1 AND rules_version='r10' AND embodied_wood=3
            """, ("$id", id), ("$world", Protocol.WorldId));
        using var r = q.ExecuteReader();
        return r.Read() ? new(r.GetString(0), r.GetString(1), Integer(r, 2), r.GetString(3), r.GetString(4),
            [r.GetDouble(5), r.GetDouble(6)], Integer(r, 7)) : null;
    }

    public static List<EntityCanvasCell> Cells(SqliteConnection c, SqliteTransaction t)
    {
        using var q = Command(c, t, "SELECT x,y,color,author_actor_id,command_id,state_version FROM entity_canvas_cells ORDER BY y,x");
        using var r = q.ExecuteReader();
        var cells = new List<EntityCanvasCell>();
        while (r.Read()) cells.Add(new(Integer(r, 0), Integer(r, 1), r.GetString(2), r.IsDBNull(3) ? null : r.GetString(3),
            r.IsDBNull(4) ? null : r.GetString(4), r.IsDBNull(5) ? null : Integer(r, 5)));
        return cells;
    }

    public static List<EntityCanvasEdit> Edits(SqliteConnection c, SqliteTransaction t, string? actor = null, string? command = null, bool all = false)
    {
        using var q = Command(c, t, """
            SELECT entity_id,author_actor_id,operator_id,command_id,base_revision,revision,patch_json,state_version,event_seq,painted_at_utc,x,y,inventory_wood
            FROM (SELECT * FROM entity_canvas_edits WHERE ($actor IS NULL OR author_actor_id=$actor AND command_id=$command)
              ORDER BY revision DESC LIMIT $limit) ORDER BY revision
            """, ("$actor", actor), ("$command", command), ("$limit", all || actor is not null ? -1 : RecentLimit));
        using var r = q.ExecuteReader();
        var edits = new List<EntityCanvasEdit>();
        while (r.Read()) edits.Add(new(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), Integer(r, 4), Integer(r, 5),
            JsonSerializer.Deserialize<MosaicPatchCell[]>(r.GetString(6), Protocol.Json)!, Integer(r, 7), Integer(r, 8),
            r.GetString(9), [r.GetDouble(10), r.GetDouble(11)], Integer(r, 12)));
        return edits;
    }

    // Called on startup, under the clock lock, and before idempotent adoption.
    // A schema number alone never grants this capability.
    public static void ValidateStorage(SqliteConnection c, SqliteTransaction t, string? instance, long storage, MaterialProductionPolicy? policy)
    {
        var state = Read(c, t);
        if (storage != 13 && (storage == 12) != (state is not null)) throw new InvalidOperationException("地画能力与存储版本不一致");
        if (state is null)
        {
            if (storage == 13 && Scalar(c, t, "SELECT count(*) FROM events WHERE json_extract(event_json,'$.type')='entityCanvasAdopted'") != 0)
                throw new InvalidOperationException("原地画采用历史存在，但当前地画存储缺失");
            return;
        }
        if (policy is null || state.WorldInstanceId != instance || Target(c, t, state.EntityId) is null)
            throw new InvalidOperationException("地画与原持续世界或平台不匹配");
        static string Normalize(string s) => string.Concat(s.Where(ch => !char.IsWhiteSpace(ch) && ch != '"')).TrimEnd(';');
        foreach (var (name, expected) in Schema)
        {
            using var q = Command(c, t, "SELECT sql FROM sqlite_master WHERE name=$name", ("$name", name));
            if (q.ExecuteScalar() is not string actual || Normalize(actual) != Normalize(expected))
                throw new InvalidOperationException("地画存储结构不受支持");
        }
        if (Scalar(c, t, "SELECT count(*) FROM entity_canvas WHERE typeof(singleton)!='integer' OR typeof(version)!='integer' OR typeof(state_version)!='integer' OR typeof(event_seq)!='integer' OR typeof(revision)!='integer'") != 0)
            throw new InvalidOperationException("地画采用字段类型无效");
        using (var q = Command(c, t, "SELECT event_json FROM events WHERE seq=$seq AND state_version=$state", ("$seq", state.EventCursor), ("$state", state.StateVersion)))
        {
            var raw = q.ExecuteScalar() as string ?? throw new InvalidOperationException("缺少原地画采用事件");
            using var doc = JsonDocument.Parse(raw);
            var e = doc.RootElement;
            if (e.GetProperty("type").GetString() != "entityCanvasAdopted" || e.GetProperty("entityId").GetString() != state.EntityId
                || e.GetProperty("worldInstanceId").GetString() != instance || e.GetProperty("capability").GetString() != Capability
                || e.GetProperty("capabilityVersion").GetInt64() != 1 || e.GetProperty("paintRule").GetString() != PaintRule
                || e.GetProperty("seq").GetInt64() != state.EventCursor || e.GetProperty("stateVersion").GetInt64() != state.StateVersion
                || e.GetProperty("actorId").ValueKind != JsonValueKind.Null || e.GetProperty("commandId").ValueKind != JsonValueKind.Null
                || e.GetProperty("width").GetInt64() != Size || e.GetProperty("height").GetInt64() != Size
                || e.GetProperty("maxPatchCells").GetInt64() != MaxPatchCells || e.GetProperty("reach").GetDouble() != Reach)
                throw new InvalidOperationException("原地画采用事件不匹配");
        }
        var edits = Edits(c, t, all: true);
        var projected = Enumerable.Range(0, 25).Select(i => new EntityCanvasCell(i % 5, i / 5, "blank", null, null, null)).ToArray();
        long lastEvent = state.EventCursor, lastVersion = state.StateVersion;
        foreach (var edit in edits)
        {
            if (edit.EntityId != state.EntityId || edit.BaseRevision != edit.Revision - 1 || edit.Revision < 1 || edit.Revision > edits.Count
                || edit.EventCursor <= lastEvent || edit.StateVersion <= lastVersion || edit.Patch.Length is < 1 or > MaxPatchCells
                || !edit.Patch.SequenceEqual(edit.Patch.OrderBy(p => p.Y).ThenBy(p => p.X))
                || edit.Patch.Select(p => (p.X, p.Y)).Distinct().Count() != edit.Patch.Length)
                throw new InvalidOperationException("地画修改历史不一致");
            foreach (var cell in edit.Patch)
            {
                if (cell.X is < 0 or >= Size || cell.Y is < 0 or >= Size || !WorldScenario.MosaicPalette.Any(p => p.Id == cell.Color))
                    throw new InvalidOperationException("地画修改格无效");
                var index = checked((int)(cell.Y * Size + cell.X)); var previous = projected[index];
                if (previous.Color == cell.Color || previous.AuthorActorId is not null && previous.AuthorActorId != edit.AuthorActorId)
                    throw new InvalidOperationException("地画修改不符合原署名规则");
                projected[index] = new(cell.X, cell.Y, cell.Color, edit.AuthorActorId, edit.CommandId, edit.StateVersion);
            }
            using var q = Command(c, t, "SELECT event_json FROM events WHERE seq=$seq AND state_version=$state", ("$seq", edit.EventCursor), ("$state", edit.StateVersion));
            var eventRaw = q.ExecuteScalar() as string ?? throw new InvalidOperationException("缺少原地画修改事件");
            using var eventDoc = JsonDocument.Parse(eventRaw);
            var e = eventDoc.RootElement;
            if (e.GetProperty("type").GetString() != "entityCanvasPainted" || e.GetProperty("seq").GetInt64() != edit.EventCursor
                || e.GetProperty("actorId").GetString() != edit.AuthorActorId || e.GetProperty("capabilityVersion").GetInt64() != 1
                || JsonSerializer.Serialize(JsonSerializer.Deserialize<EntityCanvasEdit>(e, Protocol.Json), Protocol.Json) != JsonSerializer.Serialize(edit, Protocol.Json))
                throw new InvalidOperationException("原地画修改事件不匹配");
            lastEvent = edit.EventCursor; lastVersion = edit.StateVersion;
        }
        if (state.Revision != edits.Count || !projected.SequenceEqual(Cells(c, t)) || Scalar(c, t, "SELECT count(*) FROM pragma_foreign_key_check") != 0)
            throw new InvalidOperationException("当前地画与原修改历史不一致");
    }
}

internal sealed partial class WorldDatabase
{
    public bool AdoptEntityCanvas(string expectedInstance, string entityId)
    {
        if (!WorldInstance.Valid(expectedInstance) || !Protocol.ValidCommandId(entityId)) throw new ArgumentException("必须指定原实例和平台");
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var c = Open(); using var t = c.BeginTransaction(deferred: false);
        var storage = Scalar(c, t, "PRAGMA user_version"); Scenario = ReadScenario(c, t, storage);
        if (!Scenario.SupportsMaterialAccess || WorldInstance.Read(c, t) != expectedInstance || storage is not (11 or 12 or 13))
            throw new InvalidOperationException("只能在指定原持续材料世界采用地画");
        var policy = ContinuousMaterialRules.ReadPolicy(c, t, expectedInstance) ?? throw new InvalidOperationException("缺少原持续材料政策");
        ContinuousMaterialRules.ValidateState(c, t, policy);
        if (EntityNoteRules.ReadAdoption(c, t) is { } notes &&
            (notes.InstanceId != expectedInstance || EntityNoteRules.ReadBridge(c, t, notes.EntityId) is null))
            throw new InvalidOperationException("原手记能力或目标不匹配");
        EntityCanvasRules.ValidateStorage(c, t, expectedInstance, storage, policy);
        WorkshopRules.ValidateStorage(c, t, expectedInstance, storage, policy);
        if (EntityCanvasRules.Read(c, t) is { } previous)
        {
            if (previous.EntityId != entityId) throw new InvalidOperationException("地画不能更换原平台");
            return false;
        }
        if (EntityCanvasRules.Target(c, t, entityId) is null) throw new ArgumentException("目标不是原r10平台");
        foreach (var (_, sql) in EntityCanvasRules.Schema) Run(c, t, sql);
        var state = checked(Scalar(c, t, "SELECT state_version FROM worlds") + 1);
        var cursor = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
        var adopted = new { type = "entityCanvasAdopted", seq = cursor, stateVersion = state, actorId = (string?)null,
            commandId = (string?)null, entityId, worldInstanceId = expectedInstance, capability = EntityCanvasRules.Capability,
            capabilityVersion = 1, width = 5, height = 5, maxPatchCells = 8, reach = EntityCanvasRules.Reach, paintRule = EntityCanvasRules.PaintRule };
        Run(c, t, "UPDATE worlds SET state_version=$state", ("$state", state));
        Run(c, t, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES($seq,$world,$state,$json)",
            ("$seq", cursor), ("$world", Protocol.WorldId), ("$state", state), ("$json", JsonSerializer.Serialize(adopted, Protocol.Json)));
        Run(c, t, "INSERT INTO entity_canvas VALUES(1,$cap,1,$entity,$instance,$state,$seq,0)",
            ("$cap", EntityCanvasRules.Capability), ("$entity", entityId), ("$instance", expectedInstance), ("$state", state), ("$seq", cursor));
        for (var y = 0; y < 5; y++) for (var x = 0; x < 5; x++)
            Run(c, t, "INSERT INTO entity_canvas_cells(entity_id,x,y,color) VALUES($id,$x,$y,'blank')", ("$id", entityId), ("$x", x), ("$y", y));
        var nextStorage = storage == 13 ? 13 : 12;
        if (nextStorage == 12) Run(c, t, "PRAGMA user_version=12;");
        EntityCanvasRules.ValidateStorage(c, t, expectedInstance, nextStorage, policy);
        var fault = configuration.FaultsEnabled ? Environment.GetEnvironmentVariable("WORLD_CANVAS_ADOPTION_TEST_FAULT") : null;
        if (fault == "before-commit") Environment.Exit(87);
        t.Commit();
        if (fault == "after-commit") Environment.Exit(88);
        return true;
    }
}

internal sealed partial class WorldService
{
    private static void BindEntityCanvas(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t)
    {
        var s = EntityCanvasRules.Read(c, t); if (s is null) return;
        var target = EntityCanvasRules.Target(c, t, s.EntityId) ?? throw new InvalidOperationException("原地画平台不匹配");
        body["entityCanvas"] = new { capability = EntityCanvasRules.Capability, version = 1, width = 5, height = 5,
            reach = EntityCanvasRules.Reach, maxPatchCells = 8, paintRule = EntityCanvasRules.PaintRule, target,
            adoption = new { s.WorldInstanceId, s.StateVersion, s.EventCursor }, palette = WorldScenario.MosaicPalette,
            revision = s.Revision, editCount = s.Revision, cells = EntityCanvasRules.Cells(c, t), recentEdits = EntityCanvasRules.Edits(c, t) };
    }

    public ApiReply EntityCanvasEditDetail(string tokenHash, string entityId, string author, string command, string? expectedInstance)
    {
        using var c = database.Open(); using var t = c.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, c, t); var instance = WorldInstance.Require(c, t, expectedInstance);
        var state = ReadState(c, t); var canvas = Scenario.SupportsMaterialAccess ? EntityCanvasRules.Read(c, t) : null;
        ApiReply Error(int status, string code, string message) => Protocol.Error(Scenario.RulesVersion, status, code, message,
            identity, state.Version, state.Cursor).WithInstance(instance);
        if (canvas is null) return Error(422, "ENTITY_CANVAS_UNAVAILABLE", "当前世界尚未采用平台地画");
        if (canvas.EntityId != entityId) return Error(404, "CANVAS_TARGET_UNAVAILABLE", "目标未开放地画");
        var edit = EntityCanvasRules.Edits(c, t, author, command).SingleOrDefault();
        if (edit is null) return Error(404, "CANVAS_EDIT_NOT_FOUND", "原绘制记录不存在");
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor); body["edit"] = edit;
        return Protocol.Reply(200, body).WithInstance(instance);
    }

    private (int Status, ApiError Error)? ValidateEntityCanvas(SqliteConnection c, SqliteTransaction t, WorldAction action, Actor actor, Identity identity)
    {
        var canvas = Scenario.SupportsMaterialAccess ? EntityCanvasRules.Read(c, t) : null;
        if (canvas is null) return (422, new("ENTITY_CANVAS_UNAVAILABLE", "当前世界尚未采用平台地画"));
        var target = EntityCanvasRules.Target(c, t, canvas.EntityId);
        if (action.EntityId != canvas.EntityId || target is null) return (404, new("CANVAS_TARGET_UNAVAILABLE", "目标未开放地画"));
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t);
        if (ContinuousWorld.Distance(actor.X, actor.Y, target.Position[0], target.Position[1]) > EntityCanvasRules.Reach
            || !ContinuousWorld.Walkable(actor.X, actor.Y, trees, entities)
            || ContinuousWorld.Sweep(actor.X, actor.Y, target.Position[0], target.Position[1], trees, entities).Blocked)
            return (422, new("UNREACHABLE", "请走到原平台中心1.6米内且中间没有障碍"));
        if (action.ExpectedCanvasRevision != canvas.Revision) return (409, new("CANVAS_REVISION_MISMATCH", "地画已更新，原草图保留；请明确确认新基准"));
        var cells = EntityCanvasRules.Cells(c, t).ToDictionary(p => (p.X, p.Y));
        if (action.Patch!.Any(p => cells[(p.X, p.Y)].AuthorActorId is { } author && author != identity.ActorId))
            return (409, new("CANVAS_CONSENT_REQUIRED", "不能直接覆盖其他居民的格子，原草图保留"));
        if (action.Patch!.Any(p => cells[(p.X, p.Y)].Color == p.Color)) return (422, new("CANVAS_UNCHANGED", "提交批次包含颜色未变化的格子"));
        return null;
    }

    private static (object Result, object Event) ApplyEntityCanvas(SqliteConnection c, SqliteTransaction t,
        WorldCommand request, Identity identity, Actor actor, long version, long cursor)
    {
        var a = request.Action;
        var edit = new EntityCanvasEdit(a.EntityId!, identity.ActorId, identity.OperatorId, request.CommandId,
            a.ExpectedCanvasRevision, checked(a.ExpectedCanvasRevision + 1), a.Patch!, version, cursor, DateTimeOffset.UtcNow.ToString("O"), [actor.X, actor.Y], actor.Wood);
        Run(c, t, "INSERT INTO entity_canvas_edits VALUES($entity,$world,$actor,$operator,$command,$base,$revision,$patch,$state,$seq,$utc,$x,$y,$wood)",
            ("$entity", edit.EntityId), ("$world", Protocol.WorldId), ("$actor", edit.AuthorActorId), ("$operator", edit.OperatorId),
            ("$command", edit.CommandId), ("$base", edit.BaseRevision), ("$revision", edit.Revision), ("$patch", JsonSerializer.Serialize(edit.Patch, Protocol.Json)),
            ("$state", edit.StateVersion), ("$seq", edit.EventCursor), ("$utc", edit.PaintedAtUtc), ("$x", actor.X), ("$y", actor.Y), ("$wood", actor.Wood));
        foreach (var p in edit.Patch)
            GuardedDebit(Run(c, t, "UPDATE entity_canvas_cells SET color=$color,author_actor_id=$actor,command_id=$command,state_version=$state WHERE entity_id=$entity AND x=$x AND y=$y",
                ("$color", p.Color), ("$actor", identity.ActorId), ("$command", request.CommandId), ("$state", version), ("$entity", a.EntityId), ("$x", p.X), ("$y", p.Y)));
        GuardedDebit(Run(c, t, "UPDATE entity_canvas SET revision=$revision WHERE entity_id=$id AND revision=$base",
            ("$revision", edit.Revision), ("$id", a.EntityId), ("$base", edit.BaseRevision)));
        return (WithFields(edit, ("action", "paint_entity_canvas")), WithFields(edit, ("type", "entityCanvasPainted"), ("seq", cursor), ("actorId", identity.ActorId)));
    }
}
