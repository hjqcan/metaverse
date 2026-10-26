using System.Buffers;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace World.Server;

internal sealed record Identity(string OperatorId, string ActorId, string SessionId);
internal sealed record ApiError(string Code, string Message, bool Retryable = false, bool? Mutated = false);
internal sealed record ApiReply(int StatusCode, string Json, string? InstanceId = null) : IResult
{
    public ApiReply WithInstance(string? instanceId) => this with { InstanceId = instanceId };
    public IResult ToResult() => this;
    public async Task ExecuteAsync(HttpContext context)
    {
        if (InstanceId is not null) context.Response.Headers[WorldInstance.Header] = InstanceId;
        await Results.Content(Json, "application/json; charset=utf-8", statusCode: StatusCode).ExecuteAsync(context);
    }
}

internal sealed class RequestFailure(int statusCode, string code, string message, string? instanceId = null) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
    public string? InstanceId { get; } = instanceId;
}

internal static class Protocol
{
    public const string WorldId = "foundation-01";
    public const string ActorStateMode = "actor-state-v1";
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static Dictionary<string, object?> Envelope(string rulesVersion, Identity? identity, long? version = null,
        long? cursor = null, string? commandId = null, ApiError? error = null) => new()
    {
        ["schemaVersion"] = 1, ["rulesVersion"] = rulesVersion, ["stateVersion"] = version,
        ["commandId"] = commandId, ["identity"] = identity, ["eventCursor"] = cursor, ["error"] = error
    };

    public static ApiReply Reply(int status, object body) => new(status, JsonSerializer.Serialize(body, Json));
    public static ApiReply Error(string rulesVersion, int status, string code, string message, Identity? identity = null,
        long? version = null, long? cursor = null, string? commandId = null, bool retryable = false, bool? mutated = false) =>
        Reply(status, Envelope(rulesVersion, identity, version, cursor, commandId, new(code, message, retryable, mutated)));

    public static bool ValidCommandId(string id) => id.Length is >= 1 and <= 128 &&
        id.All(c => c is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or >= '0' and <= '9' or '-' or '_');

    public static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}

internal sealed record WorldAction(string Type, long Dx = 0, long Dy = 0, long Quantity = 0,
    string? RecipeId = null, long X = 0, long Y = 0, string? ActivityId = null,
    string? VisitCommandId = null, string? Text = null, long ExpectedMosaicRevision = 0,
    MosaicPatchCell[]? Patch = null, string? ProposalActorId = null, string? ProposalCommandId = null,
    string? Decision = null, string? NodeId = null, double TargetX = 0, double TargetY = 0, bool Continuous = false,
    string? RecipientActorId = null, string? Resource = null, string? SourceId = null, string? ReservationId = null,
    string? EntityId = null, string? ReplyToNoteId = null, long CapabilityVersion = 0, long ExpectedCanvasRevision = 0,
    string? ToolId = null, string? PlotId = null, string? PlantId = null)
{
    public object Canonical => Type switch
    {
        "build_workshop" => new { type = Type, capabilityVersion = CapabilityVersion, recipeId = RecipeId,
            at = new[] { TargetX, TargetY }, toolId = ToolId },
        "craft_forestry_tool" or "craft_tool" => new { type = Type, capabilityVersion = CapabilityVersion, entityId = EntityId, recipeId = RecipeId },
        "deposit_wood" or "withdraw_wood" => new { type = Type, capabilityVersion = CapabilityVersion, entityId = EntityId, quantity = Quantity },
        "reserve_forest" => new { type = Type, capabilityVersion = CapabilityVersion },
        "cancel_forest_reservation" => new { type = Type, capabilityVersion = CapabilityVersion, reservationId = ReservationId },
        "collect_seed" => new { type = Type, capabilityVersion = CapabilityVersion, sourceId = SourceId, reservationId = ReservationId },
        "plant_tree" => new { type = Type, capabilityVersion = CapabilityVersion, plotId = PlotId, reservationId = ReservationId },
        "harvest_tree" => new { type = Type, capabilityVersion = CapabilityVersion, plantId = PlantId, reservationId = ReservationId, toolId = ToolId },
        "move" => new { type = Type, dx = Dx, dy = Dy },
        "walk" => new { type = Type, to = new[] { TargetX, TargetY } },
        "build" when Continuous => new { type = Type, recipeId = RecipeId, at = new[] { TargetX, TargetY } },
        "claim" => new { type = Type, quantity = Quantity },
        "gather" => new { type = Type, nodeId = NodeId },
        "transfer" => new { type = Type, recipientActorId = RecipientActorId, resource = Resource, quantity = Quantity },
        "reserve_material" => new { type = Type, sourceId = SourceId },
        "cancel_reservation" or "harvest_material" => new { type = Type, reservationId = ReservationId },
        "append_entity_note" => new { type = Type, entityId = EntityId, text = Text, replyToNoteId = ReplyToNoteId },
        "paint_entity_canvas" => new { type = Type, entityId = EntityId, capabilityVersion = CapabilityVersion,
            expectedCanvasRevision = ExpectedCanvasRevision, patch = Patch },
        "visit" => new { type = Type, activityId = ActivityId },
        "postcard" => new { type = Type, activityId = ActivityId, visitCommandId = VisitCommandId, text = Text },
        "mosaic" => new { type = Type, activityId = ActivityId, visitCommandId = VisitCommandId,
            expectedMosaicRevision = ExpectedMosaicRevision, patch = Patch },
        "mosaic_propose" => new { type = Type, activityId = ActivityId, visitCommandId = VisitCommandId,
            expectedMosaicRevision = ExpectedMosaicRevision, patch = Patch, text = Text },
        "mosaic_review" => new { type = Type, activityId = ActivityId, visitCommandId = VisitCommandId,
            proposalActorId = ProposalActorId, proposalCommandId = ProposalCommandId, decision = Decision, text = Text },
        _ => new { type = Type, recipeId = RecipeId, at = new[] { X, Y } }
    };
}

internal sealed record MosaicPatchCell(long X, long Y, string Color);

internal sealed record WorldCommand(int SchemaVersion, string RulesVersion, string CommandId,
    long ExpectedStateVersion, WorldAction Action, string? PreconditionMode = null)
{
    // Re-serialize only typed semantic fields in fixed order, never raw client JSON.
    // The old branch is deliberately unchanged: persisted old hashes still match.
    public string RequestHash => Protocol.Hash(JsonSerializer.Serialize(PreconditionMode is null
        ? (object)new { schemaVersion = SchemaVersion, rulesVersion = RulesVersion,
            expectedStateVersion = ExpectedStateVersion, action = Action.Canonical }
        : new { schemaVersion = SchemaVersion, rulesVersion = RulesVersion,
            expectedStateVersion = ExpectedStateVersion, preconditionMode = PreconditionMode,
            action = Action.Canonical }, Protocol.Json));

    public static async Task<WorldCommand> Read(HttpRequest request, WorldScenario scenario)
    {
        if (!request.HasJsonContentType()) Invalid("请求必须使用 JSON");
        using var buffer = new MemoryStream();
        var chunk = new byte[4096];
        while (true)
        {
            var read = await request.Body.ReadAsync(chunk, request.HttpContext.RequestAborted);
            if (read == 0) break;
            if (buffer.Length + read > 16384) Invalid("请求内容过大");
            buffer.Write(chunk, 0, read);
        }
        JsonDocument document;
        try { document = JsonDocument.Parse(buffer.ToArray(), new JsonDocumentOptions { MaxDepth = 32 }); }
        catch (JsonException) { throw new RequestFailure(400, "INVALID_REQUEST", "JSON 格式无效"); }
        using (document)
        {
            var root = document.RootElement;
            RejectIdentity(root);
            var hasMode = root.ValueKind == JsonValueKind.Object && root.TryGetProperty("preconditionMode", out _);
            if (hasMode)
                Fields(root, "schemaVersion", "rulesVersion", "commandId", "expectedStateVersion", "preconditionMode", "action");
            else Fields(root, "schemaVersion", "rulesVersion", "commandId", "expectedStateVersion", "action");
            var mode = hasMode ? String(root.GetProperty("preconditionMode")) : null;
            if (mode is not null && mode != Protocol.ActorStateMode) Invalid("不支持的动作前置条件模式");
            var schema = Integer(root.GetProperty("schemaVersion"));
            if (schema != 1) Invalid("不支持的接口版本");
            var rules = String(root.GetProperty("rulesVersion"));
            var id = String(root.GetProperty("commandId"));
            if (!Protocol.ValidCommandId(id)) Invalid("命令 ID 格式无效");
            var version = Integer(root.GetProperty("expectedStateVersion"));
            if (version < 0) Invalid("世界版本必须为非负整数");
            var action = root.GetProperty("action");
            if (action.ValueKind != JsonValueKind.Object || !action.TryGetProperty("type", out var typeElement))
                Invalid("缺少动作类型");
            var type = String(action.GetProperty("type"));
            WorldAction parsed;
            switch (type)
            {
                case "reserve_forest":
                    Fields(action, "type", "capabilityVersion");
                    if (Integer(action.GetProperty("capabilityVersion")) != 1) Invalid("林业能力版本无效");
                    parsed = new(type, CapabilityVersion: 1); break;
                case "cancel_forest_reservation":
                case "collect_seed":
                case "plant_tree":
                case "harvest_tree":
                    var forestFields = type switch {
                        "cancel_forest_reservation" => new[] { "type", "capabilityVersion", "reservationId" },
                        "collect_seed" => new[] { "type", "capabilityVersion", "sourceId", "reservationId" },
                        "plant_tree" => new[] { "type", "capabilityVersion", "plotId", "reservationId" },
                        _ => new[] { "type", "capabilityVersion", "plantId", "reservationId", "toolId" } };
                    Fields(action, forestFields);
                    if (Integer(action.GetProperty("capabilityVersion")) != 1) Invalid("林业能力版本无效");
                    foreach (var field in forestFields.Where(f => f.EndsWith("Id")))
                        if (!Protocol.ValidCommandId(String(action.GetProperty(field)))) Invalid("林业原目标ID无效");
                    string? ForestId(string field) => action.TryGetProperty(field, out var value) ? String(value) : null;
                    parsed = new(type, CapabilityVersion: 1, ReservationId: ForestId("reservationId"), SourceId: ForestId("sourceId"),
                        PlotId: ForestId("plotId"), PlantId: ForestId("plantId"), ToolId: ForestId("toolId")); break;
                case "build_workshop":
                    Fields(action, "type", "capabilityVersion", "recipeId", "at", "toolId");
                    var workshopRecipe = String(action.GetProperty("recipeId"));
                    var workshopAt = action.GetProperty("at");
                    var workshopTool = action.GetProperty("toolId");
                    var toolId = workshopTool.ValueKind == JsonValueKind.Null ? null : String(workshopTool);
                    if (Integer(action.GetProperty("capabilityVersion")) != 1 || workshopRecipe is not ("workbench.v1" or "wooden_chest.v1")
                        || workshopAt.ValueKind != JsonValueKind.Array || workshopAt.GetArrayLength() != 2
                        || toolId is not null && !Protocol.ValidCommandId(toolId) || workshopRecipe == "workbench.v1" && toolId is not null)
                        Invalid("工作坊建造参数无效");
                    parsed = new(type, CapabilityVersion: 1, RecipeId: workshopRecipe, TargetX: Coordinate(workshopAt[0]),
                        TargetY: Coordinate(workshopAt[1]), ToolId: toolId);
                    break;
                case "craft_forestry_tool":
                case "craft_tool":
                    Fields(action, "type", "capabilityVersion", "entityId", "recipeId");
                    var benchId = String(action.GetProperty("entityId"));
                    if (Integer(action.GetProperty("capabilityVersion")) != 1 || !Protocol.ValidCommandId(benchId)
                        || String(action.GetProperty("recipeId")) != (type == "craft_tool" ? "wooden_mallet.v1" : "wooden_axe.v1")) Invalid("工具制作参数无效");
                    parsed = new(type, CapabilityVersion: 1, EntityId: benchId, RecipeId: type == "craft_tool" ? "wooden_mallet.v1" : "wooden_axe.v1");
                    break;
                case "deposit_wood":
                case "withdraw_wood":
                    Fields(action, "type", "capabilityVersion", "entityId", "quantity");
                    var chestId = String(action.GetProperty("entityId"));
                    var chestQuantity = Integer(action.GetProperty("quantity"));
                    if (Integer(action.GetProperty("capabilityVersion")) != 1 || !Protocol.ValidCommandId(chestId)
                        || chestQuantity is < 1 or > 12) Invalid("箱子存取参数无效");
                    parsed = new(type, CapabilityVersion: 1, EntityId: chestId, Quantity: chestQuantity);
                    break;
                case "paint_entity_canvas":
                    Fields(action, "type", "entityId", "capabilityVersion", "expectedCanvasRevision", "patch");
                    var canvasEntity = String(action.GetProperty("entityId"));
                    var canvasVersion = Integer(action.GetProperty("capabilityVersion"));
                    var canvasRevision = Integer(action.GetProperty("expectedCanvasRevision"));
                    if (!Protocol.ValidCommandId(canvasEntity) || canvasVersion != 1 || canvasRevision < 0)
                        Invalid("地画目标、能力版本或绘制基准无效");
                    parsed = new(type, EntityId: canvasEntity, CapabilityVersion: canvasVersion,
                        ExpectedCanvasRevision: canvasRevision, Patch: MosaicPatch(action.GetProperty("patch")));
                    break;
                case "append_entity_note":
                    Fields(action, "type", "entityId", "text", "replyToNoteId");
                    var noteEntity = String(action.GetProperty("entityId"));
                    var noteReference = action.GetProperty("replyToNoteId");
                    var replyToNote = noteReference.ValueKind == JsonValueKind.Null ? null : String(noteReference);
                    if (!Protocol.ValidCommandId(noteEntity) || replyToNote is not null && !Protocol.ValidCommandId(replyToNote))
                        Invalid("手记目标或引用ID格式无效");
                    parsed = new(type, EntityId: noteEntity, Text: PostcardText(action.GetProperty("text")), ReplyToNoteId: replyToNote);
                    break;
                case "reserve_material":
                    Fields(action, "type", "sourceId");
                    var sourceId = String(action.GetProperty("sourceId"));
                    if (!Protocol.ValidCommandId(sourceId)) Invalid("来源ID格式无效");
                    parsed = new(type, SourceId: sourceId);
                    break;
                case "cancel_reservation":
                case "harvest_material":
                    Fields(action, "type", "reservationId");
                    var reservationId = String(action.GetProperty("reservationId"));
                    if (!Protocol.ValidCommandId(reservationId)) Invalid("预约ID格式无效");
                    parsed = new(type, ReservationId: reservationId);
                    break;
                case "walk":
                    if (!scenario.SupportsContinuous) Invalid("当前世界不支持连续行走");
                    Fields(action, "type", "to");
                    var to = action.GetProperty("to");
                    if (to.ValueKind != JsonValueKind.Array || to.GetArrayLength() != 2) Invalid("目标必须为两个有限实数");
                    parsed = new(type, TargetX: Coordinate(to[0]), TargetY: Coordinate(to[1]), Continuous: true);
                    break;
                case "move":
                    Fields(action, "type", "dx", "dy");
                    parsed = new(type, Dx: Integer(action.GetProperty("dx")), Dy: Integer(action.GetProperty("dy")));
                    break;
                case "claim":
                    Fields(action, "type", "quantity");
                    var quantity = Integer(action.GetProperty("quantity"));
                    if (quantity is < 1 or > 12) Invalid("领取数量必须为 1 至 12 的整数");
                    parsed = new(type, Quantity: quantity);
                    break;
                case "gather":
                    Fields(action, "type", "nodeId");
                    var nodeId = String(action.GetProperty("nodeId"));
                    if (!Protocol.ValidCommandId(nodeId)) Invalid("资源节点 ID 格式无效");
                    parsed = new(type, NodeId: nodeId);
                    break;
                case "build":
                    Fields(action, "type", "recipeId", "at");
                    var recipe = String(action.GetProperty("recipeId"));
                    if (!scenario.SupportsRecipe(recipe)) Invalid("当前世界不支持此建造配方");
                    var at = action.GetProperty("at");
                    if (at.ValueKind != JsonValueKind.Array || at.GetArrayLength() != 2) Invalid("目标必须为两个整数坐标");
                    parsed = scenario.SupportsContinuous
                        ? new(type, RecipeId: recipe, TargetX: Coordinate(at[0]), TargetY: Coordinate(at[1]), Continuous: true)
                        : new(type, RecipeId: recipe, X: Integer(at[0]), Y: Integer(at[1]));
                    break;
                case "transfer":
                    Fields(action, "type", "recipientActorId", "resource", "quantity");
                    var recipient = String(action.GetProperty("recipientActorId"));
                    var resource = String(action.GetProperty("resource"));
                    var transferQuantity = Integer(action.GetProperty("quantity"));
                    if (!Protocol.ValidCommandId(recipient)) Invalid("收件人 ID 格式无效");
                    if (resource != "wood") Invalid("只能转让木材");
                    if (transferQuantity is < 1 or > 12) Invalid("转让数量必须为 1 至 12 的整数");
                    parsed = new(type, Quantity: transferQuantity, RecipientActorId: recipient, Resource: resource);
                    break;
                case "visit":
                    Fields(action, "type", "activityId");
                    parsed = new(type, ActivityId: String(action.GetProperty("activityId")));
                    break;
                case "postcard":
                    Fields(action, "type", "activityId", "visitCommandId", "text");
                    var activityId = String(action.GetProperty("activityId"));
                    var visitCommandId = String(action.GetProperty("visitCommandId"));
                    if (!Protocol.ValidCommandId(visitCommandId)) Invalid("到访命令 ID 格式无效");
                    parsed = new(type, ActivityId: activityId, VisitCommandId: visitCommandId,
                        Text: PostcardText(action.GetProperty("text")));
                    break;
                case "mosaic":
                case "mosaic_propose":
                    if (type == "mosaic_propose")
                        Fields(action, "type", "activityId", "visitCommandId", "expectedMosaicRevision", "patch", "text");
                    else
                        Fields(action, "type", "activityId", "visitCommandId", "expectedMosaicRevision", "patch");
                    var mosaicVisit = String(action.GetProperty("visitCommandId"));
                    if (!Protocol.ValidCommandId(mosaicVisit)) Invalid("到访命令 ID 格式无效");
                    var revision = Integer(action.GetProperty("expectedMosaicRevision"));
                    if (revision < 0) Invalid("画布版本必须为非负整数");
                    parsed = new(type, ActivityId: String(action.GetProperty("activityId")), VisitCommandId: mosaicVisit,
                        ExpectedMosaicRevision: revision, Patch: MosaicPatch(action.GetProperty("patch")),
                        Text: type == "mosaic_propose" ? PostcardText(action.GetProperty("text")) : null);
                    break;
                case "mosaic_review":
                    Fields(action, "type", "activityId", "visitCommandId", "proposalActorId", "proposalCommandId", "decision", "text");
                    var reviewVisit = String(action.GetProperty("visitCommandId"));
                    var proposalCommand = String(action.GetProperty("proposalCommandId"));
                    if (!Protocol.ValidCommandId(reviewVisit) || !Protocol.ValidCommandId(proposalCommand))
                        Invalid("到访或提议命令 ID 格式无效");
                    var decision = String(action.GetProperty("decision"));
                    if (decision is not ("accept" or "reject")) Invalid("审阅决定只能为 accept 或 reject");
                    parsed = new(type, ActivityId: String(action.GetProperty("activityId")), VisitCommandId: reviewVisit,
                        ProposalActorId: String(action.GetProperty("proposalActorId")), ProposalCommandId: proposalCommand,
                        Decision: decision, Text: PostcardText(action.GetProperty("text")));
                    break;
                default:
                    throw new RequestFailure(400, "INVALID_REQUEST", "不支持的动作类型");
            }
            return new((int)schema, rules, id, version, parsed, mode);
        }
    }

    private static void RejectIdentity(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
            foreach (var property in element.EnumerateObject())
            {
                if (new[] { "actorId", "operatorId", "sessionId", "identity" }.Contains(property.Name, StringComparer.OrdinalIgnoreCase))
                    throw new RequestFailure(403, "IDENTITY_OVERRIDE", "身份只能由认证会话确定");
                RejectIdentity(property.Value);
            }
        else if (element.ValueKind == JsonValueKind.Array)
            foreach (var item in element.EnumerateArray()) RejectIdentity(item);
    }

    private static void Fields(JsonElement element, params string[] names)
    {
        if (element.ValueKind != JsonValueKind.Object) Invalid("请求结构必须为对象");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in element.EnumerateObject())
            if (!names.Contains(property.Name, StringComparer.Ordinal) || !seen.Add(property.Name))
                Invalid("请求包含未知或重复字段");
        if (seen.Count != names.Length) Invalid("请求缺少必填字段");
    }

    private static string String(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.String) Invalid("字段必须为非空字符串");
        string? value;
        try { value = element.GetString(); }
        catch (InvalidOperationException) { throw new RequestFailure(400, "INVALID_REQUEST", "字符串包含无效 Unicode"); }
        if (string.IsNullOrEmpty(value)) Invalid("字段必须为非空字符串");
        return value!;
    }

    private static string PostcardText(JsonElement element)
    {
        var text = String(element);
        var remaining = text.AsSpan();
        var count = 0;
        var hasContent = false;
        while (!remaining.IsEmpty)
        {
            if (Rune.DecodeFromUtf16(remaining, out var rune, out var consumed) != OperationStatus.Done)
                Invalid("手记不能包含孤立代理项");
            if (Rune.GetUnicodeCategory(rune) == UnicodeCategory.Control)
                Invalid("手记不能包含控制字符");
            if (++count > 160) Invalid("手记最多 160 个 Unicode 标量值");
            hasContent |= !Rune.IsWhiteSpace(rune);
            remaining = remaining[consumed..];
        }
        if (!hasContent) Invalid("手记不能全为空白");
        return text;
    }

    private static MosaicPatchCell[] MosaicPatch(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Array || element.GetArrayLength() is < 1 or > 8)
            Invalid("画布修改必须包含 1 至 8 格");
        var cells = new List<MosaicPatchCell>();
        var positions = new HashSet<(long X, long Y)>();
        foreach (var cell in element.EnumerateArray())
        {
            Fields(cell, "x", "y", "color");
            var x = Integer(cell.GetProperty("x"));
            var y = Integer(cell.GetProperty("y"));
            var color = String(cell.GetProperty("color"));
            if (x is < 0 or > 4 || y is < 0 or > 4 || !positions.Add((x, y)))
                Invalid("画布坐标必须为 0 至 4 且不得重复");
            if (!WorldScenario.MosaicPalette.Any(candidate => candidate.Id == color))
                Invalid("画布颜色必须使用固定调色板 ID");
            cells.Add(new(x, y, color));
        }
        return cells.OrderBy(cell => cell.Y).ThenBy(cell => cell.X).ToArray();
    }

    private static double Coordinate(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Number || !element.TryGetDouble(out var value) || !double.IsFinite(value) || Math.Abs(value) > 1000000)
            throw new RequestFailure(400, "INVALID_REQUEST", "坐标必须为有限实数，绝对值不超过一百万");
        return value;
    }

    private static long Integer(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Number || !element.TryGetInt64(out var value))
            throw new RequestFailure(400, "INVALID_REQUEST", "字段必须为 64 位整数");
        return value;
    }

    private static void Invalid(string message) => throw new RequestFailure(400, "INVALID_REQUEST", message);
}
