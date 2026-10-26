using System.Globalization;
using System.Net;
using Microsoft.Data.Sqlite;
using World.Server;

SQLitePCL.Batteries.Init();
var configuration = ServerConfiguration.Load();
var database = new WorldDatabase(configuration);
if (args.Length > 0)
{
    try
    {
        if (args.Length == 3 && args[0] == "adopt-workshop" && args[1] == "--instance")
        {
            Console.WriteLine(database.AdoptWorkshop(args[2]) ? "工作坊能力已在原实例采用。" : "工作坊已采用，原历史保持。");
            return 0;
        }
        if (args.Length == 5 && args[0] == "adopt-entity-canvas" && args[1] == "--instance" && args[3] == "--entity")
        {
            Console.WriteLine(database.AdoptEntityCanvas(args[2], args[4]) ? "地画已在原平台开启。" : "地画已采用，原图和历史保持。");
            return 0;
        }
        if (args.Length == 3 && args[0] == "adopt-continuous-material-source" && args[1] == "--instance")
        {
            Console.WriteLine(database.AdoptContinuousMaterialSource(args[2]) ? "持续材料政策已在原实例采用。" : "持续材料政策已采用，原进度保持。");
            return 0;
        }
        if (args.Length == 5 && args[0] == "adopt-entity-notes" && args[1] == "--instance" && args[3] == "--entity")
        {
            Console.WriteLine(database.AdoptEntityNotes(args[2], args[4]) ? "共同手记已在原桥开启。" : "共同手记已采用，原内容和额度保持。");
            return 0;
        }
        if (args.Length == 3 && args[0] == "enable-material-source" && args[1] == "--instance")
        {
            Console.WriteLine(database.EnableMaterialSource(args[2]) ? "材料来源已在原实例开启。" : "材料来源已经开启，原进度保持。");
            return 0;
        }
        if (args.Length != 7 || args[0] != "issue-session")
            throw new ArgumentException("用法：issue-session --actor a1 --ttl-seconds 86400 --output <path>");
        var options = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var i = 1; i < args.Length; i += 2)
            if (args[i] is not ("--actor" or "--ttl-seconds" or "--output") || !options.TryAdd(args[i], args[i + 1]))
                throw new ArgumentException("管理命令参数无效");
        if (!options.TryGetValue("--actor", out var actor) || !options.TryGetValue("--ttl-seconds", out var rawTtl) ||
            !options.TryGetValue("--output", out var output) ||
            !long.TryParse(rawTtl, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var ttl))
            throw new ArgumentException("管理命令参数无效");
        var outputPath = Path.GetFullPath(output);
        if (new[] { database.Path, database.Path + "-wal", database.Path + "-shm", Path.Combine(configuration.DataDirectory, "access.json") }.Contains(outputPath, StringComparer.Ordinal))
            throw new ArgumentException("输出文件不能覆盖数据库或初始 access.json");
        database.IssueSession(actor, ttl, outputPath);
        Console.WriteLine("会话已替换，凭据已写入指定文件。");
        return 0;
    }
    catch (Exception ex) when (ex is ArgumentException or IOException or SqliteException or InvalidOperationException)
    {
        Console.Error.WriteLine("离线管理失败：" + ex.GetType().Name);
        return 1;
    }
}

database.Initialize();
using var materialClock = database.Scenario.SupportsMaterialAccess ? new MaterialServiceClock(database) : null;
var service = new WorldService(database, configuration, materialClock);
var builder = WebApplication.CreateBuilder(new WebApplicationOptions
{
    Args = [], ContentRootPath = configuration.ContentRoot,
    WebRootPath = Path.Combine(configuration.ContentRoot, "wwwroot")
});
builder.Services.AddSingleton(service);
if (database.Scenario.SupportsMaterialAccess) builder.Services.AddHostedService<MaterialClockWorker>();
builder.WebHost.ConfigureKestrel(options =>
{
    options.AddServerHeader = false;
    options.Limits.MaxRequestBodySize = 16384;
    var uri = new Uri(configuration.Url);
    if (uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase)) options.ListenLocalhost(uri.Port);
    else options.Listen(IPAddress.Parse(uri.DnsSafeHost), uri.Port);
});
var app = builder.Build();

app.Use(async (context, next) =>
{
    try
    {
        if (context.Request.Path.StartsWithSegments("/v1"))
        {
            context.Response.Headers.CacheControl = "no-store";
            var authorization = context.Request.Headers.Authorization;
            if (authorization.Count != 1 || !authorization[0]!.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
                throw new RequestFailure(401, "UNAUTHORIZED", "请提供有效的 Bearer 会话令牌");
            var token = authorization[0]![7..];
            if (token.Length is < 1 or > 512 || token.Any(char.IsWhiteSpace))
                throw new RequestFailure(401, "UNAUTHORIZED", "会话令牌格式无效");
            var hash = Protocol.Hash(token);
            context.Items["tokenHash"] = hash;
            context.Items["identity"] = database.Authenticate(hash);
            // Covers authenticated parse errors too. World operations replace this
            // with the identity read in their own transaction before returning.
            if (database.InstanceId is not null) context.Response.Headers[WorldInstance.Header] = database.InstanceId;
        }
        await next(context);
    }
    catch (RequestFailure failure)
    {
        if (failure.StatusCode == 401) context.Response.Headers.WWWAuthenticate = "Bearer";
        await Protocol.Error(database.Scenario.RulesVersion, failure.StatusCode, failure.Code, failure.Message,
            failure.StatusCode == 401 ? null : context.Items["identity"] as Identity).WithInstance(failure.InstanceId).ToResult().ExecuteAsync(context);
    }
    catch (BadHttpRequestException)
    {
        await Protocol.Error(database.Scenario.RulesVersion, 400, "INVALID_REQUEST", "请求内容无效或过大", context.Items["identity"] as Identity).ToResult().ExecuteAsync(context);
    }
    catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested) { }
    catch (Exception failure) when (failure is SqliteException or IOException or InjectedFailure or OverflowException or InvalidOperationException)
    {
        // Do not log request bodies, authorization, SQL parameters or exception content containing data.
        app.Logger.LogWarning("World request could not complete ({FailureType})", failure.GetType().Name);
        await Protocol.Error(database.Scenario.RulesVersion, 503, "SERVICE_UNAVAILABLE", "服务暂时无法确认结果，请查询或原样重试", retryable: true, mutated: null).ToResult().ExecuteAsync(context);
    }
});
// The historical browser board speaks r1-r7. The continuous world uses the native client.
if (database.Scenario.SupportsContinuous)
    app.Use(async (context, next) =>
    {
        if (context.Request.Path is { Value: "/" or "/index.html" })
        {
            context.Response.ContentType = "text/html; charset=utf-8";
            var nativeCommand = database.Scenario.SupportsMaterialAccess ? "npm run start:godot:material-access"
                : database.Scenario.SupportsTransfer ? "npm run start:godot:cooperation" : "npm run start:godot";
            var cooperation = database.Scenario.SupportsTransfer ? "<p>走近另一位居民，选择「赠送木材」，确认收件人与数量后交付。</p>" : "";
            await context.Response.WriteAsync($$"""
                <!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
                <title>荒野 · 连续世界</title>
                <style>body{margin:12vh auto;padding:24px;max-width:620px;background:#17271f;color:#e9e8d5;font:18px/1.8 sans-serif}h1{font-size:34px}code{display:block;padding:18px;background:#294032;border-radius:8px;color:#e4c98e}a{color:#bbd3ad}</style>
                <h1>荒野 · 连续世界</h1><p>河谷、树木与最初的居民。使用 Godot 客户端进入3D场景，自由行走、采集木材并建造。</p>
                <p>在项目目录运行：</p><code>{{nativeCommand}}</code>
                <p>WASD 行走 · E 采集 · 1 / 2 建造 · 点击地面前往</p>
                {{cooperation}}
                <p><a href="/resident.html">查看居民任务报告</a></p></html>
                """);
            return;
        }
        await next(context);
    });
app.UseDefaultFiles();
app.UseStaticFiles();
// Resolve the catch-all only after static files; otherwise its endpoint suppresses static serving.
app.UseRouting();

app.MapGet("/healthz", () => Results.Json(new { status = "ok", worldId = Protocol.WorldId, sqliteVersion = database.SqliteVersion() }, Protocol.Json));
app.MapDelete("/v1/session", (HttpContext context) =>
{
    var instance = service.Revoke(TokenHash(context), WorldInstance.ReadHeader(context.Request));
    if (instance is not null) context.Response.Headers[WorldInstance.Header] = instance;
    return Results.NoContent();
});
app.MapGet("/v1/worlds/{worldId}/observation", (string worldId, HttpContext context) =>
{
    RequireWorld(worldId);
    return service.Observe(TokenHash(context), WorldInstance.ReadHeader(context.Request),
        context.Request.Headers[WorkshopRules.Header].ToString().Split(',', StringSplitOptions.TrimEntries).Contains(WorkshopRules.Capability)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/workshop/actions/{authorActorId}/{commandId}",
    (string worldId, string authorActorId, string commandId, HttpContext context) =>
{
    RequireWorld(worldId);
    if (context.Request.Query.Count != 0 || !Protocol.ValidCommandId(authorActorId) || !Protocol.ValidCommandId(commandId))
        throw new RequestFailure(400, "INVALID_REQUEST", "工作坊原记录定位字段无效或含有查询参数");
    return service.WorkshopActionDetail(TokenHash(context), authorActorId, commandId, WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/entities/{entityId}/canvas/edits/{authorActorId}/{commandId}",
    (string worldId, string entityId, string authorActorId, string commandId, HttpContext context) =>
{
    RequireWorld(worldId);
    if (context.Request.Query.Count != 0 || !Protocol.ValidCommandId(entityId) || !Protocol.ValidCommandId(authorActorId) || !Protocol.ValidCommandId(commandId))
        throw new RequestFailure(400, "INVALID_REQUEST", "地画原记录定位字段无效或含有查询参数");
    return service.EntityCanvasEditDetail(TokenHash(context), entityId, authorActorId, commandId, WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/mosaic-proposals", (string worldId, HttpContext context) =>
{
    RequireWorld(worldId);
    return service.MosaicProposalInbox(TokenHash(context), ReadMosaicInboxQuery(context.Request.Query), WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/mosaic-proposals/{proposalActorId}/{proposalCommandId}",
    (string worldId, string proposalActorId, string proposalCommandId, HttpContext context) =>
{
    RequireWorld(worldId);
    if (context.Request.Query.Count != 0 || !Protocol.ValidCommandId(proposalActorId) || !Protocol.ValidCommandId(proposalCommandId))
        throw new RequestFailure(400, "INVALID_REQUEST", "提议定位字段无效或含有查询参数");
    return service.MosaicProposalDetail(TokenHash(context), proposalActorId, proposalCommandId, WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/events", (string worldId, HttpContext context) =>
{
    RequireWorld(worldId);
    var query = context.Request.Query;
    if (query.Count != 1 || !query.TryGetValue("after", out var values) || values.Count != 1 ||
        string.IsNullOrEmpty(values[0]) || !values[0]!.All(c => c is >= '0' and <= '9') ||
        !long.TryParse(values[0], NumberStyles.None, CultureInfo.InvariantCulture, out var after))
        throw new RequestFailure(400, "INVALID_REQUEST", "after 必须为非负整数游标");
    return service.Events(TokenHash(context), after, WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapGet("/v1/worlds/{worldId}/commands/{id}", (string worldId, string id, HttpContext context) =>
{
    RequireWorld(worldId);
    if (!Protocol.ValidCommandId(id)) throw new RequestFailure(400, "INVALID_REQUEST", "命令 ID 格式无效");
    return service.Receipt(TokenHash(context), id, WorldInstance.ReadHeader(context.Request)).ToResult();
});
app.MapPost("/v1/worlds/{worldId}/commands", async (string worldId, HttpContext context) =>
{
    RequireWorld(worldId);
    var request = await WorldCommand.Read(context.Request, database.Scenario);
    return service.Execute(TokenHash(context), request, context.Request.Headers["X-Test-Fault"].ToString(), WorldInstance.ReadHeader(context.Request),
        context.Request.Headers[WorkshopRules.Header].ToString().Split(',', StringSplitOptions.TrimEntries).Contains(WorkshopRules.Capability)).ToResult();
});
app.MapFallback((HttpContext context) => Protocol.Error(database.Scenario.RulesVersion, 404, "INVALID_REQUEST", "接口不存在", context.Items["identity"] as Identity).ToResult());
await app.RunAsync();
return 0;

static string TokenHash(HttpContext context) => (string)context.Items["tokenHash"]!;
static MosaicInboxQuery ReadMosaicInboxQuery(IQueryCollection query)
{
    var scope = "received";
    var status = "pending";
    long? before = null;
    var limit = 20;
    foreach (var (key, values) in query)
    {
        if (values.Count != 1 || string.IsNullOrEmpty(values[0]))
            throw new RequestFailure(400, "INVALID_REQUEST", "查询参数不得为空或重复");
        var value = values[0]!;
        switch (key)
        {
            case "scope" when value is "received" or "sent" or "all": scope = value; break;
            case "status" when value is "pending" or "reviewed" or "all": status = value; break;
            case "before" when PositiveInteger(value, out var cursor): before = cursor; break;
            case "limit" when PositiveInteger(value, out var size) && size <= 20: limit = (int)size; break;
            default: throw new RequestFailure(400, "INVALID_REQUEST", "查询参数无效");
        }
    }
    return new(scope, status, before, limit);
}
static bool PositiveInteger(string value, out long number)
{
    number = 0;
    return value.All(c => c is >= '0' and <= '9') &&
        long.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out number) && number > 0;
}
static void RequireWorld(string worldId)
{
    if (worldId != Protocol.WorldId) throw new RequestFailure(404, "WORLD_NOT_FOUND", "世界不存在");
}
