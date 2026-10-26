using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record NaturalObstacle(string Id, string Kind, double[] Position, double Radius);
internal sealed record NaturalStructure(string EntityId, string DefinitionId, long DefinitionVersion, string RulesVersion,
    string OwnerActorId, double[] Position, long EmbodiedWood);

// Engine-independent planar geometry. Y in the database is the public Z coordinate, in metres.
internal static class ContinuousWorld
{
    public const double Radius = 0.28, Speed = 3, MaxStep = 0.6, TreeRadius = 0.45, GatherReach = 1.6, BuildReach = 3.2;
    public static readonly double[][] Centerline = MakeRiver();
    private static double[][] MakeRiver()
    {
        double[] knots = [16, 15, 16.4, 18, 17, 15.3, 15];
        return Enumerable.Range(0, 49).Select(step =>
        {
            var z = step * 0.5; var i = Math.Min(5, (int)(z / 4)); var t = (z - i * 4) / 4;
            var a = knots[Math.Max(0, i - 1)]; var b = knots[i]; var c = knots[i + 1]; var d = knots[Math.Min(6, i + 2)];
            var x = 0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t * t * t);
            return new[] { x, z };
        }).ToArray();
    }
    public static readonly double[][] River = Centerline.Select(p => new[] { p[0] - 1.4, p[1] })
        .Concat(Centerline.Reverse().Select(p => new[] { p[0] + 1.4, p[1] })).ToArray();
    public static readonly NaturalObstacle[] Rocks = [
        new("rock-west", "rock", [10.5,8.5], 1.05), new("rock-south", "rock", [5.6,19.7], 0.8),
        new("rock-east", "rock", [23,12.5], 1.2), new("rock-north", "rock", [21.8,3.2], 0.75)];
    public static readonly IReadOnlyList<WorldResourceNode> Trees = Array.AsReadOnly<WorldResourceNode>([
        new("tree-west-north","tree",[6.2,7.8],3,3), new("tree-west-south","tree",[9.2,16.3],3,3),
        new("tree-east-north","tree",[25.4,5.8],3,3), new("tree-east-south","tree",[25.7,18.2],3,3)]);
    public static double Distance(double x, double z, double a, double b) => Math.Sqrt((x - a) * (x - a) + (z - b) * (z - b));
    public static double RiverX(double z)
    {
        var i = Math.Clamp((int)(z / 0.5), 0, Centerline.Length - 2);
        return Centerline[i][0] + (Centerline[i + 1][0] - Centerline[i][0]) * (z - Centerline[i][1]) / 0.5;
    }
    public static double SegmentDistance(double x, double z, double[] a, double[] b)
    {
        var dx = b[0] - a[0]; var dz = b[1] - a[1];
        var t = Math.Clamp(((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz), 0, 1);
        return Distance(x, z, a[0] + t * dx, a[1] + t * dz);
    }
    public static bool Water(double x, double z, double radius = 0)
    {
        var inside = false;
        for (var i = 0; i < River.Length; i++)
        {
            var a = River[i]; var b = River[(i + 1) % River.Length];
            if ((a[1] > z) != (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
            if (radius > 0 && SegmentDistance(x, z, a, b) < radius - 1e-9) return true;
        }
        return inside;
    }
    public static (double X, double Z) HalfSize(NaturalStructure e) => e.DefinitionId switch
    {
        "bridge" => (2.4, 0.8), "platform" => (1, 1), "workbench" => (1, 0.5), "wooden_chest" => (0.5, 0.5),
        _ => throw new InvalidOperationException("不支持的实体几何")
    };
    public static bool Walkable(double x, double z, IReadOnlyList<WorldResourceNode> trees, IReadOnlyList<NaturalStructure> entities)
    {
        if (x < Radius || x > 32 - Radius || z < Radius || z > 24 - Radius) return false;
        if (Rocks.Any(r => Distance(x, z, r.Position[0], r.Position[1]) < r.Radius + Radius - 1e-9)) return false;
        if (trees.Any(t => t.RemainingWood > 0 && Distance(x, z, t.Position[0], t.Position[1]) < TreeRadius + Radius - 1e-9)) return false;
        foreach (var e in entities.Where(WorkshopRules.IsFurniture))
        {
            var h = HalfSize(e); var p = e.Position;
            if (Distance(x, z, Math.Clamp(x, p[0] - h.X, p[0] + h.X), Math.Clamp(z, p[1] - h.Z, p[1] + h.Z)) < Radius - 1e-9) return false;
        }
        return !Water(x, z, Radius) || entities.Any(e => e.DefinitionId == "bridge" &&
            Math.Abs(x - e.Position[0]) <= 2.4 - Radius && Math.Abs(z - e.Position[1]) <= 0.8 - Radius);
    }
    // Partition a sweep at every circle, expanded river-edge and bridge-boundary crossing.
    // Check each open interval: even a thin obstacle between two valid endpoints is detected.
    public static (double[] Position, bool Blocked) Sweep(double x, double z, double tx, double tz,
        IReadOnlyList<WorldResourceNode> trees, IReadOnlyList<NaturalStructure> entities)
    {
        var dx = tx - x; var dz = tz - z; var length = Distance(x, z, tx, tz);
        if (length < 1e-10) return ([x, z], false);
        var cuts = new List<double> { 0, 1 };
        void Cut(double t) { if (t > 0 && t < 1 && double.IsFinite(t)) cuts.Add(t); }
        void Circle(double cx, double cz, double r)
        {
            var a = dx * dx + dz * dz; var b = 2 * ((x - cx) * dx + (z - cz) * dz); var c = (x - cx) * (x - cx) + (z - cz) * (z - cz) - r * r;
            var d = b * b - 4 * a * c; if (d < 0) return; var root = Math.Sqrt(d); Cut((-b - root) / (2 * a)); Cut((-b + root) / (2 * a));
        }
        void Vertical(double v) { if (Math.Abs(dx) > 1e-14) Cut((v - x) / dx); }
        void Horizontal(double v) { if (Math.Abs(dz) > 1e-14) Cut((v - z) / dz); }
        Vertical(Radius); Vertical(32 - Radius); Horizontal(Radius); Horizontal(24 - Radius);
        foreach (var r in Rocks) Circle(r.Position[0], r.Position[1], r.Radius + Radius);
        foreach (var t in trees.Where(t => t.RemainingWood > 0)) Circle(t.Position[0], t.Position[1], TreeRadius + Radius);
        for (var i = 0; i < River.Length; i++)
        {
            var a = River[i]; var b = River[(i + 1) % River.Length]; var ex = b[0] - a[0]; var ez = b[1] - a[1];
            var normal = Math.Sqrt(ex * ex + ez * ez); var denominator = ex * dz - ez * dx; var initial = ex * (z - a[1]) - ez * (x - a[0]);
            if (Math.Abs(denominator) > 1e-14) foreach (var offset in new[] { -Radius * normal, 0, Radius * normal }) Cut((offset - initial) / denominator);
            Circle(a[0], a[1], Radius);
        }
        foreach (var e in entities.Where(e => e.DefinitionId == "bridge"))
        { Vertical(e.Position[0] - 2.4 + Radius); Vertical(e.Position[0] + 2.4 - Radius); Horizontal(e.Position[1] - 0.8 + Radius); Horizontal(e.Position[1] + 0.8 - Radius); }
        foreach (var e in entities.Where(WorkshopRules.IsFurniture))
        {
            var h = HalfSize(e); var p = e.Position;
            foreach (var cx in new[] { p[0] - h.X, p[0] + h.X })
            {
                Vertical(cx - Radius); Vertical(cx); Vertical(cx + Radius);
                foreach (var cz in new[] { p[1] - h.Z, p[1] + h.Z }) Circle(cx, cz, Radius);
            }
            foreach (var cz in new[] { p[1] - h.Z, p[1] + h.Z })
            { Horizontal(cz - Radius); Horizontal(cz); Horizontal(cz + Radius); }
        }
        cuts.Sort();
        for (var i = 0; i < cuts.Count - 1; i++)
        {
            var middle = (cuts[i] + cuts[i + 1]) / 2;
            if (!Walkable(x + dx * middle, z + dz * middle, trees, entities))
            { var t = Math.Max(0, cuts[i] - 0.00001 / length); return ([x + dx * t, z + dz * t], true); }
        }
        return ([tx, tz], false);
    }
}

internal sealed partial class WorldService
{
    private static List<NaturalStructure> ReadStructures(SqliteConnection c, SqliteTransaction t)
    {
        var list = new List<NaturalStructure>();
        using var command = Command(c, t, "SELECT entity_id,definition_id,definition_version,rules_version,owner_actor_id,x,y,embodied_wood FROM entities WHERE world_id=$world ORDER BY entity_id", ("$world", Protocol.WorldId));
        using var r = command.ExecuteReader();
        while (r.Read()) list.Add(new(r.GetString(0), r.GetString(1), r.GetInt64(2), r.GetString(3), r.GetString(4), [r.GetDouble(5), r.GetDouble(6)], r.GetInt64(7)));
        return list;
    }
    private ApiReply ObserveContinuous(string tokenHash, string? expectedInstance, bool supportsWorkshop)
    {
        using var c = database.Open(); using var t = c.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, c, t); var state = ReadState(c, t); var actor = ReadActor(c, t, identity.ActorId);
        var instance = WorldInstance.Require(c, t, expectedInstance);
        if (Scenario.SupportsMaterialAccess && WorkshopRules.Read(c, t) is not null && !supportsWorkshop)
        {
            var required = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor,
                error: new("CLIENT_CAPABILITY_REQUIRED", "此世界已采用工作台和储物箱，请升级支持workshop-v1的客户端"));
            required["requiredCapabilities"] = new[] { WorkshopRules.Capability };
            return Protocol.Reply(409, required).WithInstance(instance);
        }
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t); var residents = new List<object>();
        using (var command = Command(c, t, "SELECT actor_id,x,y FROM residents WHERE world_id=$world ORDER BY actor_id", ("$world", Protocol.WorldId)))
        using (var r = command.ExecuteReader()) while (r.Read()) residents.Add(new { actorId = r.GetString(0), position = new[] { r.GetDouble(1), r.GetDouble(2) } });
        var inventoryWood = Scalar(c, t, "SELECT sum(wood) FROM residents"); var embodiedWood = entities.Sum(e => e.EmbodiedWood); var wildWood = trees.Sum(n => n.RemainingWood);
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor);
        body["world"] = new { id = Protocol.WorldId, scenarioId = Scenario.Id, width = 32, height = 24, coordinateSystem = "continuous-xz", bounds = new[] { 0, 0, 32, 24 } };
        body["movement"] = new { version = 1, kind = "continuous", speed = ContinuousWorld.Speed, radius = ContinuousWorld.Radius, maxStepDistance = ContinuousWorld.MaxStep, gatherReach = ContinuousWorld.GatherReach, buildReach = ContinuousWorld.BuildReach };
        body["terrain"] = new { version = 1, river = new { polygon = ContinuousWorld.River, centerline = ContinuousWorld.Centerline, halfWidth = 1.4 }, obstacles = ContinuousWorld.Rocks };
        body["self"] = new { actorId = identity.ActorId, position = new[] { actor.X, actor.Y }, inventory = new { wood = actor.Wood } };
        body["residents"] = residents; body["resourceNodes"] = trees; body["entities"] = entities;
        body["recipes"] = new[] { new { id = "platform.v1", definitionId = "platform", woodCost = 3 }, new { id = "bridge.v1", definitionId = "bridge", woodCost = 6 } };
        body["gathering"] = new { version = 1, quantityPerAction = 1 }; body["depot"] = new { wood = 0, available = false };
        body["resourceAudit"] = new { issuedWood = state.IssuedWood, wildWood, depotWood = 0, inventoryWood, embodiedWood, conserved = wildWood + inventoryWood + embodiedWood == state.IssuedWood };
        if (Scenario.SupportsMaterialAccess)
        {
            var source = MaterialSourceRules.Read(c, t);
            var (toolWood, storedWood) = WorkshopRules.Wood(c, t);
            body["resourceAudit"] = new { initialWood = 12, issuedWood = state.IssuedWood, generatedWood = source.GeneratedWood,
                sourceWood = source.StockWood, wildWood, depotWood = 0, inventoryWood, embodiedWood, toolWood, storedWood,
                conserved = wildWood + source.StockWood + inventoryWood + embodiedWood + toolWood + storedWood == state.IssuedWood && state.IssuedWood == 12 + source.GeneratedWood };
            BindMaterialAccess(body, c, t, identity);
            BindEntityNotes(body, c, t, identity);
            BindEntityCanvas(body, c, t);
            BindWorkshop(body, c, t, identity, entities);
        }
        if (Scenario.SupportsTransfer) BindTransfers(body, c, t, identity.ActorId);
        BindObservation(body, instance);
        return Protocol.Reply(200, body).WithInstance(instance);
    }
    private (int Status, ApiError Error)? ValidateContinuous(SqliteConnection c, SqliteTransaction t, WorldAction action, Actor actor)
    {
        if (action.Type == "walk") return null;
        if (action.Type == "move") return (422, new("CONTINUOUS_MOVEMENT_REQUIRED", "请使用 walk 和连续目标坐标"));
        if (action.Type == "claim") return (422, new("NO_PUBLIC_DEPOT", "这里尚无公共储备，请到树旁采集"));
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t);
        if (action.Type == "gather")
        {
            if (Scenario.SupportsMaterialAccess && actor.Wood >= 12) return (422, new("INVENTORY_CAPACITY_EXCEEDED", "本人木材库存已满"));
            var node = trees.SingleOrDefault(n => n.NodeId == action.NodeId);
            if (node is null) return (404, new("RESOURCE_NOT_FOUND", "资源节点不存在"));
            if (node.RemainingWood == 0) return (422, new("RESOURCE_DEPLETED", "木材已采空"));
            if (ContinuousWorld.Distance(actor.X, actor.Y, node.Position[0], node.Position[1]) > ContinuousWorld.GatherReach)
                return (422, new("UNREACHABLE", "请走到树旁 1.6 米内"));
            return null;
        }
        if (action.Type != "build") return (422, new("ACTION_UNAVAILABLE", "连续荒野暂不支持此动作"));
        var x = action.TargetX; var z = action.TargetY; var bridge = action.RecipeId == "bridge.v1"; var hx = bridge ? 2.4 : 1; var hz = bridge ? 0.8 : 1;
        if (Scenario.SupportsMaterialAccess && x + hx > 27 && x - hx < 29 && z + hz > 9 && z - hz < 11)
            return (409, new("AREA_OCCUPIED", "采集区始终保留，不能在其中建造"));
        if (x - hx < 0 || x + hx > 32 || z - hz < 0 || z + hz > 24 || ContinuousWorld.Distance(actor.X, actor.Y, x, z) > ContinuousWorld.BuildReach)
            return (422, new("UNREACHABLE", "建造占地须在地图内，中心距居民不超过 3.2 米"));
        if (bridge && Math.Abs(x - ContinuousWorld.RiverX(z)) > 0.08) return (422, new("UNREACHABLE", "桥中心须对齐河道中心线"));
        if (!bridge)
        {
            // River is a piecewise-linear X interval at each Z. Extrema occur at ends or vertices.
            var heights = ContinuousWorld.Centerline.Select(p => p[1]).Where(v => v > z - hz && v < z + hz).Append(z - hz).Append(z + hz);
            if (heights.Any(v => x + hx > ContinuousWorld.RiverX(v) - 1.4 && x - hx < ContinuousWorld.RiverX(v) + 1.4))
                return (422, new("UNREACHABLE", "平台占地须完整处于陆地"));
        }
        bool OverlapCircle(double cx, double cz, double r) => ContinuousWorld.Distance(cx, cz, Math.Clamp(cx, x - hx, x + hx), Math.Clamp(cz, z - hz, z + hz)) < r;
        if (ContinuousWorld.Rocks.Any(r => OverlapCircle(r.Position[0], r.Position[1], r.Radius)) || trees.Any(n => n.RemainingWood > 0 && OverlapCircle(n.Position[0], n.Position[1], ContinuousWorld.TreeRadius)))
            return (409, new("AREA_OCCUPIED", "占地碰到树木或岩石"));
        if (entities.Any(e => { var h = ContinuousWorld.HalfSize(e); return Math.Abs(e.Position[0] - x) < h.X + hx && Math.Abs(e.Position[1] - z) < h.Z + hz; }))
            return (409, new("AREA_OCCUPIED", "占地与既有建筑重叠"));
        var cost = bridge ? 6 : 3;
        return actor.Wood < cost ? (422, new("INSUFFICIENT_RESOURCE", $"需要 {cost} 木材")) : null;
    }
    private (double[] Position, bool Blocked) WalkContinuous(SqliteConnection c, SqliteTransaction t, Actor actor, string actorId, double tx, double tz)
    {
        long last; double credit;
        using (var command = Command(c, t, "SELECT last_walk_ms,walk_credit FROM residents WHERE world_id=$world AND actor_id=$actor", ("$world", Protocol.WorldId), ("$actor", actorId)))
        using (var r = command.ExecuteReader()) { r.Read(); last = r.GetInt64(0); credit = r.GetDouble(1); }
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        credit = Math.Min(ContinuousWorld.MaxStep, credit + Math.Max(0, now - last) / 1000.0 * ContinuousWorld.Speed);
        var distance = ContinuousWorld.Distance(actor.X, actor.Y, tx, tz); var step = Math.Min(distance, credit);
        var ratio = distance > 1e-10 ? step / distance : 0;
        var walked = ContinuousWorld.Sweep(actor.X, actor.Y, actor.X + (tx - actor.X) * ratio, actor.Y + (tz - actor.Y) * ratio, ReadResourceNodes(c, t), ReadStructures(c, t));
        credit = Math.Max(0, credit - ContinuousWorld.Distance(actor.X, actor.Y, walked.Position[0], walked.Position[1]));
        Run(c, t, "UPDATE residents SET x=$x,y=$y,last_walk_ms=$now,walk_credit=$credit WHERE world_id=$world AND actor_id=$actor",
            ("$x", walked.Position[0]), ("$y", walked.Position[1]), ("$now", now), ("$credit", credit), ("$world", Protocol.WorldId), ("$actor", actorId));
        return walked;
    }
}
