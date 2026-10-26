using System.Text.Json;
using Microsoft.Data.Sqlite;
using static World.Server.WorldDatabase;

namespace World.Server;

internal sealed record EntityNoteAdoption(string EntityId, string InstanceId, long StateVersion, long EventCursor);
internal sealed record EntityNote(string NoteId, string EntityId, string AuthorActorId, string OperatorId,
    string CommandId, string Text, string? ReplyToNoteId, long StateVersion, long EventCursor,
    string SharedAtUtc, double[] Position, long InventoryWood)
{
    public int CapabilityVersion => 1;
}

internal static class EntityNoteRules
{
    public const string Capability = "entity-notes-v1";
    public const int MaxPerOperator = 2, MaxTotal = 6, MaxTextScalars = 160;
    public const double Reach = 1.6;

    public const string Schema = """
        CREATE TABLE entity_note_adoption(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), capability TEXT NOT NULL CHECK(capability='entity-notes-v1'),
          version INTEGER NOT NULL CHECK(version=1), entity_id TEXT NOT NULL REFERENCES entities(entity_id),
          instance_id TEXT NOT NULL REFERENCES world_instance(instance_id), state_version INTEGER NOT NULL,
          event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq));
        CREATE TABLE entity_notes(
          note_id TEXT PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id),
          entity_id TEXT NOT NULL REFERENCES entities(entity_id), author_actor_id TEXT NOT NULL, operator_id TEXT NOT NULL,
          command_id TEXT NOT NULL, text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 160),
          reply_to_note_id TEXT REFERENCES entity_notes(note_id), state_version INTEGER NOT NULL,
          event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq) DEFERRABLE INITIALLY DEFERRED,
          shared_at_utc TEXT NOT NULL, x REAL NOT NULL, y REAL NOT NULL, inventory_wood INTEGER NOT NULL CHECK(inventory_wood BETWEEN 0 AND 12),
          UNIQUE(world_id,author_actor_id,command_id), FOREIGN KEY(world_id,author_actor_id) REFERENCES residents(world_id,actor_id));
        CREATE TRIGGER immutable_entity_note_adoption_update BEFORE UPDATE ON entity_note_adoption BEGIN SELECT RAISE(ABORT,'immutable note adoption'); END;
        CREATE TRIGGER immutable_entity_note_adoption_delete BEFORE DELETE ON entity_note_adoption BEGIN SELECT RAISE(ABORT,'immutable note adoption'); END;
        CREATE TRIGGER immutable_entity_note_update BEFORE UPDATE ON entity_notes BEGIN SELECT RAISE(ABORT,'immutable entity note'); END;
        CREATE TRIGGER immutable_entity_note_delete BEFORE DELETE ON entity_notes BEGIN SELECT RAISE(ABORT,'immutable entity note'); END;
        """;

    public static EntityNoteAdoption? ReadAdoption(SqliteConnection c, SqliteTransaction t)
    {
        var tables = Scalar(c, t, "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN('entity_note_adoption','entity_notes')");
        if (tables == 0) return null;
        if (tables != 2) throw new InvalidOperationException("手记扩展表不完整");
        using var command = Command(c, t, "SELECT singleton,capability,version,entity_id,instance_id,state_version,event_seq FROM entity_note_adoption");
        using var r = command.ExecuteReader();
        if (!r.Read() || r.GetInt64(0) != 1 || r.GetString(1) != Capability || r.GetInt64(2) != 1 ||
            !WorldInstance.Valid(r.GetString(4))) throw new InvalidOperationException("手记采用元数据不受支持");
        var adopted = new EntityNoteAdoption(r.GetString(3), r.GetString(4), r.GetInt64(5), r.GetInt64(6));
        if (r.Read()) throw new InvalidOperationException("手记采用元数据不唯一");
        return adopted;
    }

    public static NaturalStructure? ReadBridge(SqliteConnection c, SqliteTransaction t, string entityId)
    {
        using var command = Command(c, t, """
            SELECT entity_id,definition_id,definition_version,rules_version,owner_actor_id,x,y,embodied_wood
            FROM entities WHERE entity_id=$id AND world_id=$world AND definition_id='bridge'
              AND definition_version=1 AND rules_version='r10' AND embodied_wood=6
            """, ("$id", entityId), ("$world", Protocol.WorldId));
        using var r = command.ExecuteReader();
        return r.Read() ? new(r.GetString(0), r.GetString(1), r.GetInt64(2), r.GetString(3), r.GetString(4),
            [r.GetDouble(5), r.GetDouble(6)], r.GetInt64(7)) : null;
    }

    public static List<EntityNote> ReadNotes(SqliteConnection c, SqliteTransaction t)
    {
        using var command = Command(c, t, """
            SELECT note_id,entity_id,author_actor_id,operator_id,command_id,text,reply_to_note_id,
              state_version,event_seq,shared_at_utc,x,y,inventory_wood FROM entity_notes WHERE world_id=$world ORDER BY event_seq
            """, ("$world", Protocol.WorldId));
        using var r = command.ExecuteReader();
        var notes = new List<EntityNote>();
        while (r.Read()) notes.Add(new(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetString(4),
            r.GetString(5), r.IsDBNull(6) ? null : r.GetString(6), r.GetInt64(7), r.GetInt64(8), r.GetString(9),
            [r.GetDouble(10), r.GetDouble(11)], r.GetInt64(12)));
        return notes;
    }
}

internal sealed partial class WorldDatabase
{
    public bool AdoptEntityNotes(string expectedInstance, string entityId)
    {
        if (!WorldInstance.Valid(expectedInstance) || !Protocol.ValidCommandId(entityId))
            throw new ArgumentException("必须指定原实例和目标实体");
        using var c = Open();
        using var ownership = new FileStream(Path + ".material-clock.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        using var t = c.BeginTransaction(deferred: false);
        Scenario = ReadScenario(c, t, Scalar(c, t, "PRAGMA user_version"));
        if (!Scenario.SupportsMaterialAccess || WorldInstance.Read(c, t) != expectedInstance)
            throw new InvalidOperationException("共同手记只能在指定的原r10实例采用");
        var previous = EntityNoteRules.ReadAdoption(c, t);
        if (previous is not null)
        {
            if (previous.EntityId != entityId || previous.InstanceId != expectedInstance)
                throw new InvalidOperationException("既有共同手记不能更换目标或重置额度");
            return false;
        }
        if (EntityNoteRules.ReadBridge(c, t, entityId) is null) throw new ArgumentException("目标不是原世界中的桥");
        Run(c, t, EntityNoteRules.Schema);
        var version = checked(Scalar(c, t, "SELECT state_version FROM worlds WHERE id=$world", ("$world", Protocol.WorldId)) + 1);
        var seq = checked(Scalar(c, t, "SELECT coalesce(max(seq),0) FROM events") + 1);
        var adopted = new { seq, stateVersion = version, actorId = (string?)null, commandId = (string?)null,
            type = "entityNotesAdopted", capability = EntityNoteRules.Capability, capabilityVersion = 1,
            entityId, worldInstanceId = expectedInstance, maxPerOperator = EntityNoteRules.MaxPerOperator,
            maxTotal = EntityNoteRules.MaxTotal, maxTextScalars = EntityNoteRules.MaxTextScalars, reach = EntityNoteRules.Reach };
        Run(c, t, "UPDATE worlds SET state_version=$version WHERE id=$world", ("$version", version), ("$world", Protocol.WorldId));
        Run(c, t, "INSERT INTO events(seq,world_id,state_version,event_json) VALUES($seq,$world,$version,$event)",
            ("$seq", seq), ("$world", Protocol.WorldId), ("$version", version), ("$event", JsonSerializer.Serialize(adopted, Protocol.Json)));
        Run(c, t, "INSERT INTO entity_note_adoption VALUES(1,$capability,1,$entity,$instance,$version,$seq)",
            ("$capability", EntityNoteRules.Capability), ("$entity", entityId), ("$instance", expectedInstance), ("$version", version), ("$seq", seq));
        t.Commit();
        return true;
    }
}

internal sealed partial class WorldService
{
    private void BindEntityNotes(Dictionary<string, object?> body, SqliteConnection c, SqliteTransaction t, Identity identity)
    {
        var adopted = EntityNoteRules.ReadAdoption(c, t);
        if (adopted is null) return;
        var target = EntityNoteRules.ReadBridge(c, t, adopted.EntityId) ?? throw new InvalidOperationException("原手记目标不再匹配");
        var notes = EntityNoteRules.ReadNotes(c, t);
        body["entityNotes"] = new { capability = EntityNoteRules.Capability, version = 1, target, reach = EntityNoteRules.Reach,
            maxTextScalars = EntityNoteRules.MaxTextScalars, maxPerOperator = EntityNoteRules.MaxPerOperator,
            maxTotal = EntityNoteRules.MaxTotal, selfCount = notes.Count(n => n.OperatorId == identity.OperatorId), totalCount = notes.Count, notes };
    }

    private (int Status, ApiError Error)? ValidateEntityNote(SqliteConnection c, SqliteTransaction t, WorldAction action, Actor actor, Identity identity)
    {
        var adopted = Scenario.SupportsMaterialAccess ? EntityNoteRules.ReadAdoption(c, t) : null;
        if (adopted is null) return (422, new("ENTITY_NOTES_UNAVAILABLE", "当前世界尚未采用共同手记"));
        var target = EntityNoteRules.ReadBridge(c, t, adopted.EntityId);
        if (action.EntityId != adopted.EntityId || target is null)
            return (404, new("NOTE_TARGET_UNAVAILABLE", "目标未开放共同手记"));
        var notes = EntityNoteRules.ReadNotes(c, t);
        if (action.ReplyToNoteId is not null && !notes.Any(n => n.NoteId == action.ReplyToNoteId && n.EntityId == action.EntityId))
            return (404, new("NOTE_REFERENCE_NOT_FOUND", "未找到这座桥上的原手记"));
        if (notes.Count >= EntityNoteRules.MaxTotal || notes.Count(n => n.OperatorId == identity.OperatorId) >= EntityNoteRules.MaxPerOperator)
            return (422, new("NOTE_LIMIT_REACHED", "本次共同手记的内容额度已用完"));
        var trees = ReadResourceNodes(c, t); var entities = ReadStructures(c, t);
        if (ContinuousWorld.Distance(actor.X, actor.Y, target.Position[0], target.Position[1]) > EntityNoteRules.Reach ||
            !ContinuousWorld.Walkable(actor.X, actor.Y, trees, entities) ||
            ContinuousWorld.Sweep(actor.X, actor.Y, target.Position[0], target.Position[1], trees, entities).Blocked)
            return (422, new("UNREACHABLE", "请走到原桥中心1.6米内且中间没有障碍"));
        return null;
    }

    private static (object Result, object Event) ApplyEntityNote(SqliteConnection c, SqliteTransaction t,
        WorldCommand request, Identity identity, Actor actor, long version, long cursor)
    {
        var action = request.Action;
        var note = new EntityNote("n" + Guid.NewGuid().ToString("N"), action.EntityId!, identity.ActorId, identity.OperatorId,
            request.CommandId, action.Text!, action.ReplyToNoteId, version, cursor, DateTimeOffset.UtcNow.ToString("O"), [actor.X, actor.Y], actor.Wood);
        Run(c, t, """
            INSERT INTO entity_notes(note_id,world_id,entity_id,author_actor_id,operator_id,command_id,text,reply_to_note_id,
              state_version,event_seq,shared_at_utc,x,y,inventory_wood)
            VALUES($id,$world,$entity,$actor,$operator,$command,$text,$reply,$version,$seq,$utc,$x,$y,$wood)
            """, ("$id", note.NoteId), ("$world", Protocol.WorldId), ("$entity", note.EntityId), ("$actor", note.AuthorActorId),
            ("$operator", note.OperatorId), ("$command", note.CommandId), ("$text", note.Text), ("$reply", note.ReplyToNoteId),
            ("$version", version), ("$seq", cursor), ("$utc", note.SharedAtUtc), ("$x", actor.X), ("$y", actor.Y), ("$wood", actor.Wood));
        return (WithFields(note, ("action", "append_entity_note")),
            WithFields(note, ("type", "entityNoteAppended"), ("seq", cursor), ("actorId", identity.ActorId)));
    }
}
