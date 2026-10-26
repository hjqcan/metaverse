using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record WorkshopAdoption(string WorldInstanceId, long StateVersion, long EventCursor, long BaseStorageVersion);
internal sealed record WorkshopTool(string ToolId, string OwnerActorId, string WorkbenchId, string CommandId, long StateVersion, long EventCursor)
{
    public string DefinitionId => "wooden_mallet";
    public int DefinitionVersion => 1;
    public int EmbodiedWood => 1;
}
internal sealed record WorkshopActionDetail(string AuthorActorId, string OperatorId, string CommandId, JsonElement Action,
    NaturalStructure Entity, WorkshopTool? Tool, long Quantity, long InventoryWoodBefore, long InventoryWood,
    long? StoredWoodBefore, long? StoredWood, double[] Position, long StateVersion, long EventCursor, string CompletedAtUtc)
{
    public int CapabilityVersion => 1;
}

internal static class WorkshopRules
{
    public const string Capability = "workshop-v1", Header = "World-Capabilities";
    public const double Reach = 1.6;
    public static bool IsAction(string type) => type is "build_workshop" or "craft_tool" or "deposit_wood" or "withdraw_wood";
    public static bool IsFurniture(NaturalStructure e) => e.DefinitionId is "workbench" or "wooden_chest";
    public static readonly (string Id, string Definition, int Wood)[] Recipes =
        [("workbench.v1", "workbench", 3), ("wooden_mallet.v1", "wooden_mallet", 1), ("wooden_chest.v1", "wooden_chest", 3)];
    public static readonly (string Name, string Sql)[] Schema =
    [
        ("workshop", """
            CREATE TABLE workshop(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), capability TEXT NOT NULL CHECK(capability='workshop-v1'),
              version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version=1),
              instance_id TEXT NOT NULL REFERENCES world_instance(instance_id),
              state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>0),
              event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
              base_storage_version INTEGER NOT NULL CHECK(typeof(base_storage_version)='integer' AND base_storage_version IN(11,12)))
            """),
        ("workshop_actions", """
            CREATE TABLE workshop_actions(
              world_id TEXT NOT NULL REFERENCES worlds(id), actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
              state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>0),
              event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq) DEFERRABLE INITIALLY DEFERRED,
              detail_json TEXT NOT NULL CHECK(json_valid(detail_json)), PRIMARY KEY(actor_id,command_id),
              FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
              FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED)
            """),
        ("workshop_tools", """
            CREATE TABLE workshop_tools(
              tool_id TEXT PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), owner_actor_id TEXT NOT NULL,
              workbench_id TEXT NOT NULL REFERENCES entities(entity_id), command_id TEXT NOT NULL,
              state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>0),
              event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq) DEFERRABLE INITIALLY DEFERRED,
              FOREIGN KEY(owner_actor_id,command_id) REFERENCES workshop_actions(actor_id,command_id) DEFERRABLE INITIALLY DEFERRED,
              FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id))
            """),
        ("workshop_chests", """
            CREATE TABLE workshop_chests(
              entity_id TEXT PRIMARY KEY REFERENCES entities(entity_id),
              wood INTEGER NOT NULL CHECK(typeof(wood)='integer' AND wood BETWEEN 0 AND 12))
            """),
        ("immutable_workshop_update", "CREATE TRIGGER immutable_workshop_update BEFORE UPDATE ON workshop BEGIN SELECT RAISE(ABORT,'immutable workshop'); END;"),
        ("immutable_workshop_delete", "CREATE TRIGGER immutable_workshop_delete BEFORE DELETE ON workshop BEGIN SELECT RAISE(ABORT,'immutable workshop'); END;"),
        ("immutable_workshop_action_update", "CREATE TRIGGER immutable_workshop_action_update BEFORE UPDATE ON workshop_actions BEGIN SELECT RAISE(ABORT,'immutable workshop action'); END;"),
        ("immutable_workshop_action_delete", "CREATE TRIGGER immutable_workshop_action_delete BEFORE DELETE ON workshop_actions BEGIN SELECT RAISE(ABORT,'immutable workshop action'); END;"),
        ("immutable_workshop_tool_update", "CREATE TRIGGER immutable_workshop_tool_update BEFORE UPDATE ON workshop_tools BEGIN SELECT RAISE(ABORT,'immutable workshop tool'); END;"),
        ("immutable_workshop_tool_delete", "CREATE TRIGGER immutable_workshop_tool_delete BEFORE DELETE ON workshop_tools BEGIN SELECT RAISE(ABORT,'immutable workshop tool'); END;"),
        ("immutable_workshop_chest_identity", "CREATE TRIGGER immutable_workshop_chest_identity BEFORE UPDATE OF entity_id ON workshop_chests BEGIN SELECT RAISE(ABORT,'immutable workshop chest'); END;"),
        ("immutable_workshop_chest_delete", "CREATE TRIGGER immutable_workshop_chest_delete BEFORE DELETE ON workshop_chests BEGIN SELECT RAISE(ABORT,'immutable workshop chest'); END;")
    ];
    private static long Integer(SqliteDataReader r, int i) => r.GetValue(i) is long value ? value
        : throw new InvalidOperationException("工作坊整数字段类型无效");
    public static WorkshopAdoption? Read(SqliteConnection c, SqliteTransaction t)
    {
        var count = Scalar(c, t, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN('workshop','workshop_actions','workshop_tools','workshop_chests')");
        if (count == 0) return null;
        if (count != 4) throw new InvalidOperationException("工作坊存储不完整");
        using var q = Command(c, t, "SELECT singleton,capability,version,instance_id,state_version,event_seq,base_storage_version FROM workshop");
        using var r = q.ExecuteReader();
        if (!r.Read() || Integer(r, 0) != 1 || r.GetString(1) != Capability || Integer(r, 2) != 1)
            throw new InvalidOperationException("工作坊采用记录无效");
        var adoption = new WorkshopAdoption(r.GetString(3), Integer(r, 4), Integer(r, 5), Integer(r, 6));
        if (r.Read()) throw new InvalidOperationException("工作坊采用记录不唯一");
        return adoption;
    }
    public static (long Tools, long Stored) Wood(SqliteConnection c, SqliteTransaction t) => Read(c, t) is null ? (0, 0)
        : (Scalar(c, t, "SELECT count(*) FROM workshop_tools"), Scalar(c, t, "SELECT coalesce(sum(wood),0) FROM workshop_chests"));
    public static List<WorkshopTool> Tools(SqliteConnection c, SqliteTransaction t, string? owner = null)
    {
        using var q = Command(c, t, "SELECT tool_id,owner_actor_id,workbench_id,command_id,state_version,event_seq FROM workshop_tools WHERE $owner IS NULL OR owner_actor_id=$owner ORDER BY tool_id", ("$owner", owner));
        using var r = q.ExecuteReader(); var result = new List<WorkshopTool>();
        while (r.Read()) result.Add(new(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), Integer(r, 4), Integer(r, 5)));
        return result;
    }
    public static long ChestWood(SqliteConnection c, SqliteTransaction t, string entity) => Scalar(c, t,
        "SELECT wood FROM workshop_chests WHERE entity_id=$entity", ("$entity", entity));
    public static List<WorkshopActionDetail> Actions(SqliteConnection c, SqliteTransaction t, string? actor = null, string? command = null)
    {
        using var q = Command(c, t, "SELECT detail_json FROM workshop_actions WHERE $actor IS NULL OR actor_id=$actor AND command_id=$command ORDER BY event_seq", ("$actor", actor), ("$command", command));
        using var r = q.ExecuteReader(); var result = new List<WorkshopActionDetail>();
        while (r.Read()) result.Add(JsonSerializer.Deserialize<WorkshopActionDetail>(r.GetString(0), Protocol.Json)
            ?? throw new InvalidOperationException("工作坊动作记录无效"));
        return result;
    }
    public static void ValidateStorage(SqliteConnection c, SqliteTransaction t, string? instance, long storage, MaterialProductionPolicy? policy)
    {
        var adoption = Read(c, t);
        if ((storage is 13 or 14) != (adoption is not null)) throw new InvalidOperationException("工作坊能力与存储版本不一致");
        if (adoption is null) return;
        if (policy is null || adoption.WorldInstanceId != instance || adoption.BaseStorageVersion is not (11 or 12)
            || adoption.BaseStorageVersion == 12 && EntityCanvasRules.Read(c, t) is null)
            throw new InvalidOperationException("工作坊采用不属于原持续世界");
        static string Normalize(string s) => string.Concat(s.Where(ch => !char.IsWhiteSpace(ch) && ch != '"')).TrimEnd(';');
        foreach (var (name, expected) in Schema)
        {
            using var q = Command(c, t, "SELECT sql FROM sqlite_master WHERE name=$name", ("$name", name));
            if (q.ExecuteScalar() is not string sql || Normalize(sql) != Normalize(expected))
                throw new InvalidOperationException("工作坊存储结构不受支持");
        }
        foreach (var recipe in Recipes)
            if (Scalar(c, t, "SELECT count(*) FROM recipes WHERE id=$id AND definition_id=$definition AND definition_version=1 AND rules_version='r10' AND wood_cost=$wood",
                ("$id", recipe.Id), ("$definition", recipe.Definition), ("$wood", recipe.Wood)) != 1)
                throw new InvalidOperationException("工作坊配方不一致");
        using (var q = Command(c, t, "SELECT event_json FROM events WHERE seq=$seq AND state_version=$state", ("$seq", adoption.EventCursor), ("$state", adoption.StateVersion)))
        {
            using var doc = JsonDocument.Parse(q.ExecuteScalar() as string ?? throw new InvalidOperationException("缺少工作坊采用事件"));
            var e = doc.RootElement;
            if (e.GetProperty("type").GetString() != "workshopAdopted" || e.GetProperty("capability").GetString() != Capability
                || e.GetProperty("capabilityVersion").GetInt64() != 1 || e.GetProperty("worldInstanceId").GetString() != instance
                || e.GetProperty("seq").GetInt64() != adoption.EventCursor || e.GetProperty("stateVersion").GetInt64() != adoption.StateVersion
                || e.GetProperty("baseStorageVersion").GetInt64() != adoption.BaseStorageVersion
                || e.GetProperty("actorId").ValueKind != JsonValueKind.Null || e.GetProperty("commandId").ValueKind != JsonValueKind.Null)
                throw new InvalidOperationException("工作坊采用事件不匹配");
        }
        var balances = new Dictionary<string, long>(); var bornTools = new Dictionary<string, WorkshopTool>();
        var bornEntities = new Dictionary<string, NaturalStructure>();
        long previousEvent = adoption.EventCursor, previousState = adoption.StateVersion;
        foreach (var detail in Actions(c, t))
        {
            var a = detail.Action; var type = a.GetProperty("type").GetString()!;
            if (!IsAction(type) || a.GetProperty("capabilityVersion").GetInt64() != 1 || detail.CapabilityVersion != 1
                || detail.EventCursor <= previousEvent || detail.StateVersion <= previousState || detail.Quantity is < 1 or > 12
                || detail.InventoryWoodBefore is < 0 or > 12 || detail.InventoryWood is < 0 or > 12
                || detail.Position.Length != 2 || detail.Position.Any(v => !double.IsFinite(v))
                || !DateTimeOffset.TryParse(detail.CompletedAtUtc, out _) || detail.Entity.RulesVersion != "r10"
                || detail.Entity.DefinitionVersion != 1 || detail.Entity.EmbodiedWood != 3)
                throw new InvalidOperationException("工作坊动作事实无效");
            var delta = type == "withdraw_wood" ? detail.Quantity : -detail.Quantity;
            if (detail.InventoryWoodBefore + delta != detail.InventoryWood)
                throw new InvalidOperationException("工作坊动作库存不守恒");
            var entity = detail.Entity; string source = "inventory:" + detail.AuthorActorId, destination;
            if (type == "build_workshop")
            {
                var recipe = a.GetProperty("recipeId").GetString();
                if (detail.Quantity != 3 || recipe != entity.DefinitionId + ".v1" || !IsFurniture(entity)
                    || entity.OwnerActorId != detail.AuthorActorId || !bornEntities.TryAdd(entity.EntityId, entity)
                    || JsonSerializer.Serialize(entity.Position, Protocol.Json) != a.GetProperty("at").GetRawText())
                    throw new InvalidOperationException("家具建造原事实不匹配");
                if (entity.DefinitionId == "wooden_chest")
                {
                    if (detail.Tool is null || a.GetProperty("toolId").GetString() != detail.Tool.ToolId
                        || detail.Tool.OwnerActorId != detail.AuthorActorId || !bornTools.TryGetValue(detail.Tool.ToolId, out var own) || own != detail.Tool
                        || detail.StoredWoodBefore != 0 || detail.StoredWood != 0)
                        throw new InvalidOperationException("原建箱工具或初始库存不匹配");
                    balances.Add(entity.EntityId, 0);
                }
                else if (detail.Tool is not null || a.GetProperty("toolId").ValueKind != JsonValueKind.Null || detail.StoredWood is not null || detail.StoredWoodBefore is not null)
                    throw new InvalidOperationException("工作台原材料不匹配");
                destination = "entity:" + entity.EntityId;
            }
            else
            {
                if (a.GetProperty("entityId").GetString() != entity.EntityId || !bornEntities.TryGetValue(entity.EntityId, out var original)
                    || JsonSerializer.Serialize(original, Protocol.Json) != JsonSerializer.Serialize(entity, Protocol.Json))
                    throw new InvalidOperationException("原工作坊目标不匹配");
                if (type == "craft_tool")
                {
                    var tool = detail.Tool;
                    if (entity.DefinitionId != "workbench" || a.GetProperty("recipeId").GetString() != "wooden_mallet.v1"
                        || detail.Quantity != 1 || tool is null || tool.OwnerActorId != detail.AuthorActorId || tool.WorkbenchId != entity.EntityId
                        || tool.CommandId != detail.CommandId || tool.StateVersion != detail.StateVersion || tool.EventCursor != detail.EventCursor
                        || !bornTools.TryAdd(tool.ToolId, tool) || detail.StoredWood is not null || detail.StoredWoodBefore is not null)
                        throw new InvalidOperationException("工具制作原事实不匹配");
                    destination = "tool:" + tool.ToolId;
                }
                else
                {
                    if (entity.OwnerActorId != detail.AuthorActorId || entity.DefinitionId != "wooden_chest" || detail.Tool is not null
                        || a.GetProperty("quantity").GetInt64() != detail.Quantity || !balances.TryGetValue(entity.EntityId, out var stock)
                        || stock != detail.StoredWoodBefore || detail.StoredWood != stock - delta || detail.StoredWood is < 0 or > 12)
                        throw new InvalidOperationException("箱内库存与原存取历史不一致");
                    balances[entity.EntityId] = detail.StoredWood.Value;
                    destination = "chest:" + entity.EntityId;
                    if (type == "withdraw_wood") (source, destination) = (destination, source);
                }
            }
            var serialized = JsonSerializer.Serialize(detail, Protocol.Json);
            using var linked = Command(c, t, """
                SELECT a.actor_id,a.command_id,a.state_version,a.event_seq,e.event_json,r.result_json,l.source_account,l.destination_account,l.quantity
                FROM workshop_actions a JOIN events e ON e.seq=a.event_seq AND e.state_version=a.state_version
                JOIN receipts r ON r.world_id=a.world_id AND r.actor_id=a.actor_id AND r.command_id=a.command_id AND r.status_code=200
                JOIN resource_ledger l ON l.event_seq=a.event_seq AND l.actor_id=a.actor_id AND l.command_id=a.command_id
                JOIN residents p ON p.world_id=a.world_id AND p.actor_id=a.actor_id AND p.operator_id=$operator
                WHERE a.actor_id=$actor AND a.command_id=$command
                """, ("$actor", detail.AuthorActorId), ("$command", detail.CommandId), ("$operator", detail.OperatorId));
            using var r = linked.ExecuteReader();
            if (!r.Read() || r.GetString(0) != detail.AuthorActorId || r.GetString(1) != detail.CommandId
                || Integer(r, 2) != detail.StateVersion || Integer(r, 3) != detail.EventCursor
                || r.GetString(6) != source || r.GetString(7) != destination || Integer(r, 8) != detail.Quantity)
                throw new InvalidOperationException("工作坊原回执或账本不匹配");
            using var ev = JsonDocument.Parse(r.GetString(4)); using var receipt = JsonDocument.Parse(r.GetString(5));
            var e2 = ev.RootElement; var re = receipt.RootElement;
            if (e2.GetProperty("type").GetString() != "workshopActionCompleted" || e2.GetProperty("actorId").GetString() != detail.AuthorActorId
                || e2.GetProperty("commandId").GetString() != detail.CommandId || e2.GetProperty("seq").GetInt64() != detail.EventCursor
                || e2.GetProperty("stateVersion").GetInt64() != detail.StateVersion || e2.GetProperty("workshopAction").GetRawText() != serialized
                || re.GetProperty("status").GetString() != "committed" || re.GetProperty("commandId").GetString() != detail.CommandId
                || re.GetProperty("identity").GetProperty("actorId").GetString() != detail.AuthorActorId
                || re.GetProperty("stateVersion").GetInt64() != detail.StateVersion || re.GetProperty("eventCursor").GetInt64() != detail.EventCursor
                || re.GetProperty("result").GetProperty("action").GetString() != type
                || re.GetProperty("result").GetProperty("workshopAction").GetRawText() != serialized)
                throw new InvalidOperationException("工作坊原事件与回执事实不匹配");
            previousEvent = detail.EventCursor; previousState = detail.StateVersion;
        }
        foreach (var entity in bornEntities.Values)
        {
            if (Scalar(c, t, """
                SELECT count(*) FROM entities WHERE entity_id=$id AND world_id=$world AND owner_actor_id=$actor
                  AND recipe_id=$recipe AND definition_id=$definition AND definition_version=1 AND rules_version='r10'
                  AND x=$x AND y=$y AND embodied_wood=3
                """, ("$id", entity.EntityId), ("$world", Protocol.WorldId), ("$actor", entity.OwnerActorId),
                ("$recipe", entity.DefinitionId + ".v1"), ("$definition", entity.DefinitionId), ("$x", entity.Position[0]), ("$y", entity.Position[1])) != 1)
                throw new InvalidOperationException("家具与原建造事实不一致");
        }
        if (Scalar(c, t, "SELECT count(*) FROM entities WHERE definition_id IN('workbench','wooden_chest')") != bornEntities.Count
            || Scalar(c, t, "SELECT count(*) FROM workshop_chests") != balances.Count
            || !Tools(c, t).OrderBy(x => x.ToolId).SequenceEqual(bornTools.Values.OrderBy(x => x.ToolId))
            || balances.Any(pair => ChestWood(c, t, pair.Key) != pair.Value)
            || Scalar(c, t, "SELECT count(*) FROM pragma_foreign_key_check") != 0)
            throw new InvalidOperationException("工作坊当前产物与原历史不一致");
    }
}

internal sealed partial class WorldDatabase
{
    public bool AdoptWorkshop(string expectedInstance)
    {
        if (!WorldInstance.Valid(expectedInstance)) throw new ArgumentException("必须指定原实例");
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var c = Open(); using var t = c.BeginTransaction(deferred: false);
        var storage = Scalar(c, t, "PRAGMA user_version"); Scenario = ReadScenario(c, t, storage);
        if (!Scenario.SupportsMaterialAccess || WorldInstance.Read(c, t) != expectedInstance || storage is not (11 or 12 or 13 or 14))
            throw new InvalidOperationException("工作坊只能在原持续材料世界显式采用");
        var policy = ContinuousMaterialRules.ReadPolicy(c, t, expectedInstance) ?? throw new InvalidOperationException("缺少持续材料政策");
        ContinuousMaterialRules.ValidateState(c, t, policy);
        EntityCanvasRules.ValidateStorage(c, t, expectedInstance, storage, policy);
        WorkshopRules.ValidateStorage(c, t, expectedInstance, storage, policy);
        ForestryRules.ValidateStorage(c, t, expectedInstance, storage);
        if (WorkshopRules.Read(c, t) is not null) return false;
        foreach (var (_, sql) in WorkshopRules.Schema) Run(c, t, sql);
        foreach (var recipe in WorkshopRules.Recipes)
            Run(c, t, "INSERT INTO recipes VALUES($id,$definition,1,'r10',$wood)", ("$id", recipe.Id), ("$definition", recipe.Definition), ("$wood", recipe.Wood));
        var state = checked(Scalar(c, t, "SELECT state_version FROM worlds") + 1);
        var cursor = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
        var adopted = new { type = "workshopAdopted", seq = cursor, stateVersion = state, actorId = (string?)null,
            commandId = (string?)null, worldInstanceId = expectedInstance, capability = WorkshopRules.Capability,
            capabilityVersion = 1, baseStorageVersion = storage };
        Run(c, t, "UPDATE worlds SET state_version=$state", ("$state", state));
        Run(c, t, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES($seq,$world,$state,$json)",
            ("$seq", cursor), ("$world", Protocol.WorldId), ("$state", state), ("$json", JsonSerializer.Serialize(adopted, Protocol.Json)));
        Run(c, t, "INSERT INTO workshop VALUES(1,'workshop-v1',1,$instance,$state,$event,$base)",
            ("$instance", expectedInstance), ("$state", state), ("$event", cursor), ("$base", storage));
        Run(c, t, "PRAGMA user_version=13;");
        WorkshopRules.ValidateStorage(c, t, expectedInstance, 13, policy);
        var fault = configuration.FaultsEnabled ? Environment.GetEnvironmentVariable("WORLD_WORKSHOP_ADOPTION_TEST_FAULT") : null;
        if (fault == "before-commit") Environment.Exit(89);
        t.Commit();
        if (fault == "after-commit") Environment.Exit(90);
        return true;
    }
}

internal sealed partial class WorldService
{
    private static void BindWorkshop(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t, Identity identity, IReadOnlyList<NaturalStructure> entities)
    {
        var s = WorkshopRules.Read(c, t); if (s is null) return;
        body["workshop"] = new { capability = WorkshopRules.Capability, version = 1, buildReach = ContinuousWorld.BuildReach,
            interactReach = WorkshopRules.Reach, inventoryCapacity = 12, chestCapacity = 12, workbenchAccess = "public", chestAccess = "owner",
            adoption = new { s.WorldInstanceId, s.StateVersion, s.EventCursor },
            recipes = WorkshopRules.Recipes.Select(r => new { id = r.Id, definitionId = r.Definition, woodCost = r.Wood,
                requiresWorkbench = r.Definition == "wooden_mallet", requiresTool = r.Definition == "wooden_chest" }),
            workbenches = entities.Where(e => e.DefinitionId == "workbench"), tools = WorkshopRules.Tools(c, t, identity.ActorId),
            chests = entities.Where(e => e.DefinitionId == "wooden_chest" && e.OwnerActorId == identity.ActorId)
                .Select(e => new { entity = e, storedWood = WorkshopRules.ChestWood(c, t, e.EntityId), capacity = 12 }).ToArray() };
    }
    public ApiReply WorkshopActionDetail(string tokenHash, string author, string command, string? expectedInstance)
    {
        using var c = database.Open(); using var t = c.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, c, t); var instance = WorldInstance.Require(c, t, expectedInstance);
        var state = ReadState(c, t);
        ApiReply Error(int status, string code, string message) => Protocol.Error(Scenario.RulesVersion, status, code, message,
            identity, state.Version, state.Cursor).WithInstance(instance);
        if (!Scenario.SupportsMaterialAccess || WorkshopRules.Read(c, t) is null) return Error(422, "WORKSHOP_UNAVAILABLE", "当前世界尚未采用工作坊");
        if (identity.ActorId != author) return Error(403, "WORKSHOP_ACCESS_DENIED", "只能查询本人的工作坊动作");
        var detail = WorkshopRules.Actions(c, t, author, command).SingleOrDefault();
        if (detail is null) return Error(404, "WORKSHOP_ACTION_NOT_FOUND", "未找到原工作坊动作");
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor); body["workshopAction"] = detail;
        return Protocol.Reply(200, body).WithInstance(instance);
    }
    private (int Status, ApiError Error)? ValidateWorkshop(SqliteConnection c, SqliteTransaction t, WorldAction a, Actor actor, Identity identity)
    {
        if (!Scenario.SupportsMaterialAccess || WorkshopRules.Read(c, t) is null) return (422, new("WORKSHOP_UNAVAILABLE", "当前世界尚未采用工作坊"));
        var entities = ReadStructures(c, t); var trees = ReadResourceNodes(c, t);
        if (a.Type == "build_workshop")
        {
            if (a.RecipeId == "wooden_chest.v1")
            {
                if (a.ToolId is null) return (422, new("TOOL_REQUIRED", "建箱须指定本人的木工锤"));
                if (!WorkshopRules.Tools(c, t, identity.ActorId).Any(tool => tool.ToolId == a.ToolId))
                    return (403, new("TOOL_NOT_OWNED", "不能使用不属于本人的工具"));
            }
            var x = a.TargetX; var z = a.TargetY; var hx = a.RecipeId == "workbench.v1" ? 1.0 : 0.5; const double hz = 0.5;
            if (x - hx < 0 || x + hx > 32 || z - hz < 0 || z + hz > 24 || ContinuousWorld.Distance(actor.X, actor.Y, x, z) > ContinuousWorld.BuildReach)
                return (422, new("UNREACHABLE", "建造中心须在3.2米内，占地须在地图内"));
            var heights = ContinuousWorld.Centerline.Select(p => p[1]).Where(v => v > z - hz && v < z + hz).Append(z - hz).Append(z + hz);
            if (heights.Any(v => x + hx > ContinuousWorld.RiverX(v) - 1.4 && x - hx < ContinuousWorld.RiverX(v) + 1.4))
                return (422, new("UNREACHABLE", "家具占地须完整处于陆地"));
            if (ForestryRules.BuildExcluded(c, t, x, z, hx, hz)) return (409, new("AREA_OCCUPIED", "公共育林保留区不能建造"));
            if (x + hx > 27 && x - hx < 29 && z + hz > 9 && z - hz < 11)
                return (409, new("AREA_OCCUPIED", "来源区域须保持空闲"));
            bool Overlap(double cx, double cz, double r) => ContinuousWorld.Distance(cx, cz, Math.Clamp(cx, x - hx, x + hx), Math.Clamp(cz, z - hz, z + hz)) < r;
            if (ContinuousWorld.Rocks.Any(r => Overlap(r.Position[0], r.Position[1], r.Radius))
                || trees.Any(n => n.RemainingWood > 0 && Overlap(n.Position[0], n.Position[1], ContinuousWorld.TreeRadius))
                || entities.Any(e => { var h = ContinuousWorld.HalfSize(e); return Math.Abs(e.Position[0] - x) < h.X + hx && Math.Abs(e.Position[1] - z) < h.Z + hz; }))
                return (409, new("AREA_OCCUPIED", "占地碰到树、岩石或既有建筑"));
            using (var q = Command(c, t, "SELECT x,y FROM residents"))
            using (var r = q.ExecuteReader()) while (r.Read()) if (Overlap(r.GetDouble(0), r.GetDouble(1), ContinuousWorld.Radius))
                return (409, new("AREA_OCCUPIED", "占地碰到居民"));
            return actor.Wood < 3 ? (422, new("INSUFFICIENT_RESOURCE", "建造需要3木材")) : null;
        }
        var target = entities.SingleOrDefault(e => e.EntityId == a.EntityId && e.DefinitionId == (a.Type == "craft_tool" ? "workbench" : "wooden_chest"));
        if (target is null) return (404, new("WORKSHOP_TARGET_UNAVAILABLE", "指定工作台或箱子不存在"));
        if (a.Type != "craft_tool" && target.OwnerActorId != identity.ActorId) return (403, new("WORKSHOP_ACCESS_DENIED", "只有箱主能存取"));
        if (ContinuousWorld.Distance(actor.X, actor.Y, target.Position[0], target.Position[1]) > WorkshopRules.Reach
            || !ContinuousWorld.Walkable(actor.X, actor.Y, trees, entities, ForestryRules.Obstacles(c, t))
            || ContinuousWorld.Sweep(actor.X, actor.Y, target.Position[0], target.Position[1], trees, entities.Where(e => e.EntityId != target.EntityId).ToArray(), ForestryRules.Obstacles(c, t)).Blocked)
            return (422, new("UNREACHABLE", "须走到目标1.6米内且途中无障碍"));
        if (a.Type == "craft_tool") return actor.Wood < 1 ? (422, new("INSUFFICIENT_RESOURCE", "制锤需要1木材")) : null;
        var stored = WorkshopRules.ChestWood(c, t, target.EntityId);
        if (a.Type == "deposit_wood")
        {
            if (actor.Wood < a.Quantity) return (422, new("INSUFFICIENT_RESOURCE", "本人木材不足"));
            if (stored + a.Quantity > 12) return (422, new("CHEST_CAPACITY_EXCEEDED", "箱子最多保存12木材"));
        }
        else
        {
            if (stored < a.Quantity) return (422, new("INSUFFICIENT_RESOURCE", "箱内木材不足"));
            if (actor.Wood + a.Quantity > 12) return (422, new("INVENTORY_CAPACITY_EXCEEDED", "个人携带最多12木材"));
        }
        return null;
    }
    private (object Result, object Event, string Source, string Destination, long Quantity) ApplyWorkshop(
        SqliteConnection c, SqliteTransaction t, WorldCommand request, Identity identity, Actor actor, long state, long cursor, string? fault)
    {
        var a = request.Action; var quantity = a.Type == "build_workshop" ? 3 : a.Type == "craft_tool" ? 1 : a.Quantity;
        var delta = a.Type == "withdraw_wood" ? quantity : -quantity;
        NaturalStructure entity; WorkshopTool? tool = null; long? before = null, after = null;
        string source = "inventory:" + identity.ActorId, destination;
        if (a.Type == "withdraw_wood")
        {
            before = WorkshopRules.ChestWood(c, t, a.EntityId!); after = before - quantity;
            GuardedDebit(Run(c, t, "UPDATE workshop_chests SET wood=wood-$qty WHERE entity_id=$entity AND wood>=$qty", ("$qty", quantity), ("$entity", a.EntityId)));
            InjectAfterDebit(fault);
        }
        GuardedDebit(Run(c, t, "UPDATE residents SET wood=wood+$delta WHERE world_id=$world AND actor_id=$actor AND wood+$delta BETWEEN 0 AND 12",
            ("$delta", delta), ("$world", Protocol.WorldId), ("$actor", identity.ActorId)));
        if (a.Type != "withdraw_wood") InjectAfterDebit(fault);
        if (a.Type == "build_workshop")
        {
            var id = "e" + Guid.NewGuid().ToString("N"); var definition = a.RecipeId == "workbench.v1" ? "workbench" : "wooden_chest";
            entity = new(id, definition, 1, "r10", identity.ActorId, [a.TargetX, a.TargetY], 3);
            Run(c, t, "INSERT INTO entities VALUES($id,$world,$actor,$recipe,$definition,1,'r10',$x,$y,3)",
                ("$id", id), ("$world", Protocol.WorldId), ("$actor", identity.ActorId), ("$recipe", a.RecipeId),
                ("$definition", definition), ("$x", a.TargetX), ("$y", a.TargetY));
            if (definition == "wooden_chest")
            {
                tool = WorkshopRules.Tools(c, t, identity.ActorId).Single(item => item.ToolId == a.ToolId);
                Run(c, t, "INSERT INTO workshop_chests VALUES($id,0)", ("$id", id)); before = after = 0;
            }
            destination = "entity:" + id;
        }
        else
        {
            entity = ReadStructures(c, t).Single(e => e.EntityId == a.EntityId);
            if (a.Type == "craft_tool")
            {
                tool = new("t" + Guid.NewGuid().ToString("N"), identity.ActorId, entity.EntityId, request.CommandId, state, cursor);
                Run(c, t, "INSERT INTO workshop_tools VALUES($id,$world,$actor,$bench,$command,$state,$seq)",
                    ("$id", tool.ToolId), ("$world", Protocol.WorldId), ("$actor", identity.ActorId), ("$bench", entity.EntityId),
                    ("$command", request.CommandId), ("$state", state), ("$seq", cursor));
                destination = "tool:" + tool.ToolId;
            }
            else
            {
                if (a.Type == "deposit_wood")
                {
                    before = WorkshopRules.ChestWood(c, t, entity.EntityId); after = before + quantity;
                    GuardedDebit(Run(c, t, "UPDATE workshop_chests SET wood=wood+$qty WHERE entity_id=$entity AND wood+$qty<=12", ("$qty", quantity), ("$entity", entity.EntityId)));
                }
                destination = "chest:" + entity.EntityId;
                if (a.Type == "withdraw_wood") (source, destination) = (destination, source);
            }
        }
        var detail = new WorkshopActionDetail(identity.ActorId, identity.OperatorId, request.CommandId,
            JsonSerializer.SerializeToElement(a.Canonical, Protocol.Json), entity, tool, quantity, actor.Wood, actor.Wood + delta,
            before, after, [actor.X, actor.Y], state, cursor, DateTimeOffset.UtcNow.ToString("O"));
        Run(c, t, "INSERT INTO workshop_actions VALUES($world,$actor,$command,$state,$seq,$detail)",
            ("$world", Protocol.WorldId), ("$actor", identity.ActorId), ("$command", request.CommandId), ("$state", state),
            ("$seq", cursor), ("$detail", JsonSerializer.Serialize(detail, Protocol.Json)));
        return (new { action = a.Type, workshopAction = detail }, new { seq = cursor, stateVersion = state,
            actorId = identity.ActorId, commandId = request.CommandId, type = "workshopActionCompleted", workshopAction = detail }, source, destination, quantity);
    }
}
