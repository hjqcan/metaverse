using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal static partial class ForestryRules
{
    private static void Require(bool condition, string reason)
    { if (!condition) throw new InvalidOperationException("林业历史不一致：" + reason); }
    public static void ValidateStorage(SqliteConnection c, SqliteTransaction t, string? instance, long storage)
    {
        var adoption = Read(c, t);
        Require((storage == 14) == (adoption is not null), "能力与存储版本");
        if (adoption is null)
        {
            Require(Scalar(c, t, "SELECT count(*) FROM events WHERE json_extract(event_json,'$.type')='forestryAdopted'") == 0, "原采用不可消失");
            return;
        }
        Require(adoption.WorldInstanceId == instance && adoption.BaseStorageVersion == 13 && adoption.AdoptedServiceMs >= 0, "原采用身份");
        static string Normalize(string s) => string.Concat(s.Where(ch => !char.IsWhiteSpace(ch) && ch != '"')).TrimEnd(';');
        foreach (var (name, expected) in Schema)
        {
            using var q = Command(c, t, "SELECT sql FROM sqlite_master WHERE name=$name", ("$name", name));
            Require(q.ExecuteScalar() is string sql && Normalize(sql) == Normalize(expected), "存储结构" + name);
        }
        var n = Nursery(c, t); var now = MaterialSourceRules.Read(c, t).ServiceMs;
        Require(now >= adoption.AdoptedServiceMs && n.ProductionPeriod >= 0 && n.GeneratedSeeds >= 0 && n.GeneratedSeeds <= MaxInteger
            && n.StockSeeds is >= 0 and <= 4 && n.NextProductionAtMs > now
            && n.NextProductionAtMs == checked(adoption.AdoptedServiceMs + (n.ProductionPeriod + 1) * SeedInterval), "种源时钟与整数");
        var rs = new Dictionary<string, ForestReservation>(); var ps = new Dictionary<string, ForestPlant>();
        var ts = new Dictionary<string, ForestryTool>(); var seeds = new Dictionary<string, long>();
        var expectedActions = Actions(c, t).ToDictionary(a => a.EventCursor); var seenActions = new HashSet<long>();
        long stock = 0, generated = 0, producedPeriod = 0, lastMs = adoption.AdoptedServiceMs, lastState = adoption.StateVersion - 1;
        var actors = new Dictionary<string, string>();
        using (var q = Command(c, t, "SELECT actor_id,operator_id FROM residents"))
        using (var r = q.ExecuteReader()) while (r.Read()) actors.Add(r.GetString(0), r.GetString(1));
        var events = new List<(long Seq, long State, JsonElement Body)>();
        using (var q = Command(c, t, "SELECT seq,state_version,event_json FROM events WHERE json_extract(event_json,'$.type') LIKE 'forest%' ORDER BY seq"))
        using (var r = q.ExecuteReader()) while (r.Read())
        { using var doc = JsonDocument.Parse(r.GetString(2)); events.Add((r.GetInt64(0), r.GetInt64(1), doc.RootElement.Clone())); }
        Require(events.Count > 0 && events[0].Seq == adoption.EventCursor, "原采用事件");
        void Ledger(long seq, string? actor, string? command, string source, string destination, long qty)
        {
            Require(Scalar(c, t, """
                SELECT count(*) FROM resource_ledger WHERE event_seq=$seq AND world_id=$world AND actor_id IS $actor
                  AND command_id IS $command AND source_account=$source AND destination_account=$destination AND quantity=$qty
                """, ("$seq", seq), ("$world", Protocol.WorldId), ("$actor", actor), ("$command", command),
                ("$source", source), ("$destination", destination), ("$qty", qty)) == 1, "原木材账");
        }
        foreach (var (seq, state, e) in events)
        {
            var type = e.GetProperty("type").GetString();
            Require(e.GetProperty("seq").GetInt64() == seq && e.GetProperty("stateVersion").GetInt64() == state && state > lastState, "事件版本");
            lastState = state;
            if (type == "forestryAdopted")
            {
                Require(seq == adoption.EventCursor && state == adoption.StateVersion && e.GetProperty("serviceMs").GetInt64() == adoption.AdoptedServiceMs
                    && Same(e.GetProperty("adoption"), JsonSerializer.SerializeToElement(adoption, Protocol.Json))
                    && Same(e.GetProperty("policy"), JsonSerializer.SerializeToElement(Policy, Protocol.Json))
                    && Same(e.GetProperty("plots"), JsonSerializer.SerializeToElement(Plots, Protocol.Json)), "采用参数");
            }
            else if (type == "forestryActionCompleted")
            {
                Require(expectedActions.TryGetValue(seq, out var d) && seenActions.Add(seq), "原动作明细");
                ValidateAction(c, t, d!, e, seq, state, actors, rs, ps, ts, seeds, ref stock, lastMs, now, Ledger);
                lastMs = d!.ServiceMs;
                continue;
            }
            else
            {
                var ms = e.GetProperty("serviceMs").GetInt64(); Require(ms >= lastMs && ms <= now, "环境时间"); lastMs = ms;
                if (type == "forestSeedProduced")
                {
                    var period = e.GetProperty("productionPeriod").GetInt64();
                    Require(e.GetProperty("quantity").GetInt64() == 1 && stock < 4 && period > producedPeriod && period <= n.ProductionPeriod
                        && ms == checked(adoption.AdoptedServiceMs + period * SeedInterval), "产种事实");
                    stock++; generated++; producedPeriod = period;
                }
                else if (type == "forestReservationGranted")
                {
                    var r = e.GetProperty("reservation").Deserialize<ForestReservation>(Protocol.Json)!;
                    var head = rs.Values.Where(x => x.Status == "queued").OrderBy(x => x.QueueOrder).FirstOrDefault();
                    Require(head is not null && head.ReservationId == r.ReservationId && r.GrantedAtMs == ms, "FIFO与实际授权时刻");
                    var mature = Plots.Select(plot => ps.Values.SingleOrDefault(p => p.PlotId == plot.PlotId && p.State == "mature"))
                        .FirstOrDefault(p => p is not null && !rs.Values.Any(v => Active(v) && v.PlantId == p.PlantId));
                    ForestReservation expected;
                    if (mature is not null) expected = head! with { Status = "harvesting", PlotId = mature.PlotId, PlantId = mature.PlantId, GrantedAtMs = ms, ExpiresAtMs = checked(ms + HarvestLease) };
                    else
                    {
                        var plot = Plots.FirstOrDefault(p => !ps.Values.Any(tree => tree.PlotId == p.PlotId && tree.State != "harvested") && !rs.Values.Any(v => Active(v) && v.PlotId == p.PlotId));
                        Require(plot is not null, "空林位"); var reserve = seeds.GetValueOrDefault(head!.ActorId) > 0 ? 0 : 1;
                        Require(stock - rs.Values.Where(Active).Sum(v => v.ReservedSeed) >= reserve, "授权种子有实存");
                        expected = head with { Status = "preparing", PlotId = plot!.PlotId, ReservedSeed = reserve, GrantedAtMs = ms, ExpiresAtMs = checked(ms + PreparationLease) };
                    }
                    Require(Same(expected, r), "授权快照"); rs[r.ReservationId] = r;
                }
                else if (type == "forestReservationExpired")
                {
                    var r = e.GetProperty("reservation").Deserialize<ForestReservation>(Protocol.Json)!;
                    Require(rs.TryGetValue(r.ReservationId, out var old) && old.Status is "preparing" or "harvesting" && old.ExpiresAtMs == ms, "原到期授权");
                    Require(Same(old! with { Status = "expired", ReservedSeed = 0 }, r) && e.GetProperty("releasedSeed").GetInt64() == old!.ReservedSeed, "到期释放");
                    rs[r.ReservationId] = r;
                }
                else if (type == "forestTreeMatured")
                {
                    var p = e.GetProperty("plant").Deserialize<ForestPlant>(Protocol.Json)!; var r = e.GetProperty("reservation").Deserialize<ForestReservation>(Protocol.Json)!;
                    Require(ps.TryGetValue(p.PlantId, out var old) && old.State == "growing" && old.MaturesAtMs == ms
                        && Same(old with { State = "mature", StandingWood = 3, MatureEventCursor = seq }, p) && e.GetProperty("quantity").GetInt64() == 3, "唯一原株成熟");
                    Require(rs.TryGetValue(p.ReservationId, out var prior) && prior.Status == "growing"
                        && Same(prior with { Status = "harvesting", ExpiresAtMs = checked(ms + HarvestLease) }, r), "原种植优先权");
                    ps[p.PlantId] = p; rs[r.ReservationId] = r; Ledger(seq, null, null, "forest-ecological-input", "plant:" + p.PlantId, 3);
                }
                else throw new InvalidOperationException("未知林业环境事件");
            }
            Require(e.GetProperty("actorId").ValueKind == JsonValueKind.Null && e.GetProperty("commandId").ValueKind == JsonValueKind.Null
                && e.GetProperty("sourceId").GetString() == SourceId, "环境事件身份");
        }
        Require(seenActions.Count == expectedActions.Count && stock == n.StockSeeds && generated == n.GeneratedSeeds, "动作完整与种库存");
        Require(Same(Reservations(c, t), rs.Values.OrderBy(r => r.QueueOrder).ToList())
            && Same(Plants(c, t), ps.Values.OrderBy(p => p.EventCursor).ToList()) && Same(Tools(c, t), ts.Values.OrderBy(x => x.ToolId).ToList()), "当前对象与历史重建");
        foreach (var table in new[] { "forestry_reservations", "forestry_plants", "forestry_tools" })
        {
            var key = table == "forestry_reservations" ? "reservationId" : table == "forestry_plants" ? "plantId" : "toolId";
            Require(Scalar(c, t, $"SELECT count(*) FROM {table} WHERE id IS NOT json_extract(data_json,'$.{key}')") == 0, "对象主键");
        }
        foreach (var actor in actors.Keys) Require(Seeds(c, t, actor) == seeds.GetValueOrDefault(actor), "本人种子与原动作");
        Require(rs.Values.Where(Active).GroupBy(r => r.OperatorId).All(g => g.Count() == 1)
            && rs.Values.Where(Active).Sum(r => r.ReservedSeed) <= stock
            && ps.Values.Where(p => p.State != "harvested").GroupBy(p => p.PlotId).All(g => g.Count() == 1)
            && generated + ps.Values.LongCount(p => p.State == "harvested") == stock + seeds.Values.Sum() + ps.Count
            && Scalar(c, t, "SELECT count(*) FROM pragma_foreign_key_check") == 0, "当前双账与引用");
        Require(ps.Values.All(p => p.State != "growing" || p.MaturesAtMs > now)
            && rs.Values.All(r => r.Status is not ("preparing" or "harvesting") || r.ExpiresAtMs > now), "到期状态须已处理");
        Require(Scalar(c, t, "SELECT count(*) FROM resource_ledger WHERE source_account='forest-ecological-input'") == ps.Values.LongCount(p => p.MatureEventCursor is not null), "成熟账数量");
    }

    private static void ValidateAction(SqliteConnection c, SqliteTransaction t, ForestryActionDetail d, JsonElement e, long seq, long state,
        Dictionary<string, string> actors, Dictionary<string, ForestReservation> rs, Dictionary<string, ForestPlant> ps,
        Dictionary<string, ForestryTool> ts, Dictionary<string, long> seeds, ref long stock, long lastMs, long now,
        Action<long, string?, string?, string, string, long> ledger)
    {
        var a = d.Action; var type = a.GetProperty("type").GetString()!;
        Require(IsAction(type) && a.GetProperty("capabilityVersion").GetInt64() == 1 && d.CapabilityVersion == 1
            && d.EventCursor == seq && d.StateVersion == state && d.ServiceMs >= lastMs && d.ServiceMs <= now
            && actors.GetValueOrDefault(d.AuthorActorId) == d.OperatorId && Protocol.ValidCommandId(d.CommandId)
            && d.InventoryWoodBefore is >= 0 and <= 12 && d.InventoryWood is >= 0 and <= 12
            && d.SeedsBefore == seeds.GetValueOrDefault(d.AuthorActorId) && d.Seeds is >= 0 and <= MaxInteger
            && d.NurseryStockBefore == stock && d.Position.Length == 2 && d.Position.All(double.IsFinite)
            && DateTimeOffset.TryParse(d.CompletedAtUtc, out _) && e.GetProperty("actorId").GetString() == d.AuthorActorId
            && e.GetProperty("commandId").GetString() == d.CommandId && e.GetProperty("forestryAction").GetRawText() == Json(d), "原动作字段");
        var rb = d.ReservationBefore; var r = d.Reservation; var pb = d.PlantBefore; var p = d.Plant; var tool = d.Tool;
        if (rb is not null) Require(rs.TryGetValue(rb.ReservationId, out var old) && Same(old, rb) && rb.ActorId == d.AuthorActorId
            && a.GetProperty("reservationId").GetString() == rb.ReservationId, "动作前原授权");
        if (pb is not null) Require(ps.TryGetValue(pb.PlantId, out var old) && Same(old, pb) && a.GetProperty("plantId").GetString() == pb.PlantId, "动作前原树");
        long woodDelta = 0, seedDelta = 0, stockDelta = 0;
        var expectedFields = type switch { "reserve_forest" => 2, "cancel_forest_reservation" => 3, "harvest_tree" => 5, _ => 4 };
        Require(a.EnumerateObject().Count() == expectedFields, "动作字段集合");
        if (type == "craft_forestry_tool")
        {
            woodDelta = -2;
            Require(rb is null && r is null && pb is null && p is null && tool is not null && tool.OwnerActorId == d.AuthorActorId
                && tool.WorkbenchId == a.GetProperty("entityId").GetString() && tool.CommandId == d.CommandId && tool.StateVersion == state
                && tool.EventCursor == seq && a.GetProperty("recipeId").GetString() == "wooden_axe.v1" && ts.TryAdd(tool.ToolId, tool), "制斧事实");
            Require(Scalar(c, t, "SELECT count(*) FROM entities WHERE entity_id=$id AND definition_id='workbench'", ("$id", tool!.WorkbenchId)) == 1, "原工作台");
            ledger(seq, d.AuthorActorId, d.CommandId, "inventory:" + d.AuthorActorId, "tool:" + tool.ToolId, 2);
        }
        else if (type == "reserve_forest")
        {
            Require(rb is null && r is not null && pb is null && p is null && tool is null
                && !rs.Values.Any(x => Active(x) && x.OperatorId == d.OperatorId)
                && Same(r, new ForestReservation(r!.ReservationId, d.AuthorActorId, d.OperatorId, d.CommandId, d.ServiceMs, seq, "queued", null, null, 0, null, null))
                && !rs.ContainsKey(r.ReservationId), "原入队事实");
        }
        else
        {
            Require(rb is not null && r is not null, "原授权必须存在");
            if (type == "cancel_forest_reservation")
                Require(rb!.Status is "queued" or "preparing" && Same(rb with { Status = "cancelled", ReservedSeed = 0 }, r)
                    && pb is null && p is null && tool is null, "种前取消");
            else if (type == "collect_seed")
            {
                seedDelta = 1; stockDelta = -1;
                Require(rb!.Status == "preparing" && rb.ExpiresAtMs > d.ServiceMs && rb.ReservedSeed == 1
                    && a.GetProperty("sourceId").GetString() == SourceId && Same(rb with { ReservedSeed = 0 }, r)
                    && pb is null && p is null && tool is null, "领取原保留种子");
            }
            else if (type == "plant_tree")
            {
                seedDelta = -1;
                Require(rb!.Status == "preparing" && rb.ExpiresAtMs > d.ServiceMs && rb.PlotId == a.GetProperty("plotId").GetString()
                    && Plots.Any(x => x.PlotId == rb.PlotId) && !ps.Values.Any(x => x.PlotId == rb.PlotId && x.State != "harvested")
                    && pb is null && p is not null && tool is null && !ps.ContainsKey(p.PlantId)
                    && Same(p, new ForestPlant(p!.PlantId, rb.PlotId!, d.AuthorActorId, d.OperatorId, rb.ReservationId, d.CommandId,
                        d.ServiceMs, checked(d.ServiceMs + Growth), "growing", 0, state, seq, null, null, null, null))
                    && Same(rb with { Status = "growing", PlantId = p.PlantId, ReservedSeed = 0, ExpiresAtMs = null }, r), "原代种植");
            }
            else
            {
                woodDelta = 3; seedDelta = 1;
                Require(rb!.Status == "harvesting" && rb.ExpiresAtMs > d.ServiceMs && pb is not null && pb.State == "mature" && pb.StandingWood == 3
                    && rb.PlantId == pb.PlantId && Same(rb with { Status = "completed" }, r)
                    && Same(pb with { State = "harvested", StandingWood = 0, HarvestActorId = d.AuthorActorId, HarvestCommandId = d.CommandId, HarvestEventCursor = seq }, p)
                    && tool is not null && ts.TryGetValue(tool.ToolId, out var original) && Same(original, tool)
                    && tool.OwnerActorId == d.AuthorActorId && a.GetProperty("toolId").GetString() == tool.ToolId, "整株原代采收");
                ledger(seq, d.AuthorActorId, d.CommandId, "plant:" + pb!.PlantId, "inventory:" + d.AuthorActorId, 3);
            }
        }
        Require(d.InventoryWood == d.InventoryWoodBefore + woodDelta && d.Seeds == d.SeedsBefore + seedDelta
            && d.NurseryStock == stock + stockDelta && d.NurseryStock is >= 0 and <= 4, "动作双账变化");
        if (woodDelta == 0) Require(Scalar(c, t, "SELECT count(*) FROM resource_ledger WHERE event_seq=$seq", ("$seq", seq)) == 0, "无木材移动不得记账");
        stock = d.NurseryStock; seeds[d.AuthorActorId] = d.Seeds;
        if (r is not null) rs[r.ReservationId] = r; if (p is not null) ps[p.PlantId] = p;
        using var q = Command(c, t, """
            SELECT a.actor_id,a.command_id,a.world_id,r.status_code,r.result_json FROM forestry_actions a
            JOIN receipts r ON r.world_id=a.world_id AND r.actor_id=a.actor_id AND r.command_id=a.command_id WHERE a.event_seq=$seq
            """, ("$seq", seq));
        using var reader = q.ExecuteReader();
        Require(reader.Read() && reader.GetString(0) == d.AuthorActorId && reader.GetString(1) == d.CommandId && reader.GetString(2) == Protocol.WorldId
            && reader.GetInt64(3) == 200, "原动作主键与回执");
        using var receipt = JsonDocument.Parse(reader.GetString(4)); var re = receipt.RootElement;
        Require(re.GetProperty("status").GetString() == "committed" && re.GetProperty("commandId").GetString() == d.CommandId
            && re.GetProperty("identity").GetProperty("actorId").GetString() == d.AuthorActorId
            && re.GetProperty("stateVersion").GetInt64() == state && re.GetProperty("eventCursor").GetInt64() == seq
            && re.GetProperty("result").GetProperty("action").GetString() == type && re.GetProperty("result").GetProperty("forestryAction").GetRawText() == Json(d), "原三方完成事实");
    }
}
