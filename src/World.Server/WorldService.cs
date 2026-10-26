using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed class InjectedFailure : Exception;
internal sealed record MosaicInboxQuery(string Scope, string Status, long? Before, int Limit);

internal sealed partial class WorldService(WorldDatabase database, ServerConfiguration configuration, MaterialServiceClock? materialClock = null)
{
    private WorldScenario Scenario => database.Scenario;

    public ApiReply Observe(string tokenHash, string? expectedInstance = null)
    {
        if (Scenario.SupportsContinuous) return ObserveContinuous(tokenHash, expectedInstance);
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance);
        var state = ReadState(connection, transaction);
        var self = ReadActor(connection, transaction, identity.ActorId);
        var residents = new List<object>();
        using (var command = Command(connection, transaction, "SELECT actor_id,x,y FROM residents WHERE world_id=$world ORDER BY actor_id", ("$world", Protocol.WorldId)))
        using (var reader = command.ExecuteReader())
            while (reader.Read()) residents.Add(new { actorId = reader.GetString(0), position = new[] { reader.GetInt64(1), reader.GetInt64(2) } });
        var entities = new List<object>();
        var bridges = new HashSet<(long X, long Y)>();
        var bridgeDetails = new List<EntryBridge>();
        using (var command = Command(connection, transaction, """
            SELECT entity_id,definition_id,definition_version,rules_version,owner_actor_id,x,y,embodied_wood
            FROM entities WHERE world_id=$world ORDER BY entity_id
            """, ("$world", Protocol.WorldId)))
        using (var reader = command.ExecuteReader())
            while (reader.Read())
            {
                entities.Add(new
                {
                    entityId = reader.GetString(0), definitionId = reader.GetString(1), definitionVersion = reader.GetInt64(2),
                    rulesVersion = reader.GetString(3), ownerActorId = reader.GetString(4),
                    position = new[] { reader.GetInt64(5), reader.GetInt64(6) }, embodiedWood = reader.GetInt64(7)
                });
                if (reader.GetString(1) == "bridge")
                {
                    bridges.Add((reader.GetInt64(5), reader.GetInt64(6)));
                    bridgeDetails.Add(new(reader.GetString(0), reader.GetString(4), [reader.GetInt64(5), reader.GetInt64(6)]));
                }
            }
        var resources = Scenario.SupportsGathering ? ReadResourceNodes(connection, transaction) : [];
        var liveTrees = resources.Where(n => n.RemainingWood > 0).Select(n => (n.Position[0], n.Position[1])).ToHashSet();
        var blocked = new List<int[]>();
        var water = new List<int[]>();
        for (var x = 0; x < 8; x++)
            for (var y = 0; y < 8; y++)
            {
                if (Scenario.IsWater(x, y)) water.Add([x, y]);
                if (WorldScenario.IsWall(x, y) || liveTrees.Contains((x, y)) || Scenario.IsWater(x, y) && !bridges.Contains((x, y)))
                    blocked.Add([x, y]);
            }
        var recipes = new List<object>();
        using (var command = Command(connection, transaction, "SELECT id,definition_id,wood_cost FROM recipes ORDER BY CASE WHEN id='platform.v1' THEN 0 ELSE 1 END,id"))
        using (var reader = command.ExecuteReader())
            while (reader.Read()) recipes.Add(new { id = reader.GetString(0), definitionId = reader.GetString(1), woodCost = reader.GetInt64(2) });
        var inventoryWood = Scalar(connection, transaction, "SELECT coalesce(sum(wood),0) FROM residents WHERE world_id=$world", ("$world", Protocol.WorldId));
        var embodiedWood = Scalar(connection, transaction, "SELECT coalesce(sum(embodied_wood),0) FROM entities WHERE world_id=$world", ("$world", Protocol.WorldId));
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor);
        body["world"] = new { id = Protocol.WorldId, scenarioId = Scenario.Id, width = 8, height = 8, blocked, water, goal = new[] { Scenario.GoalX, 1 } };
        body["recipes"] = recipes;
        body["activities"] = Scenario.ActivityCatalog.Select(activity => activity.Observation).ToArray();
        body["postcards"] = Scenario.SupportsPostcards ? ReadPostcards(connection, transaction) : [];
        body["mosaic"] = Scenario.SupportsMosaic ? ReadMosaic(connection, transaction) : null;
        body["mosaicEdits"] = Scenario.SupportsMosaic ? ReadMosaicEdits(connection, transaction) : [];
        body["mosaicProposals"] = Scenario.SupportsMosaicConsent ? ReadMosaicProposals(connection, transaction) : [];
        if (Scenario.SupportsMosaicConsent) body["mosaicProposalInbox"] = new { version = 1, maxPageSize = 20 };
        body["self"] = new { actorId = identity.ActorId, position = new[] { self.X, self.Y }, inventory = new { wood = self.Wood },
            visits = Scenario.SupportsActivities ? ReadVisits(connection, transaction, identity.ActorId) : [],
            postcards = Scenario.SupportsPostcards ? ReadPostcards(connection, transaction, identity.ActorId) : [],
            mosaicEdits = Scenario.SupportsMosaic ? ReadMosaicEdits(connection, transaction, identity.ActorId) : [],
            mosaicProposals = Scenario.SupportsMosaicConsent ? ReadMosaicProposals(connection, transaction, identity.ActorId) : [],
            mosaicReviews = Scenario.SupportsMosaicConsent ? ReadMosaicReviews(connection, transaction, identity.ActorId) : [] };
        body["residents"] = residents;
        body["depot"] = Scenario.SupportsGathering
            ? (object)new { position = new[] { 1, 1 }, wood = state.DepotWood, available = false }
            : new { position = new[] { 1, 1 }, wood = state.DepotWood };
        if (Scenario.SupportsGathering)
        {
            body["gathering"] = new { version = 1, quantityPerAction = 1 };
            body["resourceNodes"] = resources;
        }
        body["entities"] = entities;
        body["entryGuide"] = EntryGuide.Build(Scenario, state.Version, identity.ActorId, (long)self.X, (long)self.Y,
            state.DepotWood, self.Wood, bridgeDetails, resources);
        var wildWood = resources.Sum(n => n.RemainingWood);
        body["resourceAudit"] = Scenario.SupportsGathering
            ? (object)new { issuedWood = state.IssuedWood, wildWood, depotWood = state.DepotWood, inventoryWood,
                embodiedWood, conserved = checked(wildWood + state.DepotWood + inventoryWood + embodiedWood) == state.IssuedWood }
            : new { issuedWood = state.IssuedWood, depotWood = state.DepotWood, inventoryWood,
                embodiedWood, conserved = checked(state.DepotWood + inventoryWood + embodiedWood) == state.IssuedWood };
        BindObservation(body, instance);
        return Protocol.Reply(200, body).WithInstance(instance);
    }

    public ApiReply MosaicProposalInbox(string tokenHash, MosaicInboxQuery query, string? expectedInstance = null)
    {
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance);
        var state = ReadState(connection, transaction);
        if (!Scenario.SupportsMosaicConsent)
            return Protocol.Error(Scenario.RulesVersion, 422, "MOSAIC_CONSENT_UNAVAILABLE", "当前世界不支持画布协商",
                identity, state.Version, state.Cursor).WithInstance(instance);

        const string scopeFilter = """
            p.world_id=$world AND ($scope='all' OR ($scope='received' AND p.target_actor_id=$actor)
                OR ($scope='sent' AND p.author_actor_id=$actor))
            """;
        const string hasReview = """
            EXISTS(SELECT 1 FROM mosaic_reviews r WHERE r.world_id=p.world_id
                AND r.proposal_actor_id=p.author_actor_id AND r.proposal_command_id=p.command_id)
            """;
        long all, reviewed;
        // Count the entire authenticated scope, independently of page/status filters.
        using (var command = Command(connection, transaction, $"""
            SELECT count(*),coalesce(sum(CASE WHEN {hasReview} THEN 1 ELSE 0 END),0)
            FROM mosaic_proposals p WHERE {scopeFilter}
            """, ("$world", Protocol.WorldId), ("$scope", query.Scope), ("$actor", identity.ActorId)))
        using (var reader = command.ExecuteReader())
        {
            reader.Read();
            all = reader.GetInt64(0);
            reviewed = reader.GetInt64(1);
        }
        var proposals = new List<MosaicProposal>();
        using (var command = Command(connection, transaction, $"""
            SELECT {ProposalColumns} FROM mosaic_proposals p WHERE {scopeFilter}
                AND ($before IS NULL OR p.state_version<$before)
                AND ($status='all' OR ($status='reviewed' AND {hasReview}) OR ($status='pending' AND NOT {hasReview}))
            ORDER BY p.state_version DESC LIMIT $limit
            """, ("$world", Protocol.WorldId), ("$scope", query.Scope), ("$actor", identity.ActorId),
            ("$before", query.Before), ("$status", query.Status), ("$limit", query.Limit + 1)))
        using (var reader = command.ExecuteReader())
            while (reader.Read()) proposals.Add(ReadMosaicProposal(reader));
        var hasOlder = proposals.Count > query.Limit;
        if (hasOlder) proposals.RemoveAt(proposals.Count - 1);
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor);
        body["query"] = query;
        body["counts"] = new { pending = all - reviewed, reviewed, all };
        body["items"] = proposals.Select(proposal => WithFields(proposal, ("review",
            ReadMosaicReviews(connection, transaction, proposalActor: proposal.AuthorActorId, proposalCommand: proposal.CommandId).SingleOrDefault()))).ToArray();
        body["nextBefore"] = hasOlder ? proposals[^1].StateVersion : (long?)null;
        return Protocol.Reply(200, body).WithInstance(instance);
    }

    public ApiReply MosaicProposalDetail(string tokenHash, string proposalActorId, string proposalCommandId, string? expectedInstance = null)
    {
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance);
        var state = ReadState(connection, transaction);
        if (!Scenario.SupportsMosaicConsent)
            return Protocol.Error(Scenario.RulesVersion, 422, "MOSAIC_CONSENT_UNAVAILABLE", "当前世界不支持画布协商",
                identity, state.Version, state.Cursor).WithInstance(instance);
        var proposal = FindMosaicProposal(connection, transaction, proposalActorId, proposalCommandId);
        if (proposal is null)
            return Protocol.Error(Scenario.RulesVersion, 404, "MOSAIC_PROPOSAL_NOT_FOUND", "提议不存在",
                identity, state.Version, state.Cursor).WithInstance(instance);
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor);
        body["proposal"] = WithFields(proposal, ("review",
            ReadMosaicReviews(connection, transaction, proposalActor: proposalActorId, proposalCommand: proposalCommandId).SingleOrDefault()));
        return Protocol.Reply(200, body).WithInstance(instance);
    }

    public ApiReply Events(string tokenHash, long after, string? expectedInstance = null)
    {
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance);
        var state = ReadState(connection, transaction);
        if (after > state.Cursor)
            return Protocol.Error(Scenario.RulesVersion, 409, "CURSOR_AHEAD", "事件游标超过当前世界，请重新观察", identity, state.Version, state.Cursor).WithInstance(instance);
        var events = new List<JsonElement>();
        var nextCursor = after;
        using (var command = Command(connection, transaction,
                   "SELECT seq,event_json FROM events WHERE world_id=$world AND seq>$after ORDER BY seq LIMIT 100",
                   ("$world", Protocol.WorldId), ("$after", after)))
        using (var reader = command.ExecuteReader())
            while (reader.Read())
            {
                nextCursor = reader.GetInt64(0);
                using var document = JsonDocument.Parse(reader.GetString(1));
                events.Add(document.RootElement.Clone());
            }
        var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor);
        body["events"] = events;
        body["nextCursor"] = nextCursor;
        return Protocol.Reply(200, body).WithInstance(instance);
    }

    public ApiReply Receipt(string tokenHash, string id, string? expectedInstance = null)
    {
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: true);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance, required: true);
        var receipt = FindReceipt(connection, transaction, identity.ActorId, id);
        if (receipt is not null) return receipt.Value.Reply.WithInstance(instance);
        var state = ReadState(connection, transaction);
        return Protocol.Error(Scenario.RulesVersion, 404, "COMMAND_NOT_FOUND", "未找到当前居民的命令回执", identity, state.Version, state.Cursor, id).WithInstance(instance);
    }

    public string? Revoke(string tokenHash, string? expectedInstance = null)
    {
        using var connection = database.Open();
        using var transaction = connection.BeginTransaction(deferred: false);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance, required: true);
        Run(connection, transaction, "UPDATE sessions SET revoked=1 WHERE session_id=$session", ("$session", identity.SessionId));
        transaction.Commit();
        return instance;
    }

    public ApiReply Execute(string tokenHash, WorldCommand request, string? requestedFault, string? expectedInstance = null)
    {
        var requestHash = request.RequestHash;
        using var connection = database.Open();
        // BEGIN IMMEDIATE serializes the complete read/check/write decision against other writers.
        using var transaction = connection.BeginTransaction(deferred: false);
        var identity = database.Authenticate(tokenHash, connection, transaction);
        var instance = WorldInstance.Require(connection, transaction, expectedInstance, required: true);
        var previous = FindReceipt(connection, transaction, identity.ActorId, request.CommandId);
        if (previous is not null)
        {
            if (previous.Value.Hash == requestHash) return previous.Value.Reply.WithInstance(instance);
            var current = ReadState(connection, transaction);
            return Protocol.Error(Scenario.RulesVersion, 409, "IDEMPOTENCY_CONFLICT", "命令 ID 已用于不同参数", identity, current.Version, current.Cursor, request.CommandId).WithInstance(instance);
        }
        if (Scenario.SupportsMaterialAccess)
            MaterialSourceRules.Advance(connection, transaction, materialClock?.Now ?? throw new InvalidOperationException("缺少材料服务时钟"));
        var state = ReadState(connection, transaction);
        var actor = ReadActor(connection, transaction, identity.ActorId);
        var action = request.Action;
        var fault = configuration.FaultsEnabled && action.Type is "claim" or "gather" or "build" or "transfer" or "reserve_material" or "cancel_reservation" or "harvest_material" or "visit" or "postcard" or "mosaic" or "mosaic_propose" or "mosaic_review" ? requestedFault : null;
        var rejection = Validate(connection, transaction, request, state, actor, identity, instance);
        if (rejection is not null)
        {
            var body = Protocol.Envelope(Scenario.RulesVersion, identity, state.Version, state.Cursor, request.CommandId, rejection.Value.Error);
            body["status"] = "rejected";
            BindExecution(body, request, state.Version);
            var denied = Protocol.Reply(rejection.Value.Status, body);
            SaveReceipt(connection, transaction, identity.ActorId, request.CommandId, requestHash, denied);
            database.Authenticate(tokenHash, connection, transaction);
            transaction.Commit();
            return denied.WithInstance(instance);
        }

        var version = checked(state.Version + 1);
        var cursor = checked(state.Cursor + 1);
        object result;
        object worldEvent;
        string? source = null, destination = null;
        long quantity = 0;
        switch (action.Type)
        {
            case "reserve_material":
            case "cancel_reservation":
            case "harvest_material":
                (result, worldEvent, source, destination, quantity) = ApplyMaterialAccess(connection, transaction, request, identity, actor, version, cursor, fault);
                break;
            case "walk":
                var walked = WalkContinuous(connection, transaction, actor, identity.ActorId, action.TargetX, action.TargetY);
                result = new { action = "walk", position = walked.Position, blocked = walked.Blocked };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId, type = "walked", position = walked.Position, blocked = walked.Blocked };
                break;
            case "move":
                var x = actor.X + action.Dx;
                var y = actor.Y + action.Dy;
                Run(connection, transaction, "UPDATE residents SET x=$x,y=$y WHERE world_id=$world AND actor_id=$actor",
                    ("$x", x), ("$y", y), ("$world", Protocol.WorldId), ("$actor", identity.ActorId));
                result = new { action = "move", position = new[] { x, y } };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId, type = "moved", position = new[] { x, y } };
                break;
            case "claim":
                GuardedDebit(Run(connection, transaction, "UPDATE worlds SET depot_wood=depot_wood-$quantity WHERE id=$world AND depot_wood>=$quantity",
                    ("$quantity", action.Quantity), ("$world", Protocol.WorldId)));
                InjectAfterDebit(fault);
                Run(connection, transaction, "UPDATE residents SET wood=wood+$quantity WHERE world_id=$world AND actor_id=$actor",
                    ("$quantity", action.Quantity), ("$world", Protocol.WorldId), ("$actor", identity.ActorId));
                result = new { action = "claim", quantity = action.Quantity, inventoryWood = actor.Wood + action.Quantity, depotWood = state.DepotWood - action.Quantity };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId, type = "claimed", quantity = action.Quantity };
                source = "depot";
                destination = "inventory:" + identity.ActorId;
                quantity = action.Quantity;
                break;
            case "gather":
                var node = ReadResourceNodes(connection, transaction).Single(n => n.NodeId == action.NodeId);
                GuardedDebit(Run(connection, transaction, """
                    UPDATE resource_nodes SET remaining_wood=remaining_wood-1
                    WHERE world_id=$world AND node_id=$node AND remaining_wood>0
                    """, ("$world", Protocol.WorldId), ("$node", action.NodeId)));
                InjectAfterDebit(fault);
                Run(connection, transaction, "UPDATE residents SET wood=wood+1 WHERE world_id=$world AND actor_id=$actor",
                    ("$world", Protocol.WorldId), ("$actor", identity.ActorId));
                result = request.PreconditionMode is null
                    ? (object)new { action = "gather", nodeId = node.NodeId, quantity = 1,
                        position = node.Position, remainingWood = node.RemainingWood - 1, inventoryWood = actor.Wood + 1 }
                    : new { action = "gather", nodeId = node.NodeId, quantity = 1,
                        position = node.Position, remainingWoodBefore = node.RemainingWood,
                        remainingWood = node.RemainingWood - 1, inventoryWood = actor.Wood + 1 };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId,
                    type = "gathered", nodeId = node.NodeId, quantity = 1, position = node.Position, remainingWood = node.RemainingWood - 1 };
                source = "wild-wood";
                destination = "inventory:" + identity.ActorId;
                quantity = 1;
                break;
            case "transfer":
                GuardedDebit(Run(connection, transaction, "UPDATE residents SET wood=wood-$quantity WHERE world_id=$world AND actor_id=$actor AND wood>=$quantity",
                    ("$quantity", action.Quantity), ("$world", Protocol.WorldId), ("$actor", identity.ActorId)));
                InjectAfterDebit(fault);
                GuardedDebit(Run(connection, transaction, "UPDATE residents SET wood=wood+$quantity WHERE world_id=$world AND actor_id=$actor AND wood+$quantity<=12",
                    ("$quantity", action.Quantity), ("$world", Protocol.WorldId), ("$actor", action.RecipientActorId)));
                result = new { action = "transfer", resource = "wood", quantity = action.Quantity,
                    senderActorId = identity.ActorId, recipientActorId = action.RecipientActorId, inventoryWood = actor.Wood - action.Quantity };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId,
                    type = "woodTransferred", recipientActorId = action.RecipientActorId, resource = "wood", quantity = action.Quantity };
                source = "inventory:" + identity.ActorId;
                destination = "inventory:" + action.RecipientActorId;
                quantity = action.Quantity;
                break;
            case "visit":
                var visitedAtUtc = DateTimeOffset.UtcNow.ToString("O");
                Run(connection, transaction, """
                    INSERT INTO visits(world_id,actor_id,command_id,activity_id,state_version,visited_at_utc,x,y)
                    VALUES($world,$actor,$command,$activity,$version,$visited,$x,$y)
                    """, ("$world", Protocol.WorldId), ("$actor", identity.ActorId), ("$command", request.CommandId),
                    ("$activity", action.ActivityId), ("$version", version), ("$visited", visitedAtUtc), ("$x", actor.X), ("$y", actor.Y));
                result = new { action = "visit", activityId = action.ActivityId, position = new[] { actor.X, actor.Y }, visitedAtUtc };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId,
                    type = "visited", activityId = action.ActivityId, position = new[] { actor.X, actor.Y } };
                break;
            case "postcard":
                var postcard = new Postcard(action.ActivityId!, identity.ActorId, request.CommandId, action.VisitCommandId!,
                    action.Text!, version, DateTimeOffset.UtcNow.ToString("O"), [(long)actor.X, (long)actor.Y]);
                Run(connection, transaction, """
                    INSERT INTO postcards(world_id,author_actor_id,command_id,visit_command_id,activity_id,text,state_version,shared_at_utc,x,y)
                    VALUES($world,$actor,$command,$visit,$activity,$text,$version,$shared,$x,$y)
                    """, ("$world", Protocol.WorldId), ("$actor", postcard.AuthorActorId), ("$command", postcard.CommandId),
                    ("$visit", postcard.VisitCommandId), ("$activity", postcard.ActivityId), ("$text", postcard.Text),
                    ("$version", postcard.StateVersion), ("$shared", postcard.SharedAtUtc), ("$x", actor.X), ("$y", actor.Y));
                result = new { action = "postcard", postcard.ActivityId, postcard.AuthorActorId, postcard.CommandId,
                    postcard.VisitCommandId, postcard.Text, postcard.StateVersion, postcard.SharedAtUtc, postcard.Position };
                worldEvent = new { seq = cursor, type = "postcard_shared", actorId = identity.ActorId, postcard.ActivityId, postcard.AuthorActorId,
                    postcard.CommandId, postcard.VisitCommandId, postcard.Text, postcard.StateVersion, postcard.SharedAtUtc, postcard.Position };
                break;
            case "mosaic":
                var edit = new MosaicEdit(action.ActivityId!, identity.ActorId, request.CommandId, action.VisitCommandId!,
                    action.ExpectedMosaicRevision, checked(action.ExpectedMosaicRevision + 1), action.Patch!,
                    version, DateTimeOffset.UtcNow.ToString("O"), [(long)actor.X, (long)actor.Y]);
                ApplyMosaicEdit(connection, transaction, edit);
                result = new { action = "mosaic", edit.ActivityId, edit.AuthorActorId, edit.CommandId, edit.VisitCommandId,
                    edit.BaseRevision, edit.Revision, edit.Patch, edit.StateVersion, edit.PaintedAtUtc, edit.Position };
                worldEvent = new { seq = cursor, type = "mosaic_painted", actorId = identity.ActorId, edit.ActivityId,
                    edit.AuthorActorId, edit.CommandId, edit.VisitCommandId, edit.BaseRevision, edit.Revision,
                    edit.Patch, edit.StateVersion, edit.PaintedAtUtc, edit.Position };
                break;
            case "mosaic_propose":
                var proposal = new MosaicProposal(action.ActivityId!, identity.ActorId,
                    MosaicCellAuthor(connection, transaction, action.Patch![0])!, request.CommandId, action.VisitCommandId!,
                    action.ExpectedMosaicRevision, action.Patch, action.Text!, version, DateTimeOffset.UtcNow.ToString("O"), [(long)actor.X, (long)actor.Y]);
                Run(connection, transaction, """
                    INSERT INTO mosaic_proposals(world_id,activity_id,author_actor_id,target_actor_id,command_id,visit_command_id,
                        base_revision,patch_json,text,state_version,proposed_at_utc,x,y)
                    VALUES($world,$activity,$actor,$target,$command,$visit,$base,$patch,$text,$version,$proposed,$x,$y)
                    """, ("$world", Protocol.WorldId), ("$activity", proposal.ActivityId), ("$actor", proposal.AuthorActorId),
                    ("$target", proposal.TargetActorId), ("$command", proposal.CommandId), ("$visit", proposal.VisitCommandId),
                    ("$base", proposal.BaseRevision), ("$patch", JsonSerializer.Serialize(proposal.Patch, Protocol.Json)),
                    ("$text", proposal.Text), ("$version", version), ("$proposed", proposal.ProposedAtUtc), ("$x", actor.X), ("$y", actor.Y));
                result = WithFields(proposal, ("action", "mosaic_propose"));
                worldEvent = WithFields(proposal, ("seq", cursor), ("type", "mosaic_proposed"), ("actorId", identity.ActorId));
                break;
            case "mosaic_review":
                var original = FindMosaicProposal(connection, transaction, action.ProposalActorId!, action.ProposalCommandId!)!;
                var reviewedAtUtc = DateTimeOffset.UtcNow.ToString("O");
                MosaicEdit? acceptedEdit = null;
                if (action.Decision == "accept")
                {
                    acceptedEdit = new(original.ActivityId, identity.ActorId, request.CommandId, action.VisitCommandId!,
                        original.BaseRevision, checked(original.BaseRevision + 1), original.Patch, version, reviewedAtUtc, [(long)actor.X, (long)actor.Y]);
                    ApplyMosaicEdit(connection, transaction, acceptedEdit);
                }
                var review = new MosaicReview(action.ActivityId!, identity.ActorId, request.CommandId, action.VisitCommandId!,
                    original.AuthorActorId, original.CommandId, action.Decision!, action.Text!, version, reviewedAtUtc, [(long)actor.X, (long)actor.Y], acceptedEdit);
                Run(connection, transaction, """
                    INSERT INTO mosaic_reviews(world_id,activity_id,author_actor_id,command_id,visit_command_id,
                        proposal_actor_id,proposal_command_id,decision,text,state_version,reviewed_at_utc,x,y,edit_command_id)
                    VALUES($world,$activity,$actor,$command,$visit,$proposer,$proposal,$decision,$text,$version,$reviewed,$x,$y,$edit)
                    """, ("$world", Protocol.WorldId), ("$activity", review.ActivityId), ("$actor", review.AuthorActorId),
                    ("$command", review.CommandId), ("$visit", review.VisitCommandId), ("$proposer", review.ProposalActorId),
                    ("$proposal", review.ProposalCommandId), ("$decision", review.Decision), ("$text", review.Text),
                    ("$version", version), ("$reviewed", reviewedAtUtc), ("$x", actor.X), ("$y", actor.Y), ("$edit", acceptedEdit?.CommandId));
                result = WithFields(review, ("action", "mosaic_review"));
                worldEvent = WithFields(review, ("seq", cursor), ("type", "mosaic_reviewed"), ("actorId", identity.ActorId));
                break;
            default:
                var buildX = Scenario.SupportsContinuous ? action.TargetX : action.X;
                var buildY = Scenario.SupportsContinuous ? action.TargetY : action.Y;
                var cost = Scalar(connection, transaction, "SELECT wood_cost FROM recipes WHERE id=$recipe", ("$recipe", action.RecipeId));
                GuardedDebit(Run(connection, transaction, "UPDATE residents SET wood=wood-$cost WHERE world_id=$world AND actor_id=$actor AND wood>=$cost",
                    ("$cost", cost), ("$world", Protocol.WorldId), ("$actor", identity.ActorId)));
                InjectAfterDebit(fault);
                var entityId = "e" + Guid.NewGuid().ToString("N");
                Run(connection, transaction, """
                    INSERT INTO entities(entity_id,world_id,owner_actor_id,recipe_id,definition_id,definition_version,rules_version,x,y,embodied_wood)
                    SELECT $id,$world,$actor,id,definition_id,definition_version,rules_version,$x,$y,wood_cost FROM recipes WHERE id=$recipe
                    """, ("$id", entityId), ("$world", Protocol.WorldId), ("$actor", identity.ActorId),
                    ("$x", buildX), ("$y", buildY), ("$recipe", action.RecipeId));
                result = new { action = "build", entityId, position = new[] { buildX, buildY }, inventoryWood = actor.Wood - cost };
                worldEvent = new { seq = cursor, stateVersion = version, commandId = request.CommandId, actorId = identity.ActorId, type = "built", entityId, position = new[] { buildX, buildY } };
                source = "inventory:" + identity.ActorId;
                destination = "entity:" + entityId;
                quantity = cost;
                break;
        }
        GuardedDebit(Run(connection, transaction, "UPDATE worlds SET state_version=$next WHERE id=$world AND state_version=$previous",
            ("$next", version), ("$world", Protocol.WorldId), ("$previous", state.Version)));
        Run(connection, transaction, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES($seq,$world,$version,$json)",
            ("$seq", cursor), ("$world", Protocol.WorldId), ("$version", version), ("$json", JsonSerializer.Serialize(worldEvent, Protocol.Json)));
        if (quantity > 0)
            Run(connection, transaction, """
                INSERT INTO resource_ledger(world_id,event_seq,command_id,actor_id,source_account,destination_account,quantity)
                VALUES($world,$seq,$command,$actor,$source,$destination,$quantity)
                """, ("$world", Protocol.WorldId), ("$seq", cursor), ("$command", request.CommandId), ("$actor", identity.ActorId),
                ("$source", source), ("$destination", destination), ("$quantity", quantity));
        var committed = Protocol.Envelope(Scenario.RulesVersion, identity, version, cursor, request.CommandId);
        committed["status"] = "committed";
        committed["result"] = result;
        BindExecution(committed, request, state.Version);
        var reply = Protocol.Reply(200, committed);
        SaveReceipt(connection, transaction, identity.ActorId, request.CommandId, requestHash, reply);
        database.Authenticate(tokenHash, connection, transaction);
        if (fault == "before-commit") Environment.Exit(81);
        transaction.Commit();
        if (fault == "after-commit") Environment.Exit(82);
        return reply.WithInstance(instance);
    }

    private (int Status, ApiError Error)? Validate(SqliteConnection connection, SqliteTransaction transaction,
        WorldCommand request, State state, Actor actor, Identity identity, string? instance)
    {
        var actorId = identity.ActorId;
        if (request.RulesVersion != Scenario.RulesVersion)
            return (409, new("RULES_VERSION_MISMATCH", "规则版本不匹配，请重新观察"));
        if (request.PreconditionMode is null)
        {
            if (request.ExpectedStateVersion != state.Version)
                return (409, new("STALE_STATE", "世界已更新，请重新观察"));
        }
        else
        {
            if (instance is null || !Scenario.SupportsContinuous ||
                !(request.Action.Type is "walk" or "gather" or "build" || Scenario.SupportsTransfer && request.Action.Type == "transfer" ||
                    Scenario.SupportsMaterialAccess && request.Action.Type is "reserve_material" or "cancel_reservation" or "harvest_material"))
                return (422, new("PRECONDITION_MODE_UNAVAILABLE", "当前世界或动作不支持这个前置条件模式"));
            if (request.ExpectedStateVersion > state.Version)
                return (409, new("STATE_VERSION_AHEAD", "观察版本超过当前世界，请重新观察"));
            // A successful incoming transfer also changes the recipient's state. Reject even
            // if later activity restores the original balance or position (ABA).
            if (Scalar(connection, transaction, """
                SELECT EXISTS(SELECT 1 FROM events WHERE world_id=$world AND state_version>$observed
                    AND (json_extract(event_json,'$.actorId')=$actor OR
                        (json_extract(event_json,'$.type')='woodTransferred' AND json_extract(event_json,'$.recipientActorId')=$actor)))
                """, ("$world", Protocol.WorldId), ("$observed", request.ExpectedStateVersion), ("$actor", actorId)) != 0)
                return (409, new("STALE_ACTOR_STATE", "这位居民的状态已变化，请重新观察"));
        }
        var action = request.Action;
        if (action.Type is "reserve_material" or "cancel_reservation" or "harvest_material")
            return ValidateMaterialAccess(connection, transaction, action, actor, identity);
        if (action.Type == "transfer") return ValidateTransfer(connection, transaction, action, actor, actorId);
        if (Scenario.SupportsContinuous) return ValidateContinuous(connection, transaction, action, actor);
        if (action.Type == "move")
        {
            // Do not abs/add untrusted integers before bounding them (long.MinValue must not overflow).
            if (!((action.Dx is -1 or 1 && action.Dy == 0) || (action.Dy is -1 or 1 && action.Dx == 0)) ||
                !Walkable(connection, transaction, (long)actor.X + action.Dx, (long)actor.Y + action.Dy))
                return (422, new("UNREACHABLE", "只能向可通行的相邻格移动一步"));
        }
        else if (action.Type == "claim")
        {
            if (Scenario.SupportsGathering)
                return (422, new("NO_PUBLIC_DEPOT", "这里尚无公共储备，请到树旁采集木材"));
            if (Math.Abs(actor.X - 1) + Math.Abs(actor.Y - 1) > 1)
                return (422, new("UNREACHABLE", "请移动到储备点或相邻格领取"));
            if (state.DepotWood < action.Quantity)
                return (422, new("INSUFFICIENT_RESOURCE", "公共木材储备不足"));
        }
        else if (action.Type == "gather")
        {
            if (!Scenario.SupportsGathering)
                return (422, new("GATHERING_UNAVAILABLE", "当前世界不支持自然资源采集"));
            var node = ReadResourceNodes(connection, transaction).SingleOrDefault(n => n.NodeId == action.NodeId);
            if (node is null) return (404, new("RESOURCE_NOT_FOUND", "资源节点不存在"));
            if (node.RemainingWood == 0) return (422, new("RESOURCE_DEPLETED", "这里的木材已采空"));
            if (Math.Abs(actor.X - node.Position[0]) + Math.Abs(actor.Y - node.Position[1]) != 1)
                return (422, new("UNREACHABLE", "请移动到树木上下左右相邻的一格再采集"));
        }
        else if (action.Type == "visit")
        {
            if (!Scenario.SupportsActivities)
                return (422, new("ACTIVITY_UNAVAILABLE", "当前世界不支持地点活动"));
            var activity = Scenario.ActivityCatalog.FirstOrDefault(candidate => candidate.Id == action.ActivityId);
            if (activity is null)
                return (422, new("ACTIVITY_NOT_FOUND", "活动地点不存在"));
            if (actor.X != activity.X || actor.Y != activity.Y)
                return (422, new("NOT_AT_ACTIVITY", "请先到达活动地点"));
        }
        else if (action.Type == "postcard")
        {
            if (!Scenario.SupportsPostcards)
                return (422, new("POSTCARD_UNAVAILABLE", "当前世界不支持共同手记"));
            var activity = Scenario.ActivityCatalog.FirstOrDefault(candidate => candidate.Id == action.ActivityId);
            if (activity is null)
                return (422, new("ACTIVITY_NOT_FOUND", "活动地点不存在"));
            if (actor.X != activity.X || actor.Y != activity.Y)
                return (422, new("NOT_AT_ACTIVITY", "请先到达活动地点"));
            if (Scalar(connection, transaction, """
                    SELECT count(*) FROM visits WHERE world_id=$world AND actor_id=$actor
                      AND command_id=$visit AND activity_id=$activity
                    """, ("$world", Protocol.WorldId), ("$actor", actorId), ("$visit", action.VisitCommandId),
                    ("$activity", action.ActivityId)) != 1)
                return (422, new("VISIT_REQUIRED", "请引用自己在此地点已确认的到访命令"));
            if (Scalar(connection, transaction, """
                    SELECT count(*) FROM postcards WHERE world_id=$world AND author_actor_id=$actor AND visit_command_id=$visit
                    """, ("$world", Protocol.WorldId), ("$actor", actorId), ("$visit", action.VisitCommandId)) != 0)
                return (409, new("VISIT_ALREADY_SHARED", "此次到访已经分享过手记"));
        }
        else if (action.Type is "mosaic" or "mosaic_propose" or "mosaic_review")
        {
            if (action.Type != "mosaic" && !Scenario.SupportsMosaicConsent)
                return (422, new("MOSAIC_CONSENT_UNAVAILABLE", "当前世界不支持画布协商"));
            if (!Scenario.SupportsMosaic)
                return (422, new("MOSAIC_UNAVAILABLE", "当前世界不支持共同画布"));
            if (action.ActivityId != "garden")
                return (422, new("MOSAIC_LOCATION_UNAVAILABLE", "只有花园提供共同画布"));
            var garden = Scenario.ActivityCatalog.Single(activity => activity.Id == "garden");
            if (actor.X != garden.X || actor.Y != garden.Y)
                return (422, new("NOT_AT_ACTIVITY", "请先到达花园"));
            if (Scalar(connection, transaction, """
                    SELECT count(*) FROM visits WHERE world_id=$world AND actor_id=$actor
                      AND command_id=$visit AND activity_id='garden'
                    """, ("$world", Protocol.WorldId), ("$actor", actorId), ("$visit", action.VisitCommandId)) != 1)
                return (422, new("VISIT_REQUIRED", "请引用自己在花园已确认的到访命令"));
            if (action.Type == "mosaic_review")
            {
                var proposal = FindMosaicProposal(connection, transaction, action.ProposalActorId!, action.ProposalCommandId!);
                if (proposal is null)
                    return (404, new("MOSAIC_PROPOSAL_NOT_FOUND", "未找到原画布提议"));
                if (proposal.TargetActorId != actorId)
                    return (403, new("MOSAIC_REVIEW_FORBIDDEN", "只有原格最后作者可以审阅"));
                if (ReadMosaicReviews(connection, transaction, proposalActor: proposal.AuthorActorId, proposalCommand: proposal.CommandId).Count != 0)
                    return (409, new("MOSAIC_PROPOSAL_REVIEWED", "此提议已有终态审阅"));
                if (action.Decision == "accept")
                {
                    if (HasMosaicEdit(connection, transaction, actorId, action.VisitCommandId!))
                        return (409, new("VISIT_ALREADY_PAINTED", "此次到访已经修改过画布"));
                    if (proposal.BaseRevision != MosaicRevision(connection, transaction))
                        return (409, new("MOSAIC_CHANGED", "画布已变化，无法接受原提议"));
                }
                return null;
            }
            if (action.Type == "mosaic_propose")
            {
                if (Scalar(connection, transaction, """
                        SELECT count(*) FROM mosaic_proposals WHERE world_id=$world AND author_actor_id=$actor AND visit_command_id=$visit
                        """, ("$world", Protocol.WorldId), ("$actor", actorId), ("$visit", action.VisitCommandId)) != 0)
                    return (409, new("VISIT_ALREADY_PROPOSED", "此次到访已经提出过画布修改"));
            }
            else if (HasMosaicEdit(connection, transaction, actorId, action.VisitCommandId!))
                return (409, new("VISIT_ALREADY_PAINTED", "此次到访已经修改过画布"));
            if (action.ExpectedMosaicRevision != MosaicRevision(connection, transaction))
                return (409, new("MOSAIC_CHANGED", "画布已被修改，请保留草稿并重新构图"));
            foreach (var cell in action.Patch!)
                if (Scalar(connection, transaction, """
                        SELECT count(*) FROM mosaic_cells WHERE world_id=$world AND activity_id='garden' AND x=$x AND y=$y AND color=$color
                        """, ("$world", Protocol.WorldId), ("$x", cell.X), ("$y", cell.Y), ("$color", cell.Color)) != 0)
                    return (422, new("MOSAIC_UNCHANGED", "每个提交格的颜色都必须发生变化"));
            if (Scenario.SupportsMosaicConsent)
            {
                var authors = action.Patch!.Select(cell => MosaicCellAuthor(connection, transaction, cell)).ToArray();
                if (action.Type == "mosaic_propose")
                {
                    if (authors.Any(author => author is null || author == actorId) || authors.Distinct().Count() != 1)
                        return (422, new("MOSAIC_PROPOSAL_TARGET_INVALID", "提议必须只修改同一名其他居民的格子"));
                }
                else if (authors.Any(author => author is not null && author != actorId))
                    return (409, new("MOSAIC_CONSENT_REQUIRED", "修改他人的格子需要先提出协商"));
            }
        }
        else
        {
            var bridge = action.RecipeId == "bridge.v1";
            // Bound coordinates before computing distance; hostile 64-bit values must be rejected,
            // not overflow into a service failure or reach a debit.
            if (!(bridge ? Scenario.IsWater(action.X, action.Y) : Scenario.IsLand(action.X, action.Y)))
                return (422, new("UNREACHABLE", bridge ? "桥段只能建在四邻水格" : "平台只能建在自身或相邻陆地"));
            var distance = Math.Abs(actor.X - action.X) + Math.Abs(actor.Y - action.Y);
            if ((bridge ? distance != 1 : distance > 1) || !Walkable(connection, transaction, (long)actor.X, (long)actor.Y))
                return (422, new("UNREACHABLE", bridge ? "请从可通行格向四邻水格铺桥" : "平台只能建在自身或相邻陆地"));
            if (Scalar(connection, transaction, "SELECT count(*) FROM entities WHERE world_id=$world AND x=$x AND y=$y",
                    ("$world", Protocol.WorldId), ("$x", action.X), ("$y", action.Y)) != 0)
                return (409, new("CELL_OCCUPIED", "目标格已有实体"));
            if (Scenario.SupportsGathering && Scalar(connection, transaction,
                    "SELECT count(*) FROM resource_nodes WHERE world_id=$world AND x=$x AND y=$y AND remaining_wood>0",
                    ("$world", Protocol.WorldId), ("$x", action.X), ("$y", action.Y)) != 0)
                return (409, new("CELL_OCCUPIED", "目标格还有树木，请先采集清理"));
            var cost = Scalar(connection, transaction, "SELECT wood_cost FROM recipes WHERE id=$recipe", ("$recipe", action.RecipeId));
            if (actor.Wood < cost) return (422, new("INSUFFICIENT_RESOURCE", "自身木材不足，建造需要 3 单位"));
        }
        return null;
    }

    private bool Walkable(SqliteConnection connection, SqliteTransaction transaction, long x, long y) =>
        (Scenario.IsLand(x, y) || Scenario.IsWater(x, y) && Scalar(connection, transaction,
            "SELECT count(*) FROM entities WHERE world_id=$world AND x=$x AND y=$y AND definition_id='bridge'",
            ("$world", Protocol.WorldId), ("$x", x), ("$y", y)) == 1)
        && (!Scenario.SupportsGathering || Scalar(connection, transaction,
            "SELECT count(*) FROM resource_nodes WHERE world_id=$world AND x=$x AND y=$y AND remaining_wood>0",
            ("$world", Protocol.WorldId), ("$x", x), ("$y", y)) == 0);
    private static List<WorldResourceNode> ReadResourceNodes(SqliteConnection connection, SqliteTransaction transaction)
    {
        var resources = new List<WorldResourceNode>();
        using var command = Command(connection, transaction,
            "SELECT node_id,kind,x,y,initial_wood,remaining_wood FROM resource_nodes WHERE world_id=$world ORDER BY node_id",
            ("$world", Protocol.WorldId));
        using var reader = command.ExecuteReader();
        while (reader.Read()) resources.Add(new(reader.GetString(0), reader.GetString(1),
            [reader.GetDouble(2), reader.GetDouble(3)], reader.GetInt64(4), reader.GetInt64(5)));
        return resources;
    }

    private static void GuardedDebit(int affected) { if (affected != 1) throw new InvalidOperationException("事务条件写入未命中唯一状态"); }
    private static void InjectAfterDebit(string? fault) { if (fault == "throw-after-debit") throw new InjectedFailure(); }

    private sealed record State(long Version, long Cursor, long DepotWood, long IssuedWood);
    private sealed record Actor(double X, double Y, long Wood);
    private sealed record Postcard(string ActivityId, string AuthorActorId, string CommandId, string VisitCommandId,
        string Text, long StateVersion, string SharedAtUtc, long[] Position);
    private sealed record MosaicEdit(string ActivityId, string AuthorActorId, string CommandId, string VisitCommandId,
        long BaseRevision, long Revision, MosaicPatchCell[] Patch, long StateVersion, string PaintedAtUtc, long[] Position);

    private static void ApplyMosaicEdit(SqliteConnection connection, SqliteTransaction transaction, MosaicEdit edit)
    {
        Run(connection, transaction, """
            INSERT INTO mosaic_edits(world_id,activity_id,author_actor_id,command_id,visit_command_id,
                base_revision,revision,patch_json,state_version,painted_at_utc,x,y)
            VALUES($world,$activity,$actor,$command,$visit,$base,$revision,$patch,$version,$painted,$x,$y)
            """, ("$world", Protocol.WorldId), ("$activity", edit.ActivityId), ("$actor", edit.AuthorActorId),
            ("$command", edit.CommandId), ("$visit", edit.VisitCommandId), ("$base", edit.BaseRevision),
            ("$revision", edit.Revision), ("$patch", JsonSerializer.Serialize(edit.Patch, Protocol.Json)),
            ("$version", edit.StateVersion), ("$painted", edit.PaintedAtUtc), ("$x", edit.Position[0]), ("$y", edit.Position[1]));
        foreach (var cell in edit.Patch)
            GuardedDebit(Run(connection, transaction, """
                UPDATE mosaic_cells SET color=$color,author_actor_id=$actor,command_id=$command,state_version=$version
                WHERE world_id=$world AND activity_id=$activity AND x=$x AND y=$y
                """, ("$color", cell.Color), ("$actor", edit.AuthorActorId), ("$command", edit.CommandId),
                ("$version", edit.StateVersion), ("$world", Protocol.WorldId), ("$activity", edit.ActivityId), ("$x", cell.X), ("$y", cell.Y)));
        GuardedDebit(Run(connection, transaction, """
            UPDATE mosaics SET revision=$revision WHERE world_id=$world AND activity_id=$activity AND revision=$base
            """, ("$revision", edit.Revision), ("$world", Protocol.WorldId), ("$activity", edit.ActivityId), ("$base", edit.BaseRevision)));
    }

    private static bool HasMosaicEdit(SqliteConnection connection, SqliteTransaction transaction, string actor, string visit) =>
        Scalar(connection, transaction, """
            SELECT count(*) FROM mosaic_edits WHERE world_id=$world AND author_actor_id=$actor AND visit_command_id=$visit
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$visit", visit)) != 0;

    private static string? MosaicCellAuthor(SqliteConnection connection, SqliteTransaction transaction, MosaicPatchCell cell)
    {
        using var command = Command(connection, transaction, """
            SELECT author_actor_id FROM mosaic_cells WHERE world_id=$world AND activity_id='garden' AND x=$x AND y=$y
            """, ("$world", Protocol.WorldId), ("$x", cell.X), ("$y", cell.Y));
        return command.ExecuteScalar() as string;
    }

    private static void BindObservation(Dictionary<string, object?> body, string? instance)
    {
        if (instance is null) return;
        body["world"] = WithFields(body["world"]!, ("instanceId", instance));
        body["commandBinding"] = new { version = 1, required = true, header = WorldInstance.Header };
        if (body["rulesVersion"] is "r8" or "r9" or "r10")
            body["commandConcurrency"] = new { version = 1, supportedModes = new[] { Protocol.ActorStateMode } };
    }

    private static void BindExecution(Dictionary<string, object?> body, WorldCommand request, long appliedOn)
    {
        if (request.PreconditionMode is null) return;
        body["execution"] = new { preconditionMode = request.PreconditionMode,
            observedStateVersion = request.ExpectedStateVersion, appliedOnStateVersion = appliedOn };
    }

    private static Dictionary<string, object?> WithFields(object record, params (string Name, object? Value)[] fields)
    {
        var result = JsonSerializer.SerializeToElement(record, Protocol.Json).EnumerateObject()
            .ToDictionary(property => property.Name, property => (object?)property.Value);
        foreach (var (name, value) in fields) result.Add(name, value);
        return result;
    }

    private sealed record MosaicProposal(string ActivityId, string AuthorActorId, string TargetActorId, string CommandId,
        string VisitCommandId, long BaseRevision, MosaicPatchCell[] Patch, string Text, long StateVersion, string ProposedAtUtc, long[] Position);
    private sealed record MosaicReview(string ActivityId, string AuthorActorId, string CommandId, string VisitCommandId,
        string ProposalActorId, string ProposalCommandId, string Decision, string Text, long StateVersion, string ReviewedAtUtc,
        long[] Position, MosaicEdit? MosaicEdit);

    private static MosaicProposal ReadMosaicProposal(SqliteDataReader reader) =>
        new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3), reader.GetString(4),
            reader.GetInt64(5), JsonSerializer.Deserialize<MosaicPatchCell[]>(reader.GetString(6), Protocol.Json)!,
            reader.GetString(7), reader.GetInt64(8), reader.GetString(9), [reader.GetInt64(10), reader.GetInt64(11)]);

    private const string ProposalColumns = "activity_id,author_actor_id,target_actor_id,command_id,visit_command_id,base_revision,patch_json,text,state_version,proposed_at_utc,x,y";

    private static MosaicProposal? FindMosaicProposal(SqliteConnection connection, SqliteTransaction transaction, string actor, string id)
    {
        using var command = Command(connection, transaction, $"""
            SELECT {ProposalColumns} FROM mosaic_proposals WHERE world_id=$world AND author_actor_id=$actor AND command_id=$id
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$id", id));
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadMosaicProposal(reader) : null;
    }

    private static List<object> ReadMosaicProposals(SqliteConnection connection, SqliteTransaction transaction, string? actor = null)
    {
        var proposals = new List<MosaicProposal>();
        using (var command = Command(connection, transaction, $"""
            SELECT {ProposalColumns} FROM (
                SELECT * FROM mosaic_proposals WHERE world_id=$world AND ($actor IS NULL OR author_actor_id=$actor)
                ORDER BY state_version DESC LIMIT $limit
            ) ORDER BY state_version
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$limit", actor is null ? 50 : 100)))
        using (var reader = command.ExecuteReader())
            while (reader.Read()) proposals.Add(ReadMosaicProposal(reader));
        return proposals.Select(proposal => (object)WithFields(proposal, ("review",
            ReadMosaicReviews(connection, transaction, proposalActor: proposal.AuthorActorId, proposalCommand: proposal.CommandId).SingleOrDefault()))).ToList();
    }

    private static List<MosaicReview> ReadMosaicReviews(SqliteConnection connection, SqliteTransaction transaction,
        string? actor = null, string? proposalActor = null, string? proposalCommand = null)
    {
        var reviews = new List<MosaicReview>();
        using var command = Command(connection, transaction, """
            SELECT r.activity_id,r.author_actor_id,r.command_id,r.visit_command_id,r.proposal_actor_id,r.proposal_command_id,
                r.decision,r.text,r.state_version,r.reviewed_at_utc,r.x,r.y,
                e.base_revision,e.revision,e.patch_json
            FROM (SELECT * FROM mosaic_reviews WHERE world_id=$world AND ($actor IS NULL OR author_actor_id=$actor)
                AND ($proposer IS NULL OR (proposal_actor_id=$proposer AND proposal_command_id=$proposal))
                ORDER BY state_version DESC LIMIT 100) r
            LEFT JOIN mosaic_edits e ON e.world_id=r.world_id AND e.author_actor_id=r.author_actor_id AND e.command_id=r.edit_command_id
            ORDER BY r.state_version
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$proposer", proposalActor), ("$proposal", proposalCommand));
        using var reader = command.ExecuteReader();
        while (reader.Read())
        {
            MosaicEdit? edit = reader.IsDBNull(12) ? null : new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                reader.GetInt64(12), reader.GetInt64(13), JsonSerializer.Deserialize<MosaicPatchCell[]>(reader.GetString(14), Protocol.Json)!,
                reader.GetInt64(8), reader.GetString(9), [reader.GetInt64(10), reader.GetInt64(11)]);
            reviews.Add(new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3), reader.GetString(4),
                reader.GetString(5), reader.GetString(6), reader.GetString(7), reader.GetInt64(8), reader.GetString(9),
                [reader.GetInt64(10), reader.GetInt64(11)], edit));
        }
        return reviews;
    }

    private static long MosaicRevision(SqliteConnection connection, SqliteTransaction transaction) =>
        Scalar(connection, transaction, "SELECT revision FROM mosaics WHERE world_id=$world AND activity_id='garden'", ("$world", Protocol.WorldId));

    private static object ReadMosaic(SqliteConnection connection, SqliteTransaction transaction)
    {
        var cells = new List<object>();
        using var command = Command(connection, transaction, """
            SELECT x,y,color,author_actor_id,command_id,state_version FROM mosaic_cells
            WHERE world_id=$world AND activity_id='garden' ORDER BY y,x
            """, ("$world", Protocol.WorldId));
        using (var reader = command.ExecuteReader())
            while (reader.Read())
                cells.Add(new { x = reader.GetInt64(0), y = reader.GetInt64(1), color = reader.GetString(2),
                    authorActorId = reader.IsDBNull(3) ? null : reader.GetString(3),
                    commandId = reader.IsDBNull(4) ? null : reader.GetString(4),
                    stateVersion = reader.IsDBNull(5) ? (long?)null : reader.GetInt64(5) });
        return new { activityId = "garden", width = 5, height = 5, revision = MosaicRevision(connection, transaction),
            palette = WorldScenario.MosaicPalette, cells };
    }

    private static List<MosaicEdit> ReadMosaicEdits(SqliteConnection connection, SqliteTransaction transaction, string? actor = null)
    {
        var edits = new List<MosaicEdit>();
        using var command = Command(connection, transaction, """
            SELECT activity_id,author_actor_id,command_id,visit_command_id,base_revision,revision,patch_json,state_version,painted_at_utc,x,y FROM (
              SELECT * FROM mosaic_edits WHERE world_id=$world AND ($actor IS NULL OR author_actor_id=$actor)
              ORDER BY revision DESC LIMIT $limit
            ) ORDER BY revision
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$limit", actor is null ? 50 : 100));
        using var reader = command.ExecuteReader();
        while (reader.Read())
            edits.Add(new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                reader.GetInt64(4), reader.GetInt64(5), JsonSerializer.Deserialize<MosaicPatchCell[]>(reader.GetString(6), Protocol.Json)!,
                reader.GetInt64(7), reader.GetString(8), [reader.GetInt64(9), reader.GetInt64(10)]));
        return edits;
    }

    private static List<Postcard> ReadPostcards(SqliteConnection connection, SqliteTransaction transaction, string? actor = null)
    {
        var postcards = new List<Postcard>();
        using var command = Command(connection, transaction, """
            SELECT activity_id,author_actor_id,command_id,visit_command_id,text,state_version,shared_at_utc,x,y FROM (
              SELECT activity_id,author_actor_id,command_id,visit_command_id,text,state_version,shared_at_utc,x,y FROM postcards
              WHERE world_id=$world AND ($actor IS NULL OR author_actor_id=$actor) ORDER BY state_version DESC LIMIT $limit
            ) ORDER BY state_version
            """, ("$world", Protocol.WorldId), ("$actor", actor), ("$limit", actor is null ? 50 : 100));
        using var reader = command.ExecuteReader();
        while (reader.Read())
            postcards.Add(new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                reader.GetString(4), reader.GetInt64(5), reader.GetString(6), [reader.GetInt64(7), reader.GetInt64(8)]));
        return postcards;
    }

    private static List<object> ReadVisits(SqliteConnection connection, SqliteTransaction transaction, string actor)
    {
        var visits = new List<object>();
        using var command = Command(connection, transaction, """
            SELECT activity_id,command_id,state_version,visited_at_utc,x,y FROM (
              SELECT activity_id,command_id,state_version,visited_at_utc,x,y FROM visits
              WHERE world_id=$world AND actor_id=$actor ORDER BY state_version DESC LIMIT 100
            ) ORDER BY state_version
            """, ("$world", Protocol.WorldId), ("$actor", actor));
        using var reader = command.ExecuteReader();
        while (reader.Read())
            visits.Add(new { activityId = reader.GetString(0), commandId = reader.GetString(1), stateVersion = reader.GetInt64(2),
                visitedAtUtc = reader.GetString(3), position = new[] { reader.GetInt64(4), reader.GetInt64(5) } });
        return visits;
    }

    private static State ReadState(SqliteConnection connection, SqliteTransaction transaction)
    {
        using var command = Command(connection, transaction, """
            SELECT state_version,(SELECT coalesce(max(seq),0) FROM events WHERE world_id=$world),depot_wood,issued_wood
            FROM worlds WHERE id=$world
            """, ("$world", Protocol.WorldId));
        using var reader = command.ExecuteReader();
        if (!reader.Read()) throw new InvalidOperationException("世界状态缺失");
        return new(reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2), reader.GetInt64(3));
    }

    private static Actor ReadActor(SqliteConnection connection, SqliteTransaction transaction, string actor)
    {
        using var command = Command(connection, transaction, "SELECT x,y,wood FROM residents WHERE world_id=$world AND actor_id=$actor",
            ("$world", Protocol.WorldId), ("$actor", actor));
        using var reader = command.ExecuteReader();
        if (!reader.Read()) throw new InvalidOperationException("居民状态缺失");
        return new(reader.GetDouble(0), reader.GetDouble(1), reader.GetInt64(2));
    }

    private static (string Hash, ApiReply Reply)? FindReceipt(SqliteConnection connection, SqliteTransaction transaction, string actor, string id)
    {
        using var command = Command(connection, transaction,
            "SELECT request_hash,status_code,result_json FROM receipts WHERE world_id=$world AND actor_id=$actor AND command_id=$id",
            ("$world", Protocol.WorldId), ("$actor", actor), ("$id", id));
        using var reader = command.ExecuteReader();
        return reader.Read() ? (reader.GetString(0), new(reader.GetInt32(1), reader.GetString(2))) : null;
    }

    private static void SaveReceipt(SqliteConnection connection, SqliteTransaction transaction, string actor, string id, string hash, ApiReply reply) =>
        Run(connection, transaction, "INSERT INTO receipts(world_id,actor_id,command_id,request_hash,status_code,result_json) VALUES($world,$actor,$id,$hash,$status,$json)",
            ("$world", Protocol.WorldId), ("$actor", actor), ("$id", id), ("$hash", hash), ("$status", reply.StatusCode), ("$json", reply.Json));
}
