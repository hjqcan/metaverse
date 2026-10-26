namespace World.Server;

internal sealed record EntryBridge(string EntityId, string OwnerActorId, long[] Position);

// A read-only view of present access, never a technology unlock or resource grant.
internal static class EntryGuide
{
    public static object Build(WorldScenario scenario, long version, string actorId, long x, long y,
        long publicWood, long ownWood, IReadOnlyList<EntryBridge> bridges, IReadOnlyList<WorldResourceNode> resources)
    {
        var start = (X: x, Y: y);
        var bridgeAt = bridges.ToDictionary(b => (X: b.Position[0], Y: b.Position[1]));
        var liveTrees = resources.Where(n => n.RemainingWood > 0).Select(n => ((long)n.Position[0], (long)n.Position[1])).ToHashSet();
        var previous = new Dictionary<(long X, long Y), (long X, long Y)> { [start] = start };
        var queue = new Queue<(long X, long Y)>();
        queue.Enqueue(start);
        (long X, long Y)[] directions = [(1, 0), (0, 1), (-1, 0), (0, -1)];
        while (queue.TryDequeue(out var current))
            foreach (var direction in directions)
            {
                var next = (X: current.X + direction.X, Y: current.Y + direction.Y);
                if (!WorldScenario.InBounds(next.X, next.Y) || WorldScenario.IsWall(next.X, next.Y) || liveTrees.Contains(next)
                    || scenario.IsWater(next.X, next.Y) && !bridgeAt.ContainsKey(next) || previous.ContainsKey(next)) continue;
                previous[next] = current;
                queue.Enqueue(next);
            }

        object Place(string id, string label, long targetX, long targetY, string? activityId)
        {
            var target = (X: targetX, Y: targetY);
            var reachable = previous.ContainsKey(target);
            var route = new List<long[]>();
            if (reachable)
                for (var cursor = target; cursor != start; cursor = previous[cursor])
                    route.Add([cursor.X, cursor.Y]);
            route.Reverse();
            var bridgeIds = route.Where(p => bridgeAt.ContainsKey((p[0], p[1])))
                .Select(p => bridgeAt[(p[0], p[1])].EntityId).Distinct().ToArray();
            return new { id, label, position = new[] { targetX, targetY }, activityId, reachable,
                walkingSteps = reachable ? (int?)route.Count : null, route, bridgeEntityIds = bridgeIds };
        }

        var places = scenario.SupportsActivities
            ? scenario.ActivityCatalog.Select(a => Place(a.Id, a.Label, a.X, a.Y, a.Id)).ToArray()
            : new[] { Place("goal", "目标地", scenario.GoalX, 1, null) };
        return new
        {
            version = 1, stateVersion = version, actorId, position = new[] { x, y },
            sharedBridges = bridges, places,
            materials = scenario.SupportsGathering
                ? (object)new { publicWood, ownWood, depotPosition = new[] { 1, 1 }, depotAvailable = false,
                    wildWood = resources.Sum(n => n.RemainingWood) }
                : new { publicWood, ownWood, depotPosition = new[] { 1, 1 } },
            participation = new { walkWoodCost = 0, visitSupported = scenario.SupportsActivities,
                postcardSupported = scenario.SupportsPostcards, mosaicSupported = scenario.SupportsMosaic,
                foreignMosaicNeedsConsent = scenario.SupportsMosaicConsent }
        };
    }
}
