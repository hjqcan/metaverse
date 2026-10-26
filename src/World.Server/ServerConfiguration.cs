using System.Net;

namespace World.Server;

internal sealed record ServerConfiguration(string DataDirectory, string ContentRoot, string Url, bool FaultsEnabled,
    WorldScenario? RequestedScenario)
{
    public static ServerConfiguration Load()
    {
        var repo = FindRepository(AppContext.BaseDirectory) ?? FindRepository(Directory.GetCurrentDirectory());
        var data = Environment.GetEnvironmentVariable("WORLD_DATA_DIR");
        if (string.IsNullOrWhiteSpace(data))
            data = Path.Combine(repo ?? AppContext.BaseDirectory, ".local", "world");
        var url = Environment.GetEnvironmentVariable("WORLD_URL") ?? "http://127.0.0.1:5080";
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme != "http" ||
            uri.UserInfo.Length != 0 || uri.AbsolutePath != "/" || uri.Query.Length != 0 || uri.Fragment.Length != 0 ||
            !(uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
              IPAddress.TryParse(uri.DnsSafeHost, out var address) && IPAddress.IsLoopback(address)))
            throw new InvalidOperationException("WORLD_URL 只允许一个 loopback HTTP 地址");
        // Within the repository use the live source assets, including assets authored after the build.
        // Published / relocated output uses its copied wwwroot, independent of the launch directory.
        var contentRoot = repo is not null && Directory.Exists(Path.Combine(repo, "src", "World.Server", "wwwroot"))
            ? Path.Combine(repo, "src", "World.Server") : AppContext.BaseDirectory;
        var scenarioId = Environment.GetEnvironmentVariable("WORLD_SCENARIO");
        var scenario = scenarioId is null ? null : WorldScenario.FromId(scenarioId);
        return new(Path.GetFullPath(data), contentRoot, url, Environment.GetEnvironmentVariable("WORLD_ENABLE_FAULTS") == "1", scenario);
    }

    private static string? FindRepository(string start)
    {
        for (var directory = new DirectoryInfo(start); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "docs", "contracts", "foundation-v1.md")))
                return directory.FullName;
        return null;
    }
}
