using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed partial class WorldService
{
    private const double TransferReach = 1.6;

    private (int Status, ApiError Error)? ValidateTransfer(SqliteConnection c, SqliteTransaction t,
        WorldAction action, Actor sender, string senderId)
    {
        if (!Scenario.SupportsTransfer) return (422, new("ACTION_UNAVAILABLE", "当前世界不支持木材转让"));
        if (action.RecipientActorId == senderId) return (422, new("SELF_TRANSFER", "收件人必须是另一位居民"));
        if (Scalar(c, t, "SELECT count(*) FROM residents WHERE world_id=$world AND actor_id=$actor",
            ("$world", Protocol.WorldId), ("$actor", action.RecipientActorId)) != 1)
            return (404, new("RESIDENT_NOT_FOUND", "收件人不存在"));
        var recipient = ReadActor(c, t, action.RecipientActorId!);
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t);
        if (ContinuousWorld.Distance(sender.X, sender.Y, recipient.X, recipient.Y) > TransferReach ||
            !ContinuousWorld.Walkable(sender.X, sender.Y, trees, entities, ForestryRules.Obstacles(c, t)) ||
            !ContinuousWorld.Walkable(recipient.X, recipient.Y, trees, entities, ForestryRules.Obstacles(c, t)) ||
            ContinuousWorld.Sweep(sender.X, sender.Y, recipient.X, recipient.Y, trees, entities, ForestryRules.Obstacles(c, t)).Blocked)
            return (422, new("TRANSFER_UNREACHABLE", "请到收件人 1.6 米内，且双方之间没有障碍"));
        if (sender.Wood < action.Quantity) return (422, new("INSUFFICIENT_RESOURCE", "本人木材不足，不能完成转让"));
        if (recipient.Wood + action.Quantity > 12) return (422, new("RECIPIENT_CAPACITY_EXCEEDED", "收件人库存容量不足"));
        return null;
    }

    private static void BindTransfers(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t, string actor)
    {
        body["materialTransfer"] = new { version = 1, resource = "wood", maxQuantity = 12,
            reach = TransferReach, recipientConfirmation = false };
        const int limit = 20;
        var items = new List<JsonElement>();
        using (var command = Command(c, t, """
            SELECT event_json FROM events WHERE world_id=$world AND json_extract(event_json,'$.type')='woodTransferred'
                AND (json_extract(event_json,'$.actorId')=$actor OR json_extract(event_json,'$.recipientActorId')=$actor)
            ORDER BY seq DESC LIMIT 21
            """, ("$world", Protocol.WorldId), ("$actor", actor)))
        using (var reader = command.ExecuteReader())
            while (reader.Read()) items.Add(JsonSerializer.Deserialize<JsonElement>(reader.GetString(0)));
        var truncated = items.Count > limit;
        if (truncated) items.RemoveAt(limit);
        items.Reverse();
        // These are immutable public events, not a second set of private command receipts.
        body["recentTransfers"] = new { items, limit, truncated };
    }
}
