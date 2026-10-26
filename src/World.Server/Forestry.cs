using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record ForestryAdoption(string WorldInstanceId, long AdoptedServiceMs, long StateVersion, long EventCursor, long BaseStorageVersion);
internal sealed record ForestryNursery(long NextProductionAtMs, long ProductionPeriod, long GeneratedSeeds, long StockSeeds);
internal sealed record ForestryPlot(string PlotId, double[] Position)
{
    public double Radius => 0.45;
    public double[] BuildExclusion => [Position[0] - 1.5, Position[1] - 1.5, Position[0] + 1.5, Position[1] + 1.5];
}
internal sealed record ForestReservation(string ReservationId, string ActorId, string OperatorId, string CommandId,
    long RequestedAtMs, long QueueOrder, string Status, string? PlotId, string? PlantId, long ReservedSeed,
    long? GrantedAtMs, long? ExpiresAtMs);
internal sealed record ForestPlant(string PlantId, string PlotId, string PlanterActorId, string OperatorId,
    string ReservationId, string CommandId, long PlantedAtMs, long MaturesAtMs, string State, long StandingWood,
    long StateVersion, long EventCursor, long? MatureEventCursor, string? HarvestActorId, string? HarvestCommandId, long? HarvestEventCursor);
internal sealed record ForestryTool(string ToolId, string OwnerActorId, string WorkbenchId, string CommandId, long StateVersion, long EventCursor)
{
    public string DefinitionId => "wooden_axe";
    public int DefinitionVersion => 1;
    public int EmbodiedWood => 2;
}
internal sealed record ForestryActionDetail(string AuthorActorId, string OperatorId, string CommandId, JsonElement Action,
    double[] Position, long ServiceMs, long StateVersion, long EventCursor, string CompletedAtUtc,
    long InventoryWoodBefore, long InventoryWood, long SeedsBefore, long Seeds, long NurseryStockBefore, long NurseryStock,
    ForestReservation? ReservationBefore, ForestReservation? Reservation, ForestPlant? PlantBefore, ForestPlant? Plant, ForestryTool? Tool)
{
    public int CapabilityVersion => 1;
}

internal static partial class ForestryRules
{
    public const string Capability = "forestry-v1", SourceId = "nursery-west";
    public const long SeedInterval = 60000, Capacity = 4, PreparationLease = 90000, Growth = 120000, HarvestLease = 60000;
    // Public JSON integers must also be exact in the supported JavaScript clients.
    public const long MaxInteger = 9007199254740991;
    public const double Reach = 1.6;
    public static readonly double[] NurseryPosition = [7, 6], NurseryExclusion = [5.5, 4.5, 8.5, 7.5];
    public static readonly ForestryPlot[] Plots = [new("forest-west-north", [7, 12]), new("forest-west-south", [7, 16]),
        new("forest-east-north", [21, 7]), new("forest-east-far", [29, 5])];
    public static readonly object Policy = new { seedIntervalMs = SeedInterval, nurseryCapacity = Capacity,
        preparationLeaseMs = PreparationLease, growthMs = Growth, harvestLeaseMs = HarvestLease,
        woodPerTree = 3, seedsPerHarvest = 1, groupLimit = 1, interactReach = Reach };
    public static bool IsAction(string type) => type is "craft_forestry_tool" or "reserve_forest" or "cancel_forest_reservation"
        or "collect_seed" or "plant_tree" or "harvest_tree";
    public static bool Active(ForestReservation r) => r.Status is "queued" or "preparing" or "growing" or "harvesting";
    public static string Json<T>(T value) => JsonSerializer.Serialize(value, Protocol.Json);
    public static bool Same<T>(T a, T b) => Json(a) == Json(b);
    public static readonly (string Name, string Sql)[] Schema = BuildSchema();
    private static (string, string)[] BuildSchema()
    {
        var schema = new List<(string, string)>
        {
            ("forestry", """
                CREATE TABLE forestry(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                  adoption_json TEXT NOT NULL CHECK(json_valid(adoption_json)),
                  next_production_ms INTEGER NOT NULL CHECK(typeof(next_production_ms)='integer' AND next_production_ms>=0),
                  production_period INTEGER NOT NULL CHECK(typeof(production_period)='integer' AND production_period>=0),
                  generated_seeds INTEGER NOT NULL CHECK(typeof(generated_seeds)='integer' AND generated_seeds BETWEEN 0 AND 9007199254740991),
                  stock_seeds INTEGER NOT NULL CHECK(typeof(stock_seeds)='integer' AND stock_seeds BETWEEN 0 AND 4))
                """),
            ("forestry_seeds", """
                CREATE TABLE forestry_seeds(actor_id TEXT PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id),
                  seeds INTEGER NOT NULL CHECK(typeof(seeds)='integer' AND seeds BETWEEN 0 AND 9007199254740991),
                  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id))
                """),
            ("forestry_actions", """
                CREATE TABLE forestry_actions(actor_id TEXT NOT NULL, command_id TEXT NOT NULL, world_id TEXT NOT NULL,
                  event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq) DEFERRABLE INITIALLY DEFERRED,
                  detail_json TEXT NOT NULL CHECK(json_valid(detail_json)), PRIMARY KEY(actor_id,command_id),
                  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED)
                """)
        };
        foreach (var name in new[] { "forestry_reservations", "forestry_plants", "forestry_tools" })
            schema.Add((name, $"CREATE TABLE {name}(id TEXT PRIMARY KEY, data_json TEXT NOT NULL CHECK(json_valid(data_json)))"));
        foreach (var name in new[] { "forestry_actions", "forestry_tools" })
        {
            schema.Add(($"immutable_{name}_update", $"CREATE TRIGGER immutable_{name}_update BEFORE UPDATE ON {name} BEGIN SELECT RAISE(ABORT,'immutable forestry fact'); END;"));
            schema.Add(($"immutable_{name}_delete", $"CREATE TRIGGER immutable_{name}_delete BEFORE DELETE ON {name} BEGIN SELECT RAISE(ABORT,'immutable forestry fact'); END;"));
        }
        schema.Add(("immutable_forestry_adoption", "CREATE TRIGGER immutable_forestry_adoption BEFORE UPDATE OF singleton,adoption_json ON forestry BEGIN SELECT RAISE(ABORT,'immutable forestry adoption'); END;"));
        schema.Add(("immutable_forestry_delete", "CREATE TRIGGER immutable_forestry_delete BEFORE DELETE ON forestry BEGIN SELECT RAISE(ABORT,'immutable forestry adoption'); END;"));
        return schema.ToArray();
    }
    public static ForestryAdoption? Read(SqliteConnection c, SqliteTransaction t)
    {
        var count = Scalar(c, t, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN('forestry','forestry_seeds','forestry_actions','forestry_reservations','forestry_plants','forestry_tools')");
        if (count == 0) return null;
        if (count != 6) throw new InvalidOperationException("林业存储不完整");
        using var q = Command(c, t, "SELECT adoption_json FROM forestry WHERE singleton=1");
        return JsonSerializer.Deserialize<ForestryAdoption>(q.ExecuteScalar() as string ?? throw new InvalidOperationException("缺少林业采用"), Protocol.Json)
            ?? throw new InvalidOperationException("林业采用无效");
    }
    public static ForestryNursery Nursery(SqliteConnection c, SqliteTransaction t)
    {
        using var q = Command(c, t, "SELECT next_production_ms,production_period,generated_seeds,stock_seeds FROM forestry WHERE singleton=1");
        using var r = q.ExecuteReader(); if (!r.Read()) throw new InvalidOperationException("缺少种源");
        long Int(int i) => r.GetValue(i) is long value ? value : throw new InvalidOperationException("种源整数类型无效");
        return new(Int(0), Int(1), Int(2), Int(3));
    }
    private static List<T> Records<T>(SqliteConnection c, SqliteTransaction t, string table, string column = "data_json")
    {
        using var q = Command(c, t, $"SELECT {column} FROM {table}"); using var r = q.ExecuteReader(); var result = new List<T>();
        while (r.Read()) result.Add(JsonSerializer.Deserialize<T>(r.GetString(0), Protocol.Json) ?? throw new InvalidOperationException("林业记录无效"));
        return result;
    }
    public static List<ForestReservation> Reservations(SqliteConnection c, SqliteTransaction t) => Records<ForestReservation>(c, t, "forestry_reservations").OrderBy(r => r.QueueOrder).ToList();
    public static List<ForestPlant> Plants(SqliteConnection c, SqliteTransaction t) => Records<ForestPlant>(c, t, "forestry_plants").OrderBy(p => p.EventCursor).ToList();
    public static List<ForestryTool> Tools(SqliteConnection c, SqliteTransaction t, string? actor = null) => Records<ForestryTool>(c, t, "forestry_tools").Where(x => actor is null || x.OwnerActorId == actor).OrderBy(x => x.ToolId).ToList();
    public static List<ForestryActionDetail> Actions(SqliteConnection c, SqliteTransaction t) => Records<ForestryActionDetail>(c, t, "forestry_actions", "detail_json").OrderBy(a => a.EventCursor).ToList();
    public static long Seeds(SqliteConnection c, SqliteTransaction t, string actor) => Scalar(c, t, "SELECT coalesce((SELECT seeds FROM forestry_seeds WHERE actor_id=$actor),0)", ("$actor", actor));
    public static void Put<T>(SqliteConnection c, SqliteTransaction t, string table, string id, T value) => Run(c, t,
        $"INSERT INTO {table}(id,data_json) VALUES($id,$json) ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json", ("$id", id), ("$json", Json(value)));
    public static void Put(SqliteConnection c, SqliteTransaction t, ForestReservation r) => Put(c, t, "forestry_reservations", r.ReservationId, r);
    public static void Put(SqliteConnection c, SqliteTransaction t, ForestPlant p) => Put(c, t, "forestry_plants", p.PlantId, p);
    public static void SetSeeds(SqliteConnection c, SqliteTransaction t, string actor, long value) => Run(c, t,
        "INSERT INTO forestry_seeds VALUES($actor,$world,$seeds) ON CONFLICT(actor_id) DO UPDATE SET seeds=excluded.seeds", ("$actor", actor), ("$world", Protocol.WorldId), ("$seeds", value));
    public static (long Generated, long Standing, long Tools) Wood(SqliteConnection c, SqliteTransaction t)
    {
        if (Read(c, t) is null) return (0, 0, 0);
        var plants = Plants(c, t); return (checked(plants.LongCount(p => p.MatureEventCursor is not null) * 3), plants.Sum(p => p.StandingWood), checked(Tools(c, t).Count * 2L));
    }
    public static NaturalObstacle[] Obstacles(SqliteConnection c, SqliteTransaction t)
    {
        if (Read(c, t) is null) return ContinuousWorld.Rocks;
        return ContinuousWorld.Rocks.Concat(new[] { new NaturalObstacle(SourceId, "forestry_nursery", NurseryPosition, 0.3) })
            .Concat(Plants(c, t).Where(p => p.State != "harvested").Select(p => new NaturalObstacle(p.PlantId, "forestry_tree", Plots.Single(x => x.PlotId == p.PlotId).Position, 0.45))).ToArray();
    }
    public static bool BuildExcluded(SqliteConnection c, SqliteTransaction t, double x, double z, double hx, double hz) => Read(c, t) is not null
        && Plots.Select(p => p.BuildExclusion).Append(NurseryExclusion).Any(b => x + hx > b[0] && x - hx < b[2] && z + hz > b[1] && z - hz < b[3]);
    public static long Event(SqliteConnection c, SqliteTransaction t, string type, long ms, params (string Key, object? Value)[] fields) =>
        MaterialSourceRules.EnvironmentEvent(c, t, type, ms, fields.Prepend(("sourceId", (object?)SourceId)).ToArray());
    public static bool Advance(SqliteConnection c, SqliteTransaction t, long now)
    {
        var adoption = Read(c, t); if (adoption is null) return false;
        var before = Scalar(c, t, "SELECT state_version FROM worlds");
        // Replay due environmental facts first. New grants always begin at actual now.
        while (true)
        {
            var nursery = Nursery(c, t); var plants = Plants(c, t); var reservations = Reservations(c, t);
            var maturity = plants.Where(p => p.State == "growing").Select(p => p.MaturesAtMs).DefaultIfEmpty(long.MaxValue).Min();
            var expiry = reservations.Where(r => r.Status is "preparing" or "harvesting").Select(r => r.ExpiresAtMs!.Value).DefaultIfEmpty(long.MaxValue).Min();
            var due = Math.Min(nursery.NextProductionAtMs, Math.Min(maturity, expiry)); if (due > now) break;
            foreach (var p in plants.Where(p => p.State == "growing" && p.MaturesAtMs == due))
            {
                var seq = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
                var mature = p with { State = "mature", StandingWood = 3, MatureEventCursor = seq };
                var r = reservations.Single(r => r.ReservationId == p.ReservationId);
                var harvesting = r with { Status = "harvesting", ExpiresAtMs = checked(due + HarvestLease) };
                Put(c, t, mature); Put(c, t, harvesting);
                Run(c, t, "UPDATE worlds SET issued_wood=issued_wood+3");
                Event(c, t, "forestTreeMatured", due, ("plant", mature), ("reservation", harvesting), ("quantity", 3));
                Run(c, t, "INSERT INTO resource_ledger(world_id,event_seq,command_id,actor_id,source_account,destination_account,quantity) VALUES($world,$seq,NULL,NULL,'forest-ecological-input',$destination,3)",
                    ("$world", Protocol.WorldId), ("$seq", seq), ("$destination", "plant:" + p.PlantId));
            }
            foreach (var r in reservations.Where(r => r.Status is "preparing" or "harvesting" && r.ExpiresAtMs == due))
            {
                var expired = r with { Status = "expired", ReservedSeed = 0 }; Put(c, t, expired);
                Event(c, t, "forestReservationExpired", due, ("reservation", expired), ("releasedSeed", r.ReservedSeed));
            }
            if (nursery.NextProductionAtMs == due)
            {
                var quantity = nursery.StockSeeds < Capacity ? 1 : 0;
                var periods = quantity == 0 ? Math.Max(1, (Math.Min(now, Math.Min(maturity, expiry)) - due) / SeedInterval + 1) : 1;
                var period = checked(nursery.ProductionPeriod + periods);
                Run(c, t, "UPDATE forestry SET next_production_ms=$next,production_period=$period,generated_seeds=generated_seeds+$q,stock_seeds=stock_seeds+$q",
                    ("$next", checked(due + periods * SeedInterval)), ("$period", period), ("$q", quantity));
                if (quantity == 1) Event(c, t, "forestSeedProduced", due, ("productionPeriod", period), ("quantity", 1));
            }
        }
        Grant(c, t, now);
        return before != Scalar(c, t, "SELECT state_version FROM worlds");
    }
    private static void Grant(SqliteConnection c, SqliteTransaction t, long now)
    {
        while (true)
        {
            var all = Reservations(c, t); var head = all.FirstOrDefault(r => r.Status == "queued"); if (head is null) return;
            var plants = Plants(c, t).Where(p => p.State != "harvested").ToArray();
            var mature = Plots.Select(plot => plants.SingleOrDefault(p => p.PlotId == plot.PlotId && p.State == "mature"))
                .FirstOrDefault(p => p is not null && !all.Any(r => Active(r) && r.PlantId == p.PlantId));
            ForestReservation granted;
            if (mature is not null) granted = head with { Status = "harvesting", PlotId = mature.PlotId, PlantId = mature.PlantId,
                GrantedAtMs = now, ExpiresAtMs = checked(now + HarvestLease) };
            else
            {
                var plot = Plots.FirstOrDefault(p => !plants.Any(tree => tree.PlotId == p.PlotId) && !all.Any(r => Active(r) && r.PlotId == p.PlotId));
                if (plot is null) return;
                var seed = Seeds(c, t, head.ActorId) > 0 ? 0 : 1;
                if (Nursery(c, t).StockSeeds - all.Where(Active).Sum(r => r.ReservedSeed) < seed) return;
                granted = head with { Status = "preparing", PlotId = plot.PlotId, ReservedSeed = seed, GrantedAtMs = now, ExpiresAtMs = checked(now + PreparationLease) };
            }
            Put(c, t, granted); Event(c, t, "forestReservationGranted", now, ("reservation", granted));
        }
    }
}

internal sealed partial class WorldService
{
    private static void BindForestry(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t, Identity identity)
    {
        var adoption = ForestryRules.Read(c, t); if (adoption is null) return;
        var n = ForestryRules.Nursery(c, t); var reservations = ForestryRules.Reservations(c, t);
        var plants = ForestryRules.Plants(c, t); var reserved = reservations.Where(ForestryRules.Active).Sum(r => r.ReservedSeed);
        body["forestry"] = new { capability = ForestryRules.Capability, version = 1, adoption, policy = ForestryRules.Policy,
            nursery = new { sourceId = ForestryRules.SourceId, position = ForestryRules.NurseryPosition, radius = 0.3,
                buildExclusion = ForestryRules.NurseryExclusion, serviceMs = MaterialSourceRules.Read(c, t).ServiceMs,
                n.NextProductionAtMs, n.ProductionPeriod, n.GeneratedSeeds, n.StockSeeds, reservedSeeds = reserved, freeSeeds = n.StockSeeds - reserved },
            plots = ForestryRules.Plots, plants = plants.Where(p => p.State != "harvested"), reservations = reservations.Where(ForestryRules.Active),
            seeds = ForestryRules.Seeds(c, t, identity.ActorId), tools = ForestryRules.Tools(c, t, identity.ActorId),
            recipes = new[] { new { id = "wooden_axe.v1", definitionId = "wooden_axe", woodCost = 2, requiresWorkbench = true } } };
        var residentSeeds = Scalar(c, t, "SELECT coalesce(sum(seeds),0) FROM forestry_seeds");
        var harvested = plants.LongCount(p => p.State == "harvested");
        body["seedAudit"] = new { nurseryGeneratedSeeds = n.GeneratedSeeds, harvestGeneratedSeeds = harvested,
            nurseryStockSeeds = n.StockSeeds, residentSeeds, consumedPlantSeeds = plants.Count, reservedSeeds = reserved,
            conserved = n.GeneratedSeeds + harvested == n.StockSeeds + residentSeeds + plants.Count };
    }
    public ApiReply ForestryActionDetail(string tokenHash, string author, string command, string? expectedInstance)
    {
        using var c = database.Open(); using var t = c.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, c, t); var instance = WorldInstance.Require(c, t, expectedInstance); var state = ReadState(c, t);
        ApiReply Error(int status, string code, string message) => Protocol.Error(Scenario.RulesVersion, status, code, message, identity, state.Version, state.Cursor).WithInstance(instance);
        if (!Scenario.SupportsMaterialAccess || ForestryRules.Read(c, t) is null) return Error(422, "FORESTRY_UNAVAILABLE", "此世界尚未采用林业");
        if (author != identity.ActorId) return Error(403, "FORESTRY_ACCESS_DENIED", "只能查询本人的林业动作");
        var detail = ForestryRules.Actions(c, t).SingleOrDefault(d => d.AuthorActorId == author && d.CommandId == command);
        if (detail is null) return Error(404, "FORESTRY_ACTION_NOT_FOUND", "未找到原林业动作");
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor); body["forestryAction"] = detail;
        return Protocol.Reply(200, body).WithInstance(instance);
    }
    private (int Status, ApiError Error)? ValidateForestry(SqliteConnection c, SqliteTransaction t, WorldAction a, Actor actor, Identity identity)
    {
        if (!Scenario.SupportsMaterialAccess || ForestryRules.Read(c, t) is null) return (422, new("FORESTRY_UNAVAILABLE", "此世界尚未采用林业"));
        var reservations = ForestryRules.Reservations(c, t); var plants = ForestryRules.Plants(c, t);
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t); var obstacles = ForestryRules.Obstacles(c, t);
        bool Reach(double[] point, string? obstacleId = null, string? entityId = null) =>
            ContinuousWorld.Distance(actor.X, actor.Y, point[0], point[1]) <= ForestryRules.Reach
            && ContinuousWorld.Walkable(actor.X, actor.Y, trees, entities, obstacles)
            && !ContinuousWorld.Sweep(actor.X, actor.Y, point[0], point[1], trees,
                entities.Where(e => e.EntityId != entityId).ToArray(), obstacles.Where(o => o.Id != obstacleId).ToArray()).Blocked;
        if (a.Type == "craft_forestry_tool")
        {
            var bench = entities.SingleOrDefault(e => e.EntityId == a.EntityId && e.DefinitionId == "workbench");
            if (bench is null) return (404, new("WORKSHOP_TARGET_UNAVAILABLE", "指定公共工作台不存在"));
            if (!Reach(bench.Position, entityId: bench.EntityId)) return (422, new("UNREACHABLE", "须到工作台1.6米内且通路可达"));
            return actor.Wood < 2 ? (422, new("INSUFFICIENT_RESOURCE", "制斧需要本人2木材")) : null;
        }
        if (a.Type == "reserve_forest")
            return reservations.Any(r => r.OperatorId == identity.OperatorId && ForestryRules.Active(r))
                ? (409, new("FORESTRY_GROUP_LIMIT", "同声明控制组已有未结束的育林授权")) : null;
        var reservation = reservations.SingleOrDefault(r => r.ReservationId == a.ReservationId);
        if (reservation is null) return (404, new("FOREST_RESERVATION_NOT_FOUND", "原育林授权不存在"));
        if (reservation.ActorId != identity.ActorId) return (403, new("FORESTRY_ACCESS_DENIED", "不能使用其他居民的育林授权"));
        if (a.Type == "cancel_forest_reservation") return reservation.Status is "queued" or "preparing" ? null
            : (409, new("FOREST_RESERVATION_NOT_CANCELLABLE", "只可取消尚未种下的原授权"));
        var now = MaterialSourceRules.Read(c, t).ServiceMs;
        if (a.Type is "collect_seed" or "plant_tree")
        {
            if (reservation.Status != "preparing" || reservation.ExpiresAtMs <= now)
                return (409, new("FOREST_RESERVATION_NOT_ACTIVE", "原种前授权不在有效期内"));
            if (a.Type == "collect_seed")
            {
                if (a.SourceId != ForestryRules.SourceId) return (404, new("SEED_SOURCE_NOT_FOUND", "采种点不存在"));
                if (reservation.ReservedSeed != 1) return (409, new("SEED_NOT_RESERVED", "原授权没有待领的种子"));
                if (ForestryRules.Seeds(c, t, identity.ActorId) >= ForestryRules.MaxInteger) return (422, new("SEED_INTEGER_LIMIT", "种子整数已达可保存范围"));
                return Reach(ForestryRules.NurseryPosition, ForestryRules.SourceId) ? null : (422, new("UNREACHABLE", "须亲自到采种点旁领取"));
            }
            if (a.PlotId != reservation.PlotId) return (409, new("FOREST_TARGET_MISMATCH", "须使用原授权林位"));
            if (ForestryRules.Seeds(c, t, identity.ActorId) < 1) return (422, new("SEED_REQUIRED", "种植需要本人1份种子"));
            var plot = ForestryRules.Plots.Single(p => p.PlotId == a.PlotId);
            if (plants.Any(p => p.PlotId == plot.PlotId && p.State != "harvested")) return (409, new("FOREST_PLOT_OCCUPIED", "林位已有植株"));
            if (!Reach(plot.Position)) return (422, new("UNREACHABLE", "须走到原林位1.6米内且通路可达"));
            using var q = Command(c, t, "SELECT x,y FROM residents"); using var reader = q.ExecuteReader();
            while (reader.Read()) if (ContinuousWorld.Distance(reader.GetDouble(0), reader.GetDouble(1), plot.Position[0], plot.Position[1]) < plot.Radius + ContinuousWorld.Radius - 1e-9)
                return (409, new("AREA_OCCUPIED", "树干将覆盖居民，请先让开"));
            return null;
        }
        var plant = plants.SingleOrDefault(p => p.PlantId == a.PlantId);
        if (plant is null) return (404, new("FOREST_PLANT_NOT_FOUND", "原植株不存在"));
        if (plant.State != "mature") return (409, new("FOREST_TREE_NOT_MATURE", "原植株尚未成熟或已经采收"));
        if (reservation.Status != "harvesting" || reservation.ExpiresAtMs <= now)
            return (409, new("FOREST_RESERVATION_NOT_ACTIVE", "原采收授权不在有效期内"));
        if (reservation.PlantId != plant.PlantId) return (409, new("FOREST_TARGET_MISMATCH", "原授权不属于这株树"));
        if (!ForestryRules.Tools(c, t, identity.ActorId).Any(tool => tool.ToolId == a.ToolId)) return (403, new("TOOL_NOT_OWNED", "采收须使用本人木斧"));
        if (actor.Wood > 9) return (422, new("INVENTORY_CAPACITY_EXCEEDED", "整株采收需要腾出3木材容量"));
        if (ForestryRules.Seeds(c, t, identity.ActorId) >= ForestryRules.MaxInteger) return (422, new("SEED_INTEGER_LIMIT", "无法保存采收所得种子"));
        var target = ForestryRules.Plots.Single(p => p.PlotId == plant.PlotId);
        return Reach(target.Position, plant.PlantId) ? null : (422, new("UNREACHABLE", "须到原树1.6米内且途中无障碍"));
    }
    private (object Result, object Event, string? Source, string? Destination, long Quantity) ApplyForestry(
        SqliteConnection c, SqliteTransaction t, WorldCommand request, Identity identity, Actor actor, long state, long cursor, string? fault)
    {
        var a = request.Action; var now = MaterialSourceRules.Read(c, t).ServiceMs;
        var seedsBefore = ForestryRules.Seeds(c, t, identity.ActorId); var seeds = seedsBefore;
        var stockBefore = ForestryRules.Nursery(c, t).StockSeeds; var stock = stockBefore; var wood = actor.Wood;
        var reservationBefore = ForestryRules.Reservations(c, t).SingleOrDefault(r => r.ReservationId == a.ReservationId); var reservation = reservationBefore;
        var plantBefore = ForestryRules.Plants(c, t).SingleOrDefault(p => p.PlantId == a.PlantId); var plant = plantBefore;
        ForestryTool? tool = null; string? source = null, destination = null; long quantity = 0;
        switch (a.Type)
        {
            case "craft_forestry_tool":
                wood -= 2; quantity = 2;
                GuardedDebit(Run(c, t, "UPDATE residents SET wood=wood-2 WHERE actor_id=$actor AND wood>=2", ("$actor", identity.ActorId))); InjectAfterDebit(fault);
                tool = new("t" + Guid.NewGuid().ToString("N"), identity.ActorId, a.EntityId!, request.CommandId, state, cursor);
                Run(c, t, "INSERT INTO forestry_tools VALUES($id,$json)", ("$id", tool.ToolId), ("$json", ForestryRules.Json(tool)));
                source = "inventory:" + identity.ActorId; destination = "tool:" + tool.ToolId;
                break;
            case "reserve_forest":
                reservation = new("fr" + Guid.NewGuid().ToString("N"), identity.ActorId, identity.OperatorId, request.CommandId,
                    now, cursor, "queued", null, null, 0, null, null);
                ForestryRules.Put(c, t, reservation);
                break;
            case "cancel_forest_reservation":
                reservation = reservationBefore! with { Status = "cancelled", ReservedSeed = 0 }; ForestryRules.Put(c, t, reservation);
                break;
            case "collect_seed":
                GuardedDebit(Run(c, t, "UPDATE forestry SET stock_seeds=stock_seeds-1 WHERE stock_seeds>0")); InjectAfterDebit(fault);
                stock--; seeds++; ForestryRules.SetSeeds(c, t, identity.ActorId, seeds);
                reservation = reservationBefore! with { ReservedSeed = 0 }; ForestryRules.Put(c, t, reservation);
                break;
            case "plant_tree":
                seeds--; ForestryRules.SetSeeds(c, t, identity.ActorId, seeds); InjectAfterDebit(fault);
                plant = new("p" + Guid.NewGuid().ToString("N"), a.PlotId!, identity.ActorId, identity.OperatorId, a.ReservationId!, request.CommandId,
                    now, checked(now + ForestryRules.Growth), "growing", 0, state, cursor, null, null, null, null);
                reservation = reservationBefore! with { Status = "growing", PlantId = plant.PlantId, ReservedSeed = 0, ExpiresAtMs = null };
                ForestryRules.Put(c, t, plant); ForestryRules.Put(c, t, reservation);
                break;
            case "harvest_tree":
                plant = plantBefore! with { State = "harvested", StandingWood = 0, HarvestActorId = identity.ActorId,
                    HarvestCommandId = request.CommandId, HarvestEventCursor = cursor };
                ForestryRules.Put(c, t, plant); InjectAfterDebit(fault);
                wood += 3; quantity = 3; seeds++;
                GuardedDebit(Run(c, t, "UPDATE residents SET wood=wood+3 WHERE actor_id=$actor AND wood<=9", ("$actor", identity.ActorId)));
                ForestryRules.SetSeeds(c, t, identity.ActorId, seeds);
                reservation = reservationBefore! with { Status = "completed" }; ForestryRules.Put(c, t, reservation);
                tool = ForestryRules.Tools(c, t, identity.ActorId).Single(tool => tool.ToolId == a.ToolId);
                source = "plant:" + plant.PlantId; destination = "inventory:" + identity.ActorId;
                break;
        }
        var detail = new ForestryActionDetail(identity.ActorId, identity.OperatorId, request.CommandId, JsonSerializer.SerializeToElement(a.Canonical, Protocol.Json),
            [actor.X, actor.Y], now, state, cursor, DateTimeOffset.UtcNow.ToString("O"), actor.Wood, wood, seedsBefore, seeds, stockBefore, stock,
            reservationBefore, reservation, plantBefore, plant, tool);
        Run(c, t, "INSERT INTO forestry_actions VALUES($actor,$command,$world,$seq,$detail)", ("$actor", identity.ActorId), ("$command", request.CommandId),
            ("$world", Protocol.WorldId), ("$seq", cursor), ("$detail", ForestryRules.Json(detail)));
        return (new { action = a.Type, forestryAction = detail }, new { seq = cursor, stateVersion = state, actorId = identity.ActorId,
            commandId = request.CommandId, type = "forestryActionCompleted", forestryAction = detail }, source, destination, quantity);
    }
}

internal sealed partial class WorldDatabase
{
    public bool AdoptForestry(string expectedInstance)
    {
        if (!WorldInstance.Valid(expectedInstance)) throw new ArgumentException("必须指定原实例");
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var c = Open(); using var t = c.BeginTransaction(deferred: false);
        var storage = Scalar(c, t, "PRAGMA user_version"); Scenario = ReadScenario(c, t, storage);
        if (!Scenario.SupportsMaterialAccess || WorldInstance.Read(c, t) != expectedInstance || storage is not (13 or 14))
            throw new InvalidOperationException("林业只能在原持续材料工坊世界采用");
        var policy = ContinuousMaterialRules.ReadPolicy(c, t, expectedInstance) ?? throw new InvalidOperationException("缺少持续材料政策");
        ContinuousMaterialRules.ValidateState(c, t, policy); EntityCanvasRules.ValidateStorage(c, t, expectedInstance, storage, policy);
        WorkshopRules.ValidateStorage(c, t, expectedInstance, storage, policy); ForestryRules.ValidateStorage(c, t, expectedInstance, storage);
        if (ForestryRules.Read(c, t) is not null) return false;
        foreach (var b in ForestryRules.Plots.Select(p => p.BuildExclusion).Append(ForestryRules.NurseryExclusion))
        {
            bool Circle(double x, double z, double radius) => ContinuousWorld.Distance(x, z, Math.Clamp(x, b[0], b[2]), Math.Clamp(z, b[1], b[3])) < radius;
            if (b[2] > 27 && b[0] < 29 && b[3] > 9 && b[1] < 11
                || ContinuousWorld.Rocks.Any(r => Circle(r.Position[0], r.Position[1], r.Radius))) throw new InvalidOperationException("林业保留区被原设施占用");
            var heights = ContinuousWorld.Centerline.Select(p => p[1]).Where(z => z > b[1] && z < b[3]).Append(b[1]).Append(b[3]);
            if (heights.Any(z => b[2] > ContinuousWorld.RiverX(z) - 1.4 && b[0] < ContinuousWorld.RiverX(z) + 1.4)) throw new InvalidOperationException("林业保留区碰到河道");
            using (var q = Command(c, t, "SELECT x,y,0.28 FROM residents UNION ALL SELECT x,y,0.45 FROM resource_nodes WHERE remaining_wood>0"))
            using (var r = q.ExecuteReader()) while (r.Read()) if (Circle(r.GetDouble(0), r.GetDouble(1), r.GetDouble(2))) throw new InvalidOperationException("林业保留区碰到居民或原树");
            using (var q = Command(c, t, "SELECT entity_id,definition_id,definition_version,rules_version,owner_actor_id,x,y,embodied_wood FROM entities"))
            using (var r = q.ExecuteReader()) while (r.Read())
            {
                var e = new NaturalStructure(r.GetString(0), r.GetString(1), r.GetInt64(2), r.GetString(3), r.GetString(4), [r.GetDouble(5), r.GetDouble(6)], r.GetInt64(7));
                var h = ContinuousWorld.HalfSize(e);
                if (e.Position[0] + h.X > b[0] && e.Position[0] - h.X < b[2] && e.Position[1] + h.Z > b[1] && e.Position[1] - h.Z < b[3])
                    throw new InvalidOperationException("林业保留区碰到原建筑");
            }
        }
        foreach (var (_, sql) in ForestryRules.Schema) Run(c, t, sql);
        var ms = MaterialSourceRules.Read(c, t).ServiceMs;
        var state = checked(Scalar(c, t, "SELECT state_version FROM worlds") + 1); var cursor = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
        var adoption = new ForestryAdoption(expectedInstance, ms, state, cursor, storage);
        ForestryRules.Event(c, t, "forestryAdopted", ms, ("adoption", adoption), ("policy", ForestryRules.Policy), ("plots", ForestryRules.Plots));
        Run(c, t, "INSERT INTO forestry VALUES(1,$json,$next,0,0,0)", ("$json", ForestryRules.Json(adoption)), ("$next", checked(ms + ForestryRules.SeedInterval)));
        Run(c, t, "PRAGMA user_version=14"); ForestryRules.ValidateStorage(c, t, expectedInstance, 14);
        var fault = configuration.FaultsEnabled ? Environment.GetEnvironmentVariable("WORLD_FORESTRY_ADOPTION_TEST_FAULT") : null;
        if (fault == "before-commit") Environment.Exit(91);
        t.Commit(); if (fault == "after-commit") Environment.Exit(92); return true;
    }
}
