(() => {
  "use strict";
  const roster = { a1: "local-operator", a1_alias: "local-operator", a2: "declared-late", a3: "declared-third" };
  const fields = ["noteId", "entityId", "authorActorId", "operatorId", "commandId", "text", "replyToNoteId", "capabilityVersion", "stateVersion", "eventCursor", "sharedAtUtc", "position", "inventoryWood"];
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const integer = x => Number.isSafeInteger(x) && x >= 0;
  const point = x => Array.isArray(x) && x.length === 2 && x.every(Number.isFinite);
  const id = (x, prefix) => typeof x === "string" && new RegExp(`^${prefix}[0-9a-f]{32}$`).test(x);
  const text = x => typeof x === "string" && Array.from(x).length >= 1 && Array.from(x).length <= 160
    && /[^\p{White_Space}]/u.test(x) && !/[\p{Cc}\p{Cs}]/u.test(x);
  const equal = (a, b) => Array.isArray(a) ? Array.isArray(b) && a.length === b.length && a.every((v, i) => equal(v, b[i]))
    : object(a) ? object(b) && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => equal(a[k], b[k])) : a === b;
  const target = x => object(x) && id(x.entityId, "e") && x.definitionId === "bridge" && x.definitionVersion === 1
    && x.rulesVersion === "r10" && Object.hasOwn(roster, x.ownerActorId) && x.embodiedWood === 6 && point(x.position);
  const note = x => object(x) && fields.every(k => Object.hasOwn(x, k)) && id(x.noteId, "n") && id(x.entityId, "e")
    && Object.hasOwn(roster, x.authorActorId) && x.operatorId === roster[x.authorActorId] && typeof x.commandId === "string" && x.commandId.length > 0
    && text(x.text) && (x.replyToNoteId === null || id(x.replyToNoteId, "n")) && x.capabilityVersion === 1
    && integer(x.stateVersion) && x.stateVersion > 0 && x.eventCursor === x.stateVersion + 1
    && typeof x.sharedAtUtc === "string" && Number.isFinite(Date.parse(x.sharedAtUtc))
    && point(x.position) && integer(x.inventoryWood) && x.inventoryWood <= 12;
  const goal = x => object(x) && Object.keys(x).length === 3 && id(x.entityId, "e") && text(x.text)
    && Object.hasOwn(x, "replyToNoteId") && (x.replyToNoteId === null || id(x.replyToNoteId, "n"));
  const action = x => object(x) && x.type === "append_entity_note" && Object.keys(x).length === 4
    && goal({entityId:x.entityId, text:x.text, replyToNoteId:x.replyToNoteId});
  const record = x => note(x) && /^w_[0-9a-f]{32}$/.test(x.worldInstanceId);
  function capability(x) {
    if (!object(x) || x.capability !== "entity-notes-v1" || x.version !== 1 || x.reach !== 1.6
      || x.maxTextScalars !== 160 || x.maxPerOperator !== 2 || x.maxTotal !== 6 || !target(x.target)
      || !integer(x.selfCount) || x.selfCount > 2 || !integer(x.totalCount) || x.totalCount > 6
      || !Array.isArray(x.notes) || x.notes.length !== x.totalCount) return false;
    const ids = new Set(), counts = {};
    return x.notes.every((n, i) => {
      if (!note(n) || n.entityId !== x.target.entityId || ids.has(n.noteId) || i && n.eventCursor <= x.notes[i - 1].eventCursor
        || n.replyToNoteId !== null && !ids.has(n.replyToNoteId)) return false;
      ids.add(n.noteId); counts[n.operatorId] = (counts[n.operatorId] || 0) + 1;
      return counts[n.operatorId] <= 2;
    });
  }
  function validate(data, require) {
    const {mission:m, facts:f, budget:b, world:w, steps} = data, uses = m.goal?.entityNote !== undefined;
    require(m.allowEntityNotes === undefined || typeof m.allowEntityNotes === "boolean", "旧桥手记权限应为布尔值。");
    require(!uses || m.rulesVersion === "r10" && m.preconditionMode === "actor-state-v1" && goal(m.goal.entityNote)
      && !m.goal.buildRecipeId && !m.goal.materialAccess && !m.goal.transfer && !m.goal.activityId
      && !m.sharePostcard && !m.paintMosaic && !m.proposeMosaic && !m.reviewMosaicProposal, "旧桥手记需要独立的原桥、正文和引用目标。");
    require(!uses || integer(b.limits.queries) && b.limits.queries >= 1 && b.limits.queries <= 5000
      && integer(b.used.queries), "旧桥手记任务缺少累计查询预算。");
    require(f.entityNoteShared === undefined || typeof f.entityNoteShared === "boolean", "手记发表事实应为布尔值。");
    require(f.entityNote === undefined || f.entityNote === null || record(f.entityNote), "原手记事实不完整。");
    require(w.entityNotes === undefined || w.entityNotes === null || capability(w.entityNotes), "共同手记快照格式不正确。");
    for (const s of steps.filter(s => s.action.type === "append_entity_note")) {
      require(uses && action(s.action), "手记动作缺少原任务目标。");
      if (s.status === "committed") require(record(s.entityNoteEvidence), "手记步骤缺少原发表依据。");
    }
  }
  function assess(data) {
    const {mission:m, facts:f, world:w, steps} = data, uses = Boolean(m.goal?.entityNote);
    const claims = steps.filter(s => s.action.type === "append_entity_note" && s.status === "committed");
    const n = f.entityNote, cap = w.entityNotes, s = claims[0];
    const original = object(n) ? Object.fromEntries(fields.map(k => [k,n[k]])) : null;
    const reference = cap?.notes?.find(r => r.noteId === n?.replyToNoteId);
    const verified = Boolean(uses && m.allowEntityNotes === true && f.entityNoteShared === true && record(n) && claims.length === 1
      && capability(cap) && cap.target.entityId === m.goal.entityNote.entityId && equal(cap.target.position,m.goal.target)
      && w.entities.some(e => equal(e,cap.target)) && n.worldInstanceId === m.worldInstanceId && n.worldInstanceId === w.instanceId
      && n.authorActorId === m.actorId && n.operatorId === roster[m.actorId]
      && n.entityId === m.goal.entityNote.entityId && n.text === m.goal.entityNote.text && n.replyToNoteId === m.goal.entityNote.replyToNoteId
      && s.commandId === n.commandId && s.stateVersion === n.stateVersion && s.inventoryWood === n.inventoryWood
      && equal(s.position,n.position) && Math.hypot(n.position[0]-cap.target.position[0], n.position[1]-cap.target.position[1]) <= 1.600001
      && equal(s.action,{type:"append_entity_note",...m.goal.entityNote}) && equal(s.entityNoteEvidence,n)
      && s.evidenceSource === "original_receipt_note_and_event"
      && cap.notes.some(r => equal(r,original)) && n.stateVersion <= f.endStateVersion
      && (n.replyToNoteId === null || reference && reference.entityId === n.entityId && reference.eventCursor < n.eventCursor));
    const consistent = verified || f.entityNoteShared !== true && !n && claims.length === 0;
    return {uses,verified,consistent};
  }
  window.EntityNoteReport = {validate,assess,action};
})();
