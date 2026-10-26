(() => {
  "use strict";
  const roster = { a1: "local-operator", a1_alias: "local-operator", a2: "declared-late", a3: "declared-third" };
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const integer = x => Number.isSafeInteger(x) && x >= 0;
  const id = x => typeof x === "string" && x.length > 0;
  const reservationId = x => typeof x === "string" && /^m[0-9a-f]{32}$/.test(x);
  const point = x => Array.isArray(x) && x.length === 2 && x.every(Number.isFinite);
  const sourcePoint = x => point(x) && x[0] === 28 && x[1] === 10;
  const equal = (a, b) => object(a) && object(b) && Object.keys(a).length === Object.keys(b).length
    && Object.keys(a).every(k => Array.isArray(a[k]) ? point(b[k]) && a[k].every((v, i) => v === b[k][i]) : a[k] === b[k]);
  const common = x => object(x) && id(x.worldInstanceId) && id(x.actorId) && id(x.operatorId)
    && x.sourceId === "wood-source-east" && reservationId(x.reservationId)
    && integer(x.stateVersion) && x.eventCursor === x.stateVersion + 1;
  const reservation = x => common(x) && id(x.requestCommandId) && integer(x.queueSequence)
    && x.queueSequence > 0 && integer(x.requestedAtMs);
  const harvest = x => common(x) && id(x.commandId) && x.quantity === 1 && sourcePoint(x.position)
    && integer(x.remainingBefore) && x.remainingBefore >= 1 && x.remainingBefore <= 3
    && x.remaining === x.remainingBefore - 1 && integer(x.inventoryWoodBefore) && x.inventoryWoodBefore < 12
    && x.inventoryWood === x.inventoryWoodBefore + 1;
  const action = a => object(a) && (a.type === "reserve_material" ? a.sourceId === "wood-source-east"
    : a.type === "harvest_material" && reservationId(a.reservationId));

  function validate(data, require) {
    const { mission: m, facts: f, budget: b, steps } = data, uses = m.goal?.materialAccess !== undefined;
    require(m.allowMaterialAccess === undefined || typeof m.allowMaterialAccess === "boolean", "材料入口权限应为布尔值。");
    require(!uses || m.rulesVersion === "r10" && m.preconditionMode === "actor-state-v1"
      && object(m.goal.materialAccess) && m.goal.materialAccess.sourceId === "wood-source-east"
      && m.goal.materialAccess.quantity === 3 && m.goal.buildRecipeId === "platform.v1"
      && !m.goal.transfer && !m.goal.activityId, "材料入口目标需要原来源、3木材和本人平台。");
    if (uses || b.limits.queries !== undefined || b.used.queries !== undefined) require(integer(b.limits.queries) && b.limits.queries >= 1
      && b.limits.queries <= 5000 && integer(b.used.queries), "材料入口任务缺少累计查询预算。");
    require(f.materialReservation === undefined || f.materialReservation === null || reservation(f.materialReservation), "原材料预约记录不完整。");
    require(f.materialWoodHarvested === undefined || integer(f.materialWoodHarvested) && f.materialWoodHarvested <= 3, "材料入口领取数量无效。");
    require(f.materialHarvests === undefined || Array.isArray(f.materialHarvests) && f.materialHarvests.length <= 3
      && f.materialHarvests.every(harvest), "原材料领取记录不完整。");
    for (const s of steps.filter(s => ["reserve_material", "harvest_material"].includes(s.action.type))) {
      require(uses && action(s.action), "材料动作缺少原任务授权目标。");
      if (s.status === "committed") require(s.action.type === "reserve_material" ? reservation(s.materialEvidence)
        : harvest(s.materialEvidence), "材料动作缺少原回执依据。");
    }
  }

  function assess(data) {
    const { mission: m, facts: f, steps } = data, uses = Boolean(m.goal?.materialAccess);
    const original = f.materialReservation, records = f.materialHarvests || [];
    const requests = steps.filter(s => s.status === "committed" && s.action.type === "reserve_material");
    const claims = steps.filter(s => s.status === "committed" && s.action.type === "harvest_material");
    const bound = x => x.worldInstanceId === m.worldInstanceId && x.actorId === m.actorId
      && x.operatorId === roster[m.actorId];
    const reserved = Boolean(uses && m.allowMaterialAccess === true && original && bound(original)
      && requests.length === 1 && requests[0].commandId === original.requestCommandId
      && requests[0].stateVersion === original.stateVersion && equal(requests[0].materialEvidence, original)
      && requests[0].evidenceSource === "command_receipt_and_original_event");
    const collected = reserved && records.length === (f.materialWoodHarvested || 0) && claims.length === records.length
      && new Set(records.map(r => r.commandId)).size === records.length && records.every((r, i) => {
        const s = claims[i];
        return bound(r) && r.reservationId === original.reservationId && r.remainingBefore === 3 - i
          && r.remaining === 2 - i && r.stateVersion > (i ? records[i - 1].stateVersion : original.stateVersion)
          && s.commandId === r.commandId && s.action.reservationId === original.reservationId
          && s.stateVersion === r.stateVersion && s.inventoryWood === r.inventoryWood
          && point(s.position) && Math.hypot(s.position[0] - 28, s.position[1] - 10) <= 1.6
          && equal(s.materialEvidence, r) && s.evidenceSource === "command_receipt";
      });
    const consistent = !original && requests.length === 0 && claims.length === 0 && records.length === 0
      && (f.materialWoodHarvested || 0) === 0 || collected;
    const verified = Boolean(uses && collected && records.length === 3 && (!f.constructionBuilt
      || records[2].stateVersion < f.construction?.stateVersion));
    return { uses, reserved, consistent, verified, count: records.length };
  }
  window.MaterialReport = { validate, assess, action };
})();
