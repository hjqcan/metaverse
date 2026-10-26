using System.Diagnostics;
using static World.Server.WorldDatabase;

namespace World.Server;

// A process-local monotonic clock resumed from a committed database checkpoint.
// UTC changes and time spent with no service process never create production time.
internal sealed class MaterialServiceClock : IDisposable
{
    private readonly FileStream ownership;
    private readonly Stopwatch elapsed;
    private readonly long checkpoint;

    public MaterialServiceClock(WorldDatabase database)
    {
        // Only one production clock may run for this database. Offline session
        // administration does not acquire this lock or start the clock.
        ownership = new FileStream(database.Path + ".material-clock.lock", FileMode.OpenOrCreate,
            FileAccess.ReadWrite, FileShare.None);
        try
        {
            using var connection = database.Open();
            using var transaction = connection.BeginTransaction(deferred: true);
            // Adoption may have committed after Initialize read the old schema.
            // The running policy must be read while this clock owns the lock.
            database.ReloadMaterialPolicy(connection, transaction);
            checkpoint = Scalar(connection, transaction, "SELECT service_ms FROM material_source WHERE id=1");
            transaction.Commit();
            elapsed = Stopwatch.StartNew();
        }
        catch { ownership.Dispose(); throw; }
    }

    public long Now => checked(checkpoint + elapsed.ElapsedMilliseconds);

    public void Dispose() => ownership.Dispose();
}
