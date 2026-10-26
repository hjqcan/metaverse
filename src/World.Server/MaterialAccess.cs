using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record MaterialSource(bool Active, long ServiceMs, long? EnabledAtServiceMs, long? NextProductionAtMs,
    long ProductionPeriod, long GeneratedWood, long StockWood);
internal sealed record MaterialReservation(string ReservationId, string ActorId, string OperatorId,
    string RequestCommandId, long QueueSequence, string Status, long RequestedAtMs,
    long? GrantedAtMs, long? ExpiresAtMs, long Remaining);

internal static class MaterialSourceRules
{
    public const string SourceId = "wood-source-east";
    public const long InputBudget = 12, Capacity = 6, Quantity = 3, IntervalMs = 10000, LeaseMs = 60000;
    public static readonly double[] Position = [28, 10];
    public static readonly double[] BuildExclusion = [27, 9, 29, 11];

    public const string Schema = """
        CREATE TABLE material_source(
          id INTEGER PRIMARY KEY CHECK(id=1), active INTEGER NOT NULL CHECK(active IN(0,1)),
          service_ms INTEGER NOT NULL CHECK(service_ms>=0), enabled_at_ms INTEGER, next_production_ms INTEGER,
          production_period INTEGER NOT NULL CHECK(production_period>=0),
          generated_wood INTEGER NOT NULL CHECK(generated_wood BETWEEN 0 AND 12),
          stock_wood INTEGER NOT NULL CHECK(stock_wood BETWEEN 0 AND 6),
          CHECK(stock_wood<=generated_wood), CHECK((active=0 AND enabled_at_ms IS NULL AND next_production_ms IS NULL) OR
              (active=1 AND enabled_at_ms>=0 AND next_production_ms=enabled_at_ms+(production_period+1)*10000)));
        INSERT INTO material_source VALUES(1,0,0,NULL,NULL,0,0,0);
        CREATE TABLE material_reservations(
          queue_sequence INTEGER PRIMARY KEY AUTOINCREMENT, reservation_id TEXT NOT NULL UNIQUE,
          world_id TEXT NOT NULL, actor_id TEXT NOT NULL, operator_id TEXT NOT NULL, request_command_id TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN('queued','active','completed','cancelled','expired')),
          requested_at_ms INTEGER NOT NULL CHECK(requested_at_ms>=0), granted_at_ms INTEGER, expires_at_ms INTEGER,
          remaining INTEGER NOT NULL CHECK(remaining BETWEEN 0 AND 3),
          UNIQUE(world_id,actor_id,request_command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
          CHECK((granted_at_ms IS NULL AND expires_at_ms IS NULL) OR expires_at_ms=granted_at_ms+60000),
          CHECK(status!='active' OR (granted_at_ms IS NOT NULL AND remaining>0)),
          CHECK(status!='completed' OR remaining=0));
        CREATE UNIQUE INDEX one_material_request_per_operator ON material_reservations(operator_id) WHERE status IN('queued','active');
        CREATE TRIGGER immutable_reservation_identity BEFORE UPDATE OF queue_sequence,reservation_id,world_id,actor_id,operator_id,request_command_id,requested_at_ms ON material_reservations
          BEGIN SELECT RAISE(ABORT,'immutable reservation identity'); END;
        CREATE TRIGGER immutable_control_group BEFORE UPDATE OF operator_id ON residents
          BEGIN SELECT RAISE(ABORT,'immutable experiment control group'); END;
        CREATE TABLE material_production(
          production_period INTEGER PRIMARY KEY CHECK(production_period>0), service_ms INTEGER NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 3), event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq));
        CREATE TRIGGER immutable_production_update BEFORE UPDATE ON material_production BEGIN SELECT RAISE(ABORT,'immutable production'); END;
        CREATE TRIGGER immutable_production_delete BEFORE DELETE ON material_production BEGIN SELECT RAISE(ABORT,'immutable production'); END;
        """;

    public static MaterialSource Read(SqliteConnection c, SqliteTransaction? t)
    {
        using var command = Command(c, t, "SELECT active,service_ms,enabled_at_ms,next_production_ms,production_period,generated_wood,stock_wood FROM material_source WHERE id=1");
        using var r = command.ExecuteReader();
        if (!r.Read()) throw new InvalidOperationException("缺少材料来源状态");
        return new(r.GetInt64(0) == 1, r.GetInt64(1), r.IsDBNull(2) ? null : r.GetInt64(2), r.IsDBNull(3) ? null : r.GetInt64(3), r.GetInt64(4), r.GetInt64(5), r.GetInt64(6));
    }

    public static List<MaterialReservation> Reservations(SqliteConnection c, SqliteTransaction t)
    {
        var result = new List<MaterialReservation>();
        using var command = Command(c, t, """
            SELECT reservation_id,actor_id,operator_id,request_command_id,queue_sequence,status,requested_at_ms,granted_at_ms,expires_at_ms,remaining
            FROM material_reservations ORDER BY queue_sequence
            """);
        using var r = command.ExecuteReader();
        while (r.Read()) result.Add(new(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetInt64(4),
            r.GetString(5), r.GetInt64(6), r.IsDBNull(7) ? null : r.GetInt64(7), r.IsDBNull(8) ? null : r.GetInt64(8), r.GetInt64(9)));
        return result;
    }

    public static long EnvironmentEvent(SqliteConnection c, SqliteTransaction t, string type, long serviceMs,
        params (string Key, object? Value)[] fields)
    {
        var version = checked(Scalar(c, t, "SELECT state_version FROM worlds") + 1);
        var seq = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
        var body = new Dictionary<string, object?> { ["seq"] = seq, ["stateVersion"] = version,
            ["actorId"] = null, ["commandId"] = null, ["type"] = type, ["sourceId"] = SourceId, ["serviceMs"] = serviceMs };
        foreach (var (key, value) in fields) body[key] = value;
        Run(c, t, "UPDATE worlds SET state_version=$version", ("$version", version));
        Run(c, t, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES($seq,$world,$version,$json)",
            ("$seq", seq), ("$world", Protocol.WorldId), ("$version", version), ("$json", JsonSerializer.Serialize(body, Protocol.Json)));
        return seq;
    }

    public static void Grant(SqliteConnection c, SqliteTransaction t, long now)
    {
        var reservations = Reservations(c, t);
        var free = Read(c, t).StockWood - reservations.Where(r => r.Status == "active").Sum(r => r.Remaining);
        foreach (var r in reservations.Where(r => r.Status == "queued"))
        {
            if (free < Quantity) break;
            Run(c, t, "UPDATE material_reservations SET status='active',remaining=3,granted_at_ms=$now,expires_at_ms=$expires WHERE reservation_id=$id AND status='queued'",
                ("$now", now), ("$expires", checked(now + LeaseMs)), ("$id", r.ReservationId));
            EnvironmentEvent(c, t, "materialReservationGranted", now, ("reservationId", r.ReservationId),
                ("reservationActorId", r.ActorId), ("operatorId", r.OperatorId), ("remaining", Quantity), ("expiresAtMs", checked(now + LeaseMs)));
            free -= Quantity;
        }
    }

    public static bool Advance(SqliteConnection c, SqliteTransaction t, long now, bool continuous = false)
    {
        var before = Scalar(c, t, "SELECT state_version FROM worlds");
        var source = Read(c, t);
        if (now < source.ServiceMs) throw new InvalidOperationException("服务时钟不能倒退");
        // Expire and process input periods in order. Grant only at the actual
        // transaction time below: delayed callbacks must not backdate a new lease.
        while (source.Active)
        {
            var expiry = Reservations(c, t).Where(r => r.Status == "active").Select(r => r.ExpiresAtMs!.Value).DefaultIfEmpty(long.MaxValue).Min();
            var next = Math.Min(expiry, source.NextProductionAtMs!.Value);
            if (next > now) break;
            foreach (var r in Reservations(c, t).Where(r => r.Status == "active" && r.ExpiresAtMs <= next))
            {
                Run(c, t, "UPDATE material_reservations SET status='expired' WHERE reservation_id=$id", ("$id", r.ReservationId));
                EnvironmentEvent(c, t, "materialReservationExpired", next, ("reservationId", r.ReservationId),
                    ("reservationActorId", r.ActorId), ("releasedQuantity", r.Remaining));
            }
            if (source.NextProductionAtMs == next)
            {
                var quantity = Math.Min(Quantity, Capacity - source.StockWood);
                if (!continuous) quantity = Math.Min(quantity, InputBudget - source.GeneratedWood);
                var periods = quantity == 0 ? Math.Max(1, (Math.Min(now, expiry) - next) / IntervalMs + 1) : 1;
                var period = checked(source.ProductionPeriod + periods);
                Run(c, t, "UPDATE material_source SET next_production_ms=$next,production_period=$period,generated_wood=generated_wood+$q,stock_wood=stock_wood+$q WHERE id=1",
                    ("$next", checked(next + periods * IntervalMs)), ("$period", period), ("$q", quantity));
                if (quantity > 0)
                {
                    Run(c, t, "UPDATE worlds SET issued_wood=issued_wood+$q", ("$q", quantity));
                    var seq = EnvironmentEvent(c, t, "materialProduced", next, ("productionPeriod", period), ("quantity", quantity));
                    Run(c, t, "INSERT INTO material_production VALUES($period,$now,$q,$seq)", ("$period", period), ("$now", next), ("$q", quantity), ("$seq", seq));
                    Run(c, t, """
                        INSERT INTO resource_ledger(world_id,event_seq,command_id,actor_id,source_account,destination_account,quantity)
                        VALUES($world,$seq,NULL,NULL,'ecological-input',$destination,$q)
                        """, ("$world", Protocol.WorldId), ("$seq", seq), ("$destination", "source:" + SourceId), ("$q", quantity));
                }
            }
            source = Read(c, t);
        }
        if (source.Active) Grant(c, t, now);
        Run(c, t, "UPDATE material_source SET service_ms=$now WHERE id=1", ("$now", now));
        return Scalar(c, t, "SELECT state_version FROM worlds") != before;
    }
}

internal sealed partial class WorldService
{
    public void TickMaterialClock()
    {
        if (!Scenario.SupportsMaterialAccess || materialClock is null) return;
        using var c = database.Open(); using var t = c.BeginTransaction(deferred: false);
        var changed = MaterialSourceRules.Advance(c, t, materialClock.Now, database.ProductionPolicy is not null);
        var fault = configuration.FaultsEnabled ? Environment.GetEnvironmentVariable("WORLD_MATERIAL_TEST_FAULT") : null;
        if (changed && fault == "before-commit") Environment.Exit(83);
        t.Commit();
        if (changed && fault == "after-commit") Environment.Exit(84);
    }

    private void BindMaterialAccess(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t, Identity identity)
    {
        var source = MaterialSourceRules.Read(c, t); var reservations = MaterialSourceRules.Reservations(c, t);
        var roster = new List<object>();
        using (var command = Command(c, t, "SELECT actor_id,operator_id FROM residents ORDER BY actor_id"))
        using (var r = command.ExecuteReader()) while (r.Read()) roster.Add(new { actorId = r.GetString(0), operatorId = r.GetString(1) });
        body["materialAccess"] = new { version = database.ProductionPolicy is null ? 1 : 2, sourceId = MaterialSourceRules.SourceId,
            position = MaterialSourceRules.Position, buildExclusion = MaterialSourceRules.BuildExclusion,
            source.Active, source.ServiceMs, source.EnabledAtServiceMs, source.NextProductionAtMs, source.GeneratedWood, source.StockWood,
            freeWood = source.StockWood - reservations.Where(r => r.Status == "active").Sum(r => r.Remaining),
            inputBudget = database.ProductionPolicy is null ? (long?)MaterialSourceRules.InputBudget : null,
            productionPolicy = database.ProductionPolicy, capacity = MaterialSourceRules.Capacity,
            reservationQuantity = MaterialSourceRules.Quantity, leaseMs = MaterialSourceRules.LeaseMs,
            productionIntervalMs = MaterialSourceRules.IntervalMs,
            currentReservation = reservations.SingleOrDefault(r => r.OperatorId == identity.OperatorId && r.Status is "queued" or "active"),
            recentReservations = reservations.Where(r => r.ActorId == identity.ActorId).TakeLast(20).Reverse().ToArray(),
            queue = reservations.Where(r => r.Status == "queued").ToArray(),
            controlBasis = "declared-local-fixture", controlRoster = roster };
    }

    private (int Status, ApiError Error)? ValidateMaterialAccess(SqliteConnection c, SqliteTransaction t, WorldAction action, Actor actor, Identity identity)
    {
        if (!Scenario.SupportsMaterialAccess) return (422, new("ACTION_UNAVAILABLE", "当前世界没有预约采集来源"));
        var source = MaterialSourceRules.Read(c, t);
        var reservations = MaterialSourceRules.Reservations(c, t);
        if (action.Type == "reserve_material")
        {
            if (action.SourceId != MaterialSourceRules.SourceId) return (404, new("MATERIAL_SOURCE_NOT_FOUND", "采集区不存在"));
            if (!source.Active) return (422, new("MATERIAL_SOURCE_INACTIVE", "采集区尚未开启"));
            if (reservations.Any(r => r.OperatorId == identity.OperatorId && r.Status is "queued" or "active"))
                return (409, new("RESERVATION_ALREADY_ACTIVE", "同一已知控制组已有排队或待采预约"));
            var demand = 3 * reservations.LongCount(r => r.Status == "queued") + reservations.Where(r => r.Status == "active").Sum(r => r.Remaining);
            if (database.ProductionPolicy is null && demand + 3 > source.StockWood + MaterialSourceRules.InputBudget - source.GeneratedWood)
                return (422, new("SOURCE_BUDGET_EXHAUSTED", "有限来源剩余材料不足以接纳新预约"));
            return null;
        }
        var reservation = reservations.SingleOrDefault(r => r.ReservationId == action.ReservationId && r.ActorId == identity.ActorId);
        if (reservation is null) return (404, new("RESERVATION_NOT_FOUND", "未找到本人原预约"));
        if (action.Type == "cancel_reservation")
            return reservation.Status is "queued" or "active" ? null : (422, new("RESERVATION_NOT_ACTIVE", "原预约已经结束"));
        if (reservation.Status != "active" || reservation.ExpiresAtMs <= source.ServiceMs)
            return (422, new("RESERVATION_NOT_ACTIVE", "原预约尚未授予或已经结束，请核对原预约"));
        if (actor.Wood >= 12) return (422, new("INVENTORY_CAPACITY_EXCEEDED", "本人木材库存已满"));
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t);
        if (ContinuousWorld.Distance(actor.X, actor.Y, 28, 10) > ContinuousWorld.GatherReach ||
            !ContinuousWorld.Walkable(actor.X, actor.Y, trees, entities) ||
            ContinuousWorld.Sweep(actor.X, actor.Y, 28, 10, trees, entities).Blocked)
            return (422, new("UNREACHABLE", "请走到采集区1.6米内且中间没有障碍"));
        return null;
    }

    private (object Result, object Event, string? Source, string? Destination, long Quantity) ApplyMaterialAccess(
        SqliteConnection c, SqliteTransaction t, WorldCommand request, Identity identity, Actor actor, long version, long cursor, string? fault)
    {
        var action = request.Action; var now = MaterialSourceRules.Read(c, t).ServiceMs;
        object result; var fields = new Dictionary<string, object?> { ["seq"] = cursor, ["stateVersion"] = version,
            ["commandId"] = request.CommandId, ["actorId"] = identity.ActorId, ["sourceId"] = MaterialSourceRules.SourceId, ["serviceMs"] = now };
        if (action.Type == "reserve_material")
        {
            var id = "m" + Guid.NewGuid().ToString("N");
            Run(c, t, """
                INSERT INTO material_reservations(reservation_id,world_id,actor_id,operator_id,request_command_id,status,requested_at_ms,remaining)
                VALUES($id,$world,$actor,$operator,$command,'queued',$now,3)
                """, ("$id", id), ("$world", Protocol.WorldId), ("$actor", identity.ActorId), ("$operator", identity.OperatorId), ("$command", request.CommandId), ("$now", now));
            var sequence = Scalar(c, t, "SELECT queue_sequence FROM material_reservations WHERE reservation_id=$id", ("$id", id));
            result = new { action = action.Type, reservationId = id, sourceId = MaterialSourceRules.SourceId, queueSequence = sequence, status = "queued", requestedAtMs = now };
            fields["type"] = "materialReserved"; fields["reservationId"] = id; fields["queueSequence"] = sequence;
            fields["operatorId"] = identity.OperatorId;
        }
        else
        {
            var reservation = MaterialSourceRules.Reservations(c, t).Single(r => r.ReservationId == action.ReservationId);
            fields["reservationId"] = reservation.ReservationId;
            if (action.Type == "cancel_reservation")
            {
                Run(c, t, "UPDATE material_reservations SET status='cancelled' WHERE reservation_id=$id", ("$id", reservation.ReservationId));
                result = new { action = action.Type, reservationId = reservation.ReservationId, sourceId = MaterialSourceRules.SourceId,
                    status = "cancelled", releasedQuantity = reservation.Status == "active" ? reservation.Remaining : 0 };
                fields["type"] = "materialReservationCancelled";
                fields["releasedQuantity"] = reservation.Status == "active" ? reservation.Remaining : 0;
            }
            else
            {
                GuardedDebit(Run(c, t, "UPDATE material_source SET stock_wood=stock_wood-1 WHERE id=1 AND stock_wood>0"));
                InjectAfterDebit(fault);
                GuardedDebit(Run(c, t, "UPDATE residents SET wood=wood+1 WHERE world_id=$world AND actor_id=$actor AND wood<12", ("$world", Protocol.WorldId), ("$actor", identity.ActorId)));
                Run(c, t, "UPDATE material_reservations SET remaining=remaining-1,status=CASE WHEN remaining=1 THEN 'completed' ELSE 'active' END WHERE reservation_id=$id", ("$id", reservation.ReservationId));
                result = new { action = action.Type, reservationId = reservation.ReservationId, sourceId = MaterialSourceRules.SourceId,
                    quantity = 1, remainingBefore = reservation.Remaining, remaining = reservation.Remaining - 1,
                    inventoryWoodBefore = actor.Wood, inventoryWood = actor.Wood + 1, position = MaterialSourceRules.Position };
                fields["type"] = "materialHarvested"; fields["quantity"] = 1; fields["remaining"] = reservation.Remaining - 1;
                return (result, fields, "source:" + MaterialSourceRules.SourceId, "inventory:" + identity.ActorId, 1);
            }
        }
        return (result, fields, null, null, 0);
    }
}

internal sealed class MaterialClockWorker(WorldService service, ILogger<MaterialClockWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(250));
        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
                try { service.TickMaterialClock(); }
                catch (Exception failure) when (failure is SqliteException or IOException)
                { logger.LogWarning("Material clock transaction did not commit ({FailureType})", failure.GetType().Name); }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { }
    }
}
