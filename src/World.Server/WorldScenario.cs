namespace World.Server;

internal sealed record WorldActivity(string Id, string Label, int X, int Y, string Description)
{
    public int[] Position => [X, Y];
    public object Observation => new { id = Id, label = Label, position = Position, description = Description };
}

// Scenario selection is frozen in the database at creation, never inferred from a request.
internal sealed record WorldScenario(string Id, string RulesVersion, int GoalX)
{
    public static readonly WorldScenario Foundation = new("foundation-v1", "r1", 5);
    public static readonly WorldScenario Passage = new("passage-v1", "r2", 6);
    public static readonly WorldScenario Activities = new("activities-v1", "r3", 6);
    public static readonly WorldScenario Postcards = new("postcards-v1", "r4", 6);
    public static readonly WorldScenario Mosaic = new("mosaic-v1", "r5", 6);
    public static readonly WorldScenario Consent = new("consent-v1", "r6", 6);

    public static readonly IReadOnlyList<MosaicColor> MosaicPalette = Array.AsReadOnly<MosaicColor>([
        new("blank", "空白", "#F4F0E6"), new("leaf", "叶绿", "#42745B"),
        new("river", "河蓝", "#477FA3"), new("sun", "日黄", "#E4B858"),
        new("rose", "花红", "#C86A70"), new("ink", "墨色", "#37444D")
    ]);

    private static readonly IReadOnlyList<WorldActivity> ActivityDefinitions = Array.AsReadOnly<WorldActivity>([
        new("garden", "静谧花园", 1, 6, "在本岸花园安静散步，适合短途放松，不需过河。"),
        new("riverwalk", "河岸步道", 2, 5, "沿本岸步道观察河流，适合看水与散步，不需过河。"),
        new("lookout", "彼岸观景台", 6, 1, "从彼岸看两岸全景，需要跨河；初始须建设两段桥。")
    ]);

    public bool SupportsMosaicConsent => Id == Consent.Id;
    public bool SupportsMosaic => Id == Mosaic.Id || SupportsMosaicConsent;
    public bool SupportsPostcards => Id == Postcards.Id || SupportsMosaic;
    public bool SupportsActivities => Id == Activities.Id || SupportsPostcards;
    public IReadOnlyList<WorldActivity> ActivityCatalog => SupportsActivities ? ActivityDefinitions : Array.Empty<WorldActivity>();

    public static WorldScenario FromId(string id) => id switch
    {
        "foundation-v1" => Foundation,
        "passage-v1" => Passage,
        "activities-v1" => Activities,
        "postcards-v1" => Postcards,
        "mosaic-v1" => Mosaic,
        "consent-v1" => Consent,
        _ => throw new InvalidOperationException("不支持的 WORLD_SCENARIO 场景")
    };

    public static bool InBounds(long x, long y) => x is >= 0 and < 8 && y is >= 0 and < 8;
    public static bool IsWall(long x, long y) => InBounds(x, y) && x == 3 && y <= 2;
    public bool IsWater(long x, long y) => (Id == Passage.Id || SupportsActivities) && InBounds(x, y) && x is 4 or 5;
    public bool IsLand(long x, long y) => InBounds(x, y) && !IsWall(x, y) && !IsWater(x, y);
    public bool SupportsRecipe(string recipe) => recipe == "platform.v1" || (Id == Passage.Id || SupportsActivities) && recipe == "bridge.v1";
}

internal sealed record MosaicColor(string Id, string Label, string Hex);
