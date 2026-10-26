(() => {
  "use strict";

  const MAX_BYTES = 2 * 1024 * 1024;
  const SAMPLE = new URLSearchParams(location.search).get("sample");
  const DEMO_FILE = ({ activities: "activity-demo.json", postcards: "postcard-first.json", "postcards-reply": "postcard-second.json", mosaic: "mosaic-first.json", "mosaic-reply": "mosaic-second.json", consent: "consent-proposer.json", "consent-review": "consent-reviewer.json", inbox: "inbox-proposer.json", "inbox-review": "inbox-reviewer.json" })[SAMPLE] || "resident-demo.json";
  const $ = (id) => document.getElementById(id);
  const mosaic = window.MosaicUI;
  const consent = window.ConsentUI;
  const statuses = {
    running: ["执行中（记录时）", "neutral"], paused: ["已暂停", "warning"],
    blocked: ["受阻", "warning"], budget_exhausted: ["预算耗尽", "warning"],
    unknown: ["结果未知", "warning"], completed: ["已完成", "success"],
    decision_failed: ["目标选择失败", "error"],
  };
  const providers = { "codex-exec": "模型决策", "fixed-reference": "固定策略基线", "test-double": "测试替身 · 非真实模型" };
  const structures = { "platform.v1": { label: "平台", definition: "platform", wood: 3 }, "bridge.v1": { label: "木桥", definition: "bridge", wood: 6 } };
  const workshopPermissions = { build_workshop: "allowWorkshopBuild", craft_tool: "allowCraftTool", deposit_wood: "allowDepositWood", withdraw_wood: "allowWithdrawWood" };
  const workshopNames = { build_workshop: "建造工坊家具", craft_tool: "制作本人木工锤", deposit_wood: "存入本人箱", withdraw_wood: "从本人箱取出" };
  const forestryPermissions = { craft_forestry_tool: "allowCraftForestryTool", reserve_forest: "allowReserveForest", cancel_forest_reservation: "allowCancelForestReservation", collect_seed: "allowCollectSeed", plant_tree: "allowPlantTree", harvest_tree: "allowHarvestTree" };
  const forestryNames = { craft_forestry_tool: "制作本人木斧", reserve_forest: "申请原林业预约", cancel_forest_reservation: "取消原林业预约", collect_seed: "领取原预约树种", plant_tree: "在原林地种植", harvest_tree: "收获原树木" };
  const forestStateNames = { queued: "排队中", preparing: "准备中", growing: "生长中", harvesting: "待收获", completed: "已完成", cancelled: "已取消", expired: "已到期", mature: "成熟", harvested: "已收获" };
  const forestPlots = { "forest-west-north": [7, 12], "forest-west-south": [7, 16], "forest-east-north": [21, 7], "forest-east-far": [29, 5] };
  const forestPolicy = { seedIntervalMs: 60000, nurseryCapacity: 4, preparationLeaseMs: 90000, growthMs: 120000, harvestLeaseMs: 60000, woodPerTree: 3, seedsPerHarvest: 1, groupLimit: 1, interactReach: 1.6 };
  const forestMaterials = ["wood", "woodHarvested", "seedsCollected", "seedsPlanted", "seedsHarvested"];
  const reservationKeys = "reservationId actorId operatorId commandId requestedAtMs queueOrder status plotId plantId reservedSeed grantedAtMs expiresAtMs";
  const reservationIdentityKeys = "reservationId actorId operatorId commandId requestedAtMs queueOrder";
  const plantIdentityKeys = "plantId plotId planterActorId operatorId reservationId commandId plantedAtMs maturesAtMs stateVersion eventCursor";
  const actionNames = { paint_entity_canvas: "绘制平台地画", append_entity_note: "发表旧桥手记", reserve_material: "预约材料", harvest_material: "按原预约领取", walk: "行走", move: "移动", claim: "领取木材", gather: "采集木材", transfer: "赠送木材", build: "建造", visit: "到访", postcard: "分享手记", mosaic: "绘制画布", mosaic_propose: "提出修改建议", mosaic_review: "审阅修改建议", observe: "观察", wait: "等待" };
  const stepStatuses = { committed: "已提交", rejected: "已拒绝", unknown: "结果未知", pending: "待确认", failed: "失败" };
  const reasonNames = { round_trip_verified: "已核验到达目标并返回原起点", max_steps: "本次分段步数已到，等待恢复" };
  let report = null;
  let generation = 0;
  let request = null;
  let stepButtons = [];

  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const number = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
  const integer = (value) => number(value) && Number.isSafeInteger(value);
  const string = (value) => typeof value === "string";
  const postcardText = (value) => string(value) && Array.from(value).length >= 1 && Array.from(value).length <= 160 && /[^\p{White_Space}]/u.test(value) && !/[\p{Cc}\p{Cs}]/u.test(value);
  const same = (a, b) => a[0] === b[0] && a[1] === b[1];
  const coord = (point) => `(${formatNumber(point[0])}, ${formatNumber(point[1])})`;
  const continuous = (world) => world.coordinateSystem === "continuous-xz";
  const formatNumber = (value) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
  const put = (id, value) => { $(id).textContent = value; };
  function require(value, message) { if (!value) throw new Error(message); }
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  const exact = (a, b) => {
    if (a === b) return true;
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => exact(v, b[i]));
    return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => Object.hasOwn(b, k) && exact(a[k], b[k]));
  };
  const fields = (v, keys) => object(v) && exact(Object.keys(v).sort(), keys.split(" ").sort());
  const identifier = v => string(v) && /^[A-Za-z0-9_-]{1,128}$/.test(v);
  const point = v => Array.isArray(v) && v.length === 2 && v.every(number);
  const wood = v => integer(v) && v <= 12;
  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const subset = (v, keys) => v === null ? null : Object.fromEntries(keys.split(" ").map(k => [k, v[k]]));
  const forestRectangle = p => [p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5];
  function forestryAction(a) {
    if (!object(a) || a.capabilityVersion !== 1 || !Object.hasOwn(forestryPermissions, a.type)) return false;
    const keys = { craft_forestry_tool: "entityId recipeId", reserve_forest: "", cancel_forest_reservation: "reservationId", collect_seed: "sourceId reservationId", plant_tree: "plotId reservationId", harvest_tree: "plantId reservationId toolId" }[a.type];
    return fields(a, `type capabilityVersion${keys ? ` ${keys}` : ""}`)
      && keys.split(" ").filter(k => k && k !== "recipeId").every(k => identifier(a[k]))
      && (a.type !== "craft_forestry_tool" || a.recipeId === "wooden_axe.v1")
      && (a.type !== "collect_seed" || a.sourceId === "nursery-west")
      && (a.type !== "plant_tree" || Object.hasOwn(forestPlots, a.plotId));
  }
  function forestTool(t) {
    return fields(t, "toolId definitionId definitionVersion ownerActorId embodiedWood workbenchId commandId stateVersion eventCursor")
      && [t.toolId, t.ownerActorId, t.workbenchId, t.commandId].every(identifier) && t.definitionId === "wooden_axe"
      && t.definitionVersion === 1 && t.embodiedWood === 2 && integer(t.stateVersion) && integer(t.eventCursor) && t.eventCursor > 0;
  }
  function forestReservation(r) {
    if (!fields(r, reservationKeys) || ![r.reservationId, r.actorId, r.operatorId, r.commandId].every(identifier)
      || ![r.requestedAtMs, r.queueOrder, r.reservedSeed].every(integer) || r.queueOrder < 1 || r.reservedSeed > 1
      || !["queued", "preparing", "growing", "harvesting", "completed", "cancelled", "expired"].includes(r.status)
      || !(r.plotId === null || Object.hasOwn(forestPlots, r.plotId)) || !(r.plantId === null || identifier(r.plantId))
      || ![r.grantedAtMs, r.expiresAtMs].every(v => v === null || integer(v))
      || r.grantedAtMs !== null && (r.plotId === null || r.grantedAtMs < r.requestedAtMs)
      || r.expiresAtMs !== null && (r.grantedAtMs === null || r.expiresAtMs < r.grantedAtMs)) return false;
    if (r.status === "queued") return [r.plotId, r.plantId, r.grantedAtMs, r.expiresAtMs].every(v => v === null) && r.reservedSeed === 0;
    if (r.status === "preparing") return Object.hasOwn(forestPlots, r.plotId) && r.plantId === null && integer(r.grantedAtMs) && r.expiresAtMs === r.grantedAtMs + 90000;
    if (["growing", "harvesting"].includes(r.status)) return Object.hasOwn(forestPlots, r.plotId) && identifier(r.plantId)
      && integer(r.grantedAtMs) && r.reservedSeed === 0 && (r.status === "growing" ? r.expiresAtMs === null : integer(r.expiresAtMs));
    return r.reservedSeed === 0;
  }
  function forestPlant(p) {
    if (!fields(p, `${plantIdentityKeys} state standingWood matureEventCursor harvestActorId harvestCommandId harvestEventCursor`)
      || !Object.hasOwn(forestPlots, p.plotId) || ![p.plantId, p.planterActorId, p.operatorId, p.reservationId, p.commandId].every(identifier)
      || ![p.plantedAtMs, p.maturesAtMs, p.standingWood, p.stateVersion, p.eventCursor].every(integer)
      || p.eventCursor < 1 || p.maturesAtMs !== p.plantedAtMs + 120000 || !["growing", "mature", "harvested"].includes(p.state)) return false;
    if (p.state === "growing") return p.standingWood === 0 && [p.matureEventCursor, p.harvestActorId, p.harvestCommandId, p.harvestEventCursor].every(v => v === null);
    if (!integer(p.matureEventCursor) || p.matureEventCursor <= p.eventCursor) return false;
    return p.state === "mature" ? p.standingWood === 3 && [p.harvestActorId, p.harvestCommandId, p.harvestEventCursor].every(v => v === null)
      : p.standingWood === 0 && identifier(p.harvestActorId) && identifier(p.harvestCommandId) && integer(p.harvestEventCursor) && p.harvestEventCursor > p.matureEventCursor;
  }
  const forestCost = a => ({ wood: a.type === "craft_forestry_tool" ? 2 : 0, woodHarvested: a.type === "harvest_tree" ? 3 : 0,
    seedsCollected: a.type === "collect_seed" ? 1 : 0, seedsPlanted: a.type === "plant_tree" ? 1 : 0, seedsHarvested: a.type === "harvest_tree" ? 1 : 0 });
  function forestObservation(w, m) {
    const c = w.forestry, n = c?.nursery;
    if (!fields(c, "capability version adoption policy nursery plots plants reservations seeds tools recipes") || c.capability !== "forestry-v1" || c.version !== 1
      || !exact(c.policy, forestPolicy) || !fields(c.adoption, "worldInstanceId adoptedServiceMs stateVersion eventCursor baseStorageVersion")
      || c.adoption.worldInstanceId !== m.worldInstanceId || c.adoption.baseStorageVersion !== 13
      || ![c.adoption.adoptedServiceMs, c.adoption.stateVersion, c.adoption.eventCursor, c.seeds].every(integer) || c.adoption.eventCursor < 1
      || c.adoption.stateVersion > w.observedStateVersion || w.observedSelf.seeds !== c.seeds
      || !exact(c.recipes, [{ id: "wooden_axe.v1", definitionId: "wooden_axe", woodCost: 2, requiresWorkbench: true }])
      || !fields(n, "sourceId position radius buildExclusion serviceMs nextProductionAtMs productionPeriod generatedSeeds stockSeeds reservedSeeds freeSeeds")
      || n.sourceId !== "nursery-west" || !exact(n.position, [7, 6]) || n.radius !== .3 || !exact(n.buildExclusion, forestRectangle([7, 6]))
      || ![n.serviceMs, n.nextProductionAtMs, n.productionPeriod, n.generatedSeeds, n.stockSeeds, n.reservedSeeds, n.freeSeeds].every(integer)
      || n.serviceMs < c.adoption.adoptedServiceMs || n.nextProductionAtMs <= n.serviceMs || n.stockSeeds > 4 || n.reservedSeeds > n.stockSeeds || n.freeSeeds !== n.stockSeeds - n.reservedSeeds
      || !Array.isArray(c.plots) || c.plots.length !== 4 || new Set(c.plots.map(p => p.plotId)).size !== 4
      || !c.plots.every(p => fields(p, "plotId position radius buildExclusion") && Object.hasOwn(forestPlots, p.plotId)
        && exact(p.position, forestPlots[p.plotId]) && p.radius === .45 && exact(p.buildExclusion, forestRectangle(p.position)))
      || !Array.isArray(c.plants) || c.plants.length > 4 || !c.plants.every(p => forestPlant(p) && p.state !== "harvested" && p.stateVersion <= w.observedStateVersion && p.plantedAtMs <= n.serviceMs)
      || new Set(c.plants.map(p => p.plantId)).size !== c.plants.length || new Set(c.plants.map(p => p.plotId)).size !== c.plants.length
      || !Array.isArray(c.reservations) || !c.reservations.every(r => forestReservation(r) && ["queued", "preparing", "growing", "harvesting"].includes(r.status))
      || new Set(c.reservations.map(r => r.reservationId)).size !== c.reservations.length || new Set(c.reservations.map(r => r.operatorId)).size !== c.reservations.length
      || new Set(c.reservations.filter(r => r.plotId !== null).map(r => r.plotId)).size !== c.reservations.filter(r => r.plotId !== null).length
      || c.reservations.reduce((sum, r) => sum + r.reservedSeed, 0) !== n.reservedSeeds
      || !Array.isArray(c.tools) || !c.tools.every(t => forestTool(t) && t.ownerActorId === m.actorId && t.stateVersion <= w.observedStateVersion)
      || new Set(c.tools.map(t => t.toolId)).size !== c.tools.length) return false;
    const expected = [{ id: "nursery-west", kind: "forestry_nursery", position: [7, 6], radius: .3 },
      ...c.plants.map(p => ({ id: p.plantId, kind: "forestry_tree", position: forestPlots[p.plotId], radius: .45 }))];
    const obstacles = w.terrain.obstacles.filter(o => ["forestry_nursery", "forestry_tree"].includes(o.kind));
    return obstacles.length === expected.length && expected.every(e => obstacles.filter(o => exact(o, e)).length === 1)
      && c.reservations.every(r => !["growing", "harvesting"].includes(r.status)
        || c.plants.some(p => p.plantId === r.plantId && p.plotId === r.plotId && (p.state === "growing") === (r.status === "growing")));
  }
  function forestryAssess(data) {
    const { mission: m, facts: f, budget: b, steps, world: w } = data;
    const uses = m.forestryVersion !== undefined || m.goal?.forestry !== undefined;
    if (!uses) return { uses: false, consistent: true, verified: false, complete: true };
    try {
      const task = m.goal.forestry, action = task.action, cost = forestCost(action), records = [], ids = new Set();
      let consistent = m.forestryVersion === 1 && m.rulesVersion === "r10" && m.preconditionMode === "actor-state-v1"
        && task.worldInstanceId === m.worldInstanceId && task.actorId === m.actorId && m.allowBuild === false
        && Object.entries(forestryPermissions).every(([kind, p]) => m[p] === (kind === action.type))
        && b.used.commands === steps.length && b.used.modelCalls === 0 && b.limits.modelCalls === 0
        && b.used.queries >= 1 + steps.length && ["commands", "queries", ...forestMaterials].every(k => b.used[k] <= b.limits[k])
        && integer(w.observedStateVersion) && w.observedStateVersion <= f.endStateVersion && forestObservation(w, m)
        && fields(w.observedSelf, "actorId position inventoryWood seeds") && w.observedSelf.actorId === m.actorId
        && point(w.observedSelf.position) && wood(w.observedSelf.inventoryWood) && integer(w.observedSelf.seeds);
      const envelope = r => object(r) && r.schemaVersion === 1 && r.rulesVersion === "r10" && r.identity?.actorId === m.actorId
        && r.identity?.operatorId === m.operatorId && integer(r.stateVersion) && integer(r.eventCursor) && r.error === null;
      let position = m.origin, inventory = steps[0]?.before?.inventoryWood, seeds = steps[0]?.before?.seeds, version = f.startStateVersion;
      for (const [index, s] of steps.entries()) {
        const q = s.request, before = s.before, r = s.receipt;
        consistent &&= s.index === index + 1 && !ids.has(s.commandId) && identifier(s.commandId) && object(before)
          && before.worldInstanceId === m.worldInstanceId && before.actorId === m.actorId && before.operatorId === m.operatorId
          && exact(before.position, position) && wood(before.inventoryWood) && before.inventoryWood === inventory
          && integer(before.seeds) && before.seeds === seeds && integer(before.stateVersion) && before.stateVersion >= version
          && fields(q, "schemaVersion rulesVersion commandId expectedStateVersion preconditionMode action")
          && q.schemaVersion === 1 && q.rulesVersion === "r10" && q.commandId === s.commandId && exact(q.action, s.action)
          && q.preconditionMode === m.preconditionMode && q.expectedStateVersion === version && s.expectedStateVersion === version;
        ids.add(s.commandId);
        if (s.status !== "committed") {
          consistent &&= index === steps.length - 1 && s.forestryEvidence === null && s.forestryProof === null
            && exact(s.position, position) && s.inventoryWood === inventory && s.seeds === seeds;
          continue;
        }
        consistent &&= envelope(r) && r.status === "committed" && r.commandId === s.commandId && r.stateVersion === s.stateVersion
          && s.receiptInstanceId === m.worldInstanceId && exact(r.execution, s.execution) && r.result?.action === s.action.type
          && r.execution?.observedStateVersion === version && r.execution?.appliedOnStateVersion >= before.stateVersion;
        if (s.action.type === "walk") {
          const end = r.result?.position;
          consistent &&= fields(s.action, "type to") && point(s.action.to) && point(end) && r.result.blocked === false && s.blocked === false
            && number(before.maxStepDistance) && before.maxStepDistance > 0 && before.maxStepDistance <= .6
            && distance(position, end) <= before.maxStepDistance + 1e-6
            && distance(position, end) + distance(end, s.action.to) <= distance(position, s.action.to) + 1e-6
            && s.forestryProof === null && s.forestryEvidence === null;
          position = end;
        } else {
          const p = s.forestryProof, d = r.result?.forestryAction;
          consistent &&= forestryAction(s.action) && exact(s.action, action) && fields(r.result, "action forestryAction")
            && fields(d, "capabilityVersion authorActorId operatorId commandId action position serviceMs stateVersion eventCursor completedAtUtc inventoryWoodBefore inventoryWood seedsBefore seeds nurseryStockBefore nurseryStock reservationBefore reservation plantBefore plant tool")
            && d.capabilityVersion === 1 && d.authorActorId === m.actorId && d.operatorId === m.operatorId && d.commandId === s.commandId
            && exact(d.action, action) && exact(before.action, action) && exact(d.position, position) && d.inventoryWoodBefore === inventory && d.seedsBefore === seeds
            && wood(d.inventoryWood) && integer(d.seeds) && integer(d.serviceMs) && d.serviceMs >= before.serviceMs
            && integer(d.nurseryStockBefore) && d.nurseryStockBefore <= 4 && integer(d.nurseryStock) && d.nurseryStock <= 4
            && d.inventoryWood === inventory - cost.wood + cost.woodHarvested && d.seeds === seeds + cost.seedsCollected - cost.seedsPlanted + cost.seedsHarvested
            && d.nurseryStock === d.nurseryStockBefore - cost.seedsCollected
            && d.stateVersion === s.stateVersion && d.eventCursor === r.eventCursor && Number.isFinite(Date.parse(d.completedAtUtc))
            && fields(p, "receiptInstanceId detailInstanceId eventInstanceId detail events")
            && [p.receiptInstanceId, p.detailInstanceId, p.eventInstanceId].every(v => v === m.worldInstanceId)
            && envelope(p.detail) && envelope(p.events) && exact(p.detail.forestryAction, d)
            && exact(s.forestryEvidence, { worldInstanceId: m.worldInstanceId, ...d })
            && [p.detail, p.events].every(v => v.stateVersion >= d.stateVersion && v.eventCursor >= d.eventCursor)
            && Array.isArray(p.events.events) && exact(p.events.events.filter(e => e.seq === d.eventCursor), [{ seq: d.eventCursor,
              stateVersion: d.stateVersion, actorId: m.actorId, commandId: s.commandId, type: "forestryActionCompleted", forestryAction: d }])
            && [d.reservationBefore, d.reservation].every(v => v === null || forestReservation(v))
            && [d.plantBefore, d.plant].every(v => v === null || forestPlant(v)) && (d.tool === null || forestTool(d.tool))
            && exact(before.adoption, w.forestry.adoption)
            && ["toolIds", "plantIds", "reservationIds"].every(k => Array.isArray(before[k]) && before[k].every(identifier) && new Set(before[k]).size === before[k].length);
          const rb = d.reservationBefore, ra = d.reservation, pb = d.plantBefore, pa = d.plant, tool = d.tool;
          const remote = ["reserve_forest", "cancel_forest_reservation"].includes(action.type);
          consistent &&= remote ? before.target === null && exact(m.goal.target, m.origin) : exact(before.target.position, m.goal.target) && distance(position, m.goal.target) <= 1.6 + 1e-8;
          if (action.type === "craft_forestry_tool") consistent &&= [rb, ra, pb, pa].every(v => v === null)
            && workshopEntity(before.target) && before.target.definitionId === "workbench" && before.target.entityId === action.entityId
            && forestTool(tool) && !before.toolIds.includes(tool.toolId) && tool.ownerActorId === m.actorId && tool.workbenchId === action.entityId
            && tool.commandId === s.commandId && tool.stateVersion === d.stateVersion && tool.eventCursor === d.eventCursor;
          else if (action.type === "reserve_forest") consistent &&= [rb, pb, pa, tool].every(v => v === null) && forestReservation(ra)
            && ra.status === "queued" && !before.reservationIds.includes(ra.reservationId) && ra.actorId === m.actorId && ra.operatorId === m.operatorId
            && ra.commandId === s.commandId && ra.requestedAtMs === d.serviceMs && ra.queueOrder === d.eventCursor;
          else {
            consistent &&= forestReservation(rb) && forestReservation(ra) && rb.reservationId === action.reservationId
              && rb.actorId === m.actorId && rb.operatorId === m.operatorId && before.reservationIds.includes(rb.reservationId)
              && exact(subset(rb, reservationIdentityKeys), before.reservationIdentity) && exact(subset(ra, reservationIdentityKeys), before.reservationIdentity)
              && (rb.expiresAtMs === null || d.serviceMs < rb.expiresAtMs);
            if (action.type === "cancel_forest_reservation") consistent &&= ["queued", "preparing"].includes(rb.status) && ra.status === "cancelled"
              && (before.reservation.status !== "preparing" || exact(rb, before.reservation)) && [pb, pa, tool].every(v => v === null)
              && exact(ra, { ...rb, status: "cancelled", reservedSeed: 0, expiresAtMs: ra.expiresAtMs }) && [null, rb.expiresAtMs].includes(ra.expiresAtMs);
            else {
              consistent &&= exact(rb, before.reservation);
              if (action.type === "collect_seed") consistent &&= rb.status === "preparing" && rb.reservedSeed === 1
                && exact(ra, { ...rb, reservedSeed: 0 }) && [pb, pa, tool].every(v => v === null)
                && exact(before.target, { sourceId: "nursery-west", position: [7, 6], radius: .3, buildExclusion: forestRectangle([7, 6]) });
              else {
                const plotId = action.type === "plant_tree" ? action.plotId : pb.plotId;
                consistent &&= exact(before.target, { plotId, position: forestPlots[plotId], radius: .45, buildExclusion: forestRectangle(forestPlots[plotId]) }) && rb.plotId === plotId;
                if (action.type === "plant_tree") consistent &&= rb.status === "preparing" && seeds >= 1 && pb === null && tool === null
                  && forestPlant(pa) && !before.plantIds.includes(pa.plantId) && pa.plotId === action.plotId && pa.planterActorId === m.actorId
                  && pa.operatorId === m.operatorId && pa.reservationId === action.reservationId && pa.commandId === s.commandId
                  && pa.plantedAtMs === d.serviceMs && pa.stateVersion === d.stateVersion && pa.eventCursor === d.eventCursor && pa.state === "growing"
                  && exact(ra, { ...rb, status: "growing", plantId: pa.plantId, reservedSeed: 0, expiresAtMs: null });
                else consistent &&= rb.status === "harvesting" && rb.plantId === action.plantId && pb.state === "mature" && pb.plantId === action.plantId
                  && exact(pb, before.plant) && exact(subset(pb, plantIdentityKeys), before.plantIdentity) && d.serviceMs >= pb.maturesAtMs
                  && before.plantIds.includes(pb.plantId) && forestTool(tool) && exact(tool, before.tool) && tool.toolId === action.toolId && tool.ownerActorId === m.actorId
                  && before.toolIds.includes(tool.toolId) && exact(pa, { ...pb, state: "harvested", standingWood: 0, harvestActorId: m.actorId,
                    harvestCommandId: s.commandId, harvestEventCursor: d.eventCursor })
                  && exact(ra, { ...rb, status: "completed", reservedSeed: 0, expiresAtMs: ra.expiresAtMs }) && [null, rb.expiresAtMs].includes(ra.expiresAtMs);
              }
            }
          }
          inventory = d.inventoryWood; seeds = d.seeds; records.push(s.forestryEvidence);
        }
        version = s.stateVersion;
        consistent &&= exact(s.position, position) && s.inventoryWood === inventory && s.seeds === seeds;
      }
      const actualPosition = w.observedStateVersion >= version ? w.observedSelf.position : position;
      const record = records[0], done = records.length === 1, returned = distance(actualPosition, m.origin) <= .06;
      consistent &&= records.length <= 1 && f.forestryCompleted === done && f.goalReached === done && f.returned === returned
        && exact(f.forestryAction, record ?? null) && forestMaterials.every(k => b.used[k] === (done ? cost[k] : 0))
        && forestMaterials.filter(k => k !== "wood").every(k => f[k] === (done ? cost[k] : 0))
        && exact(f.createdEntityIds, []) && exact(f.createdToolIds, done && action.type === "craft_forestry_tool" ? [record.tool.toolId] : [])
        && exact(f.createdPlantIds, done && action.type === "plant_tree" ? [record.plant.plantId] : [])
        && exact(f.createdReservationIds, done && action.type === "reserve_forest" ? [record.reservation.reservationId] : [])
        && (!done || b.used.queries >= steps.length + 3);
      return { uses, consistent: Boolean(consistent), verified: Boolean(consistent && done),
        complete: Boolean(consistent && done && (!task.returnToOrigin || returned) && steps.every(s => s.status === "committed")) };
    } catch { return { uses, consistent: false, verified: false, complete: false }; }
  }
  function workshopAction(a) {
    if (!object(a) || a.capabilityVersion !== 1 || !Object.hasOwn(workshopPermissions, a.type)) return false;
    if (a.type === "build_workshop") return fields(a, "type capabilityVersion recipeId at toolId") && point(a.at)
      && (a.recipeId === "workbench.v1" && a.toolId === null || a.recipeId === "wooden_chest.v1" && identifier(a.toolId));
    if (a.type === "craft_tool") return fields(a, "type capabilityVersion entityId recipeId") && identifier(a.entityId) && a.recipeId === "wooden_mallet.v1";
    return fields(a, "type capabilityVersion entityId quantity") && identifier(a.entityId) && wood(a.quantity) && a.quantity > 0;
  }
  function workshopEntity(e) {
    return fields(e, "entityId definitionId definitionVersion rulesVersion ownerActorId position embodiedWood")
      && identifier(e.entityId) && identifier(e.ownerActorId) && ["workbench", "wooden_chest"].includes(e.definitionId)
      && e.definitionVersion === 1 && e.rulesVersion === "r10" && point(e.position) && e.embodiedWood === 3;
  }
  function workshopTool(t) {
    return fields(t, "toolId definitionId definitionVersion ownerActorId embodiedWood workbenchId commandId stateVersion eventCursor")
      && [t.toolId, t.ownerActorId, t.workbenchId, t.commandId].every(identifier)
      && t.definitionId === "wooden_mallet" && t.definitionVersion === 1 && t.embodiedWood === 1
      && integer(t.stateVersion) && integer(t.eventCursor) && t.eventCursor > 0;
  }
  function workshopAssess(data) {
    const { mission: m, facts: f, budget: b, steps } = data;
    const uses = m.workshopVersion !== undefined || m.goal?.workshop !== undefined;
    if (!uses) return { uses: false, verified: false, consistent: true, complete: true };
    try {
      const task = m.goal.workshop, action = task.action, records = [], ids = new Set();
      let consistent = m.workshopVersion === 1 && m.rulesVersion === "r10" && m.preconditionMode === "actor-state-v1"
        && task.worldInstanceId === m.worldInstanceId && task.actorId === m.actorId && m.allowBuild === false
        && Object.entries(workshopPermissions).every(([kind, p]) => m[p] === (kind === action.type))
        && b.used.commands === steps.length && b.used.modelCalls === 0 && b.limits.modelCalls === 0
        && b.used.queries >= 1 + steps.length && ["commands", "queries", "wood", "woodMoved"].every(k => b.used[k] <= b.limits[k])
        && integer(data.world.observedStateVersion) && data.world.observedStateVersion <= f.endStateVersion
        && fields(data.world.observedSelf, "actorId position inventoryWood") && data.world.observedSelf.actorId === m.actorId
        && point(data.world.observedSelf.position) && wood(data.world.observedSelf.inventoryWood);
      const envelope = r => object(r) && r.schemaVersion === 1 && r.rulesVersion === "r10" && r.identity?.actorId === m.actorId
        && r.identity?.operatorId === m.operatorId && integer(r.stateVersion) && integer(r.eventCursor);
      let position = m.origin, inventory = steps[0]?.before?.inventoryWood, version = f.startStateVersion;
      for (const [index, s] of steps.entries()) {
        const q = s.request, before = s.before, r = s.receipt;
        consistent &&= s.index === index + 1 && !ids.has(s.commandId) && identifier(s.commandId) && object(before)
          && before.worldInstanceId === m.worldInstanceId && before.actorId === m.actorId && before.operatorId === m.operatorId
          && exact(before.position, position) && wood(before.inventoryWood) && before.inventoryWood === inventory
          && integer(before.stateVersion) && before.stateVersion >= version
          && fields(q, "schemaVersion rulesVersion commandId expectedStateVersion preconditionMode action")
          && q.schemaVersion === 1 && q.rulesVersion === "r10" && q.commandId === s.commandId && exact(q.action, s.action)
          && q.preconditionMode === m.preconditionMode && q.expectedStateVersion === version && s.expectedStateVersion === version;
        ids.add(s.commandId);
        if (s.status !== "committed") {
          consistent &&= index === steps.length - 1 && s.workshopEvidence === null && s.workshopProof === null
            && exact(s.position, position) && s.inventoryWood === inventory;
          continue;
        }
        consistent &&= envelope(r) && r.error === null && r.commandId === s.commandId && r.stateVersion === s.stateVersion
          && s.receiptInstanceId === m.worldInstanceId && exact(r.execution, s.execution) && r.result?.action === s.action.type
          && r.execution?.observedStateVersion === version && r.execution?.appliedOnStateVersion >= before.stateVersion;
        if (s.action.type === "walk") {
          const end = r.result?.position;
          consistent &&= point(end) && r.result.blocked === false && s.blocked === false && number(before.maxStepDistance)
            && before.maxStepDistance > 0 && before.maxStepDistance <= .6 && distance(position, end) <= before.maxStepDistance + 1e-6
            && distance(position, end) + distance(end, s.action.to) <= distance(position, s.action.to) + 1e-6
            && s.workshopProof === null && s.workshopEvidence === null;
          position = end;
        } else {
          const p = s.workshopProof, d = r.result?.workshopAction;
          consistent &&= workshopAction(s.action) && exact(s.action, action) && fields(r.result, "action workshopAction")
            && fields(d, "capabilityVersion authorActorId operatorId commandId action entity tool quantity inventoryWoodBefore inventoryWood storedWoodBefore storedWood position stateVersion eventCursor completedAtUtc")
            && d.capabilityVersion === 1 && d.authorActorId === m.actorId && d.operatorId === m.operatorId && d.commandId === s.commandId
            && exact(d.action, action) && exact(before.action, action) && exact(d.position, position)
            && d.inventoryWoodBefore === inventory && wood(d.inventoryWood) && wood(d.quantity) && d.quantity > 0
            && d.stateVersion === s.stateVersion && d.eventCursor === r.eventCursor && Number.isFinite(Date.parse(d.completedAtUtc))
            && fields(p, "receiptInstanceId detailInstanceId eventInstanceId detail events")
            && [p.receiptInstanceId, p.detailInstanceId, p.eventInstanceId].every(v => v === m.worldInstanceId)
            && envelope(p.detail) && envelope(p.events) && p.detail.error === null && p.events.error === null
            && exact(p.detail.workshopAction, d) && exact(s.workshopEvidence, { worldInstanceId: m.worldInstanceId, ...d })
            && [p.detail, p.events].every(v => v.stateVersion >= d.stateVersion && v.eventCursor >= d.eventCursor)
            && Array.isArray(p.events.events) && exact(p.events.events.filter(e => e.seq === d.eventCursor), [{
              seq: d.eventCursor, stateVersion: d.stateVersion, actorId: m.actorId, commandId: s.commandId,
              type: "workshopActionCompleted", workshopAction: d }]) && workshopEntity(d.entity);
          const build = action.type === "build_workshop", craft = action.type === "craft_tool";
          const delta = action.type === "withdraw_wood" ? d.quantity : -d.quantity;
          consistent &&= d.quantity === (build ? 3 : craft ? 1 : action.quantity) && d.inventoryWood === inventory + delta
            && distance(position, m.goal.target) <= (build ? 3.2 : 1.6) + 1e-8;
          if (build) consistent &&= d.entity.ownerActorId === m.actorId && exact(d.entity.position, action.at)
            && d.entity.definitionId === (action.recipeId === "workbench.v1" ? "workbench" : "wooden_chest")
            && Array.isArray(before.entityIds) && !before.entityIds.includes(d.entity.entityId)
            && exact(d.tool, before.tool) && (action.toolId === null ? d.tool === null : workshopTool(d.tool)
              && d.tool.toolId === action.toolId && d.tool.ownerActorId === m.actorId)
            && exact([d.storedWoodBefore, d.storedWood], action.toolId === null ? [null, null] : [0, 0]);
          else {
            consistent &&= exact(d.entity, before.target) && d.entity.entityId === action.entityId && exact(d.entity.position, m.goal.target);
            if (craft) consistent &&= d.entity.definitionId === "workbench" && workshopTool(d.tool) && d.tool.ownerActorId === m.actorId
              && d.tool.workbenchId === action.entityId && d.tool.commandId === s.commandId && d.tool.stateVersion === d.stateVersion
              && d.tool.eventCursor === d.eventCursor && Array.isArray(before.toolIds) && !before.toolIds.includes(d.tool.toolId)
              && d.storedWoodBefore === null && d.storedWood === null;
            else consistent &&= d.entity.definitionId === "wooden_chest" && d.entity.ownerActorId === m.actorId && d.tool === null
              && wood(d.storedWoodBefore) && wood(d.storedWood) && d.storedWoodBefore === before.storedWood
              && d.storedWood === d.storedWoodBefore - delta;
          }
          inventory = d.inventoryWood;
          records.push(s.workshopEvidence);
        }
        version = s.stateVersion;
        consistent &&= exact(s.position, position) && s.inventoryWood === inventory;
      }
      const actualPosition = data.world.observedStateVersion >= version ? data.world.observedSelf.position : position;
      const record = records[0], done = records.length === 1, returned = distance(actualPosition, m.origin) <= .06;
      consistent &&= records.length <= 1 && f.workshopCompleted === done && f.goalReached === done && f.returned === returned
        && exact(f.workshopAction, record ?? null) && b.used.wood === (done ? action.type === "build_workshop" ? 3 : action.type === "craft_tool" ? 1 : 0 : 0)
        && b.used.woodMoved === (done && ["deposit_wood", "withdraw_wood"].includes(action.type) ? action.quantity : 0)
        && f.woodDeposited === (done && action.type === "deposit_wood" ? action.quantity : 0)
        && f.woodWithdrawn === (done && action.type === "withdraw_wood" ? action.quantity : 0)
        && exact(f.createdEntityIds, done && action.type === "build_workshop" ? [record.entity.entityId] : [])
        && exact(f.createdToolIds, done && action.type === "craft_tool" ? [record.tool.toolId] : [])
        && (!done || b.used.queries >= steps.length + 3);
      return { uses, consistent: Boolean(consistent), verified: Boolean(consistent && done),
        complete: Boolean(consistent && done && (!task.returnToOrigin || returned) && steps.every(s => s.status === "committed")) };
    } catch { return { uses, consistent: false, verified: false, complete: false }; }
  }

  function validate(data) {
    require(object(data), "报告根节点必须是 JSON 对象。");
    require(data.schemaVersion === 1 && data.kind === "resident-mission-report", "文件不是受支持的居民任务报告（需要 schemaVersion 1）。");
    const { mission: m, budget: b, facts: f, world: w, decision: d, feedback } = data;
    require(object(m) && object(b) && object(f) && object(w) && object(feedback), "报告缺少 mission、budget、facts、world 或 feedback 对象。");
    require(string(m.id) && /^[A-Za-z0-9_-]{1,64}$/.test(m.id), "任务编号必须为 1—64 位字母、数字、下划线或短横线。");
    require(string(m.objective) && m.objective.length > 0 && Array.from(m.objective).length <= 500, "任务目的应为 1—500 字符。");
    require([m.actorId, m.worldId, m.rulesVersion, m.reason].every(string), "任务身份、世界、规则版本或状态原因格式不正确。");
    require(Object.hasOwn(statuses, m.status), "报告包含不支持的任务状态。");
    require(integer(w.width) && integer(w.height) && w.width >= 1 && w.height >= 1 && w.width <= 128 && w.height <= 128, "地图尺寸应为 1—128 的整数。");
    const free = continuous(w), maxCommands = free ? 1000 : 100;
    const workshop = m.workshopVersion !== undefined || m.goal?.workshop !== undefined;
    const forestry = m.forestryVersion !== undefined || m.goal?.forestry !== undefined;
    if (forestry) {
      const task = m.goal?.forestry;
      require(!workshop && m.forestryVersion === 1 && fields(task, "worldInstanceId actorId action waitForReady returnToOrigin") && forestryAction(task.action)
        && task.worldInstanceId === m.worldInstanceId && task.actorId === m.actorId && [task.returnToOrigin, task.waitForReady].every(v => typeof v === "boolean")
        && m.allowBuild === false && Object.entries(forestryPermissions).every(([kind, p]) => m[p] === (kind === task.action.type))
        && identifier(m.operatorId), "林业任务须绑定原实例、居民、单一动作、等待与返回选项和独立权限。");
      require(object(b.limits) && object(b.used) && b.limits.modelCalls === 0 && b.used.modelCalls === 0
        && forestMaterials.every(k => integer(b.limits[k]) && b.limits[k] <= (k.startsWith("seeds") ? 4 : 12) && integer(b.used[k]))
        && integer(b.limits.queries) && b.limits.queries >= 1 && b.limits.queries <= 5000 && integer(b.used.queries), "林业固定任务需要零模型、独立木材树种与累计查询预算。");
      require(typeof f.forestryCompleted === "boolean" && forestMaterials.filter(k => k !== "wood").every(k => integer(f[k]))
        && ["createdToolIds", "createdPlantIds", "createdReservationIds"].every(k => Array.isArray(f[k]) && f[k].every(identifier)), "林业动作事实或材料计数格式不正确。");
    }
    if (workshop) {
      const task = m.goal?.workshop;
      require(m.workshopVersion === 1 && fields(task, "worldInstanceId actorId action returnToOrigin") && workshopAction(task.action)
        && task.worldInstanceId === m.worldInstanceId && task.actorId === m.actorId && typeof task.returnToOrigin === "boolean"
        && m.allowBuild === false && Object.entries(workshopPermissions).every(([kind, p]) => m[p] === (kind === task.action.type))
        && identifier(m.operatorId), "工坊任务须绑定原实例、居民、单一动作和对应独立权限。");
      require(b.limits.modelCalls === 0 && b.used.modelCalls === 0 && [b.limits.woodMoved, b.used.woodMoved].every(wood)
        && integer(b.limits.queries) && b.limits.queries >= 1 && b.limits.queries <= 5000 && integer(b.used.queries), "工坊固定任务需要零模型、独立存取量与累计查询预算。");
      require(typeof f.workshopCompleted === "boolean" && [f.woodDeposited, f.woodWithdrawn].every(wood)
        && Array.isArray(f.createdToolIds) && f.createdToolIds.every(identifier), "工坊动作事实或存取量格式不正确。");
    }
    const actorState = m.preconditionMode === "actor-state-v1";
    require(m.preconditionMode === undefined || m.preconditionMode === null || actorState, "任务的动作前置模式不受支持。");
    require(!actorState || free && ["r8", "r9", "r10"].includes(m.rulesVersion) && /^w_[0-9a-f]{32}$/.test(m.worldInstanceId)
      && w.instanceId === m.worldInstanceId, "按居民状态执行的报告必须绑定原连续世界实例。");
    const cell = (value) => Array.isArray(value) && value.length === 2 && value.every(free ? number : integer) && value[0] < w.width && value[1] < w.height;
    require(!free || ["r8", "r9", "r10"].includes(m.rulesVersion) && m.arrivalTolerance === .06, "连续坐标报告需要连续规则与 0.06 米到达容差。");
    require(!free || (m.rulesVersion === "r8" && w.scenarioId === undefined)
      || w.scenarioId === ({ r8: "wilderness-continuous-v1", r9: "wilderness-cooperation-v1", r10: "wilderness-material-access-v1" })[m.rulesVersion], "报告场景与原任务规则不一致。");
    require(cell(m.origin), "任务起点不是有效图内坐标。");
    require(m.goal === null || (object(m.goal) && string(m.goal.id) && string(m.goal.label) && cell(m.goal.target)), "任务目标格式不正确；未选择目标时应为 null。");
    require(m.goal?.activityId === undefined || string(m.goal.activityId), "活动目标编号格式不正确。");
    require(m.goal?.buildRecipeId === undefined || free && Object.hasOwn(structures, m.goal.buildRecipeId) && !m.goal.activityId, "建设目标需要连续世界的有效配方。");
    require(m.sharePostcard === undefined || typeof m.sharePostcard === "boolean", "任务分享要求应为布尔值。");
    require(m.allowGather === undefined || typeof m.allowGather === "boolean", "采集权限应为布尔值。");
    require(m.allowBuild === undefined || typeof m.allowBuild === "boolean", "建造权限应为布尔值。");
    require(m.allowTransfer === undefined || typeof m.allowTransfer === "boolean", "赠送权限应为布尔值。");
    const transferSpec = t => object(t) && string(t.recipientActorId) && /^[A-Za-z0-9_-]{1,128}$/.test(t.recipientActorId)
      && t.resource === "wood" && integer(t.quantity) && t.quantity >= 1 && t.quantity <= 12;
    require(m.goal?.transfer === undefined || ["r9", "r10"].includes(m.rulesVersion) && transferSpec(m.goal.transfer)
      && m.goal.transfer.recipientActorId !== m.actorId
      && !m.goal.activityId && !m.goal.buildRecipeId, "赠送目标需要另一位收件人、木材数量和独立会面点。");
    require(m.paintMosaic === undefined || typeof m.paintMosaic === "boolean", "画布创作要求应为布尔值。");
    require(m.proposeMosaic === undefined || typeof m.proposeMosaic === "boolean", "提议要求应为布尔值。");
    require(m.reviewMosaicProposal === undefined || m.reviewMosaicProposal === null || (object(m.reviewMosaicProposal) && string(m.reviewMosaicProposal.proposalActorId) && string(m.reviewMosaicProposal.proposalCommandId)), "审阅提议引用不完整。");
    require(d === null || (object(d) && string(d.goalId) && string(d.reason) && object(d.provider) && Object.hasOwn(providers, d.provider.kind) && string(d.provider.model) && object(d.provider.usage)), "目标决策格式不正确；未作选择时 decision 应为 null。");
    require(d?.postcardText === undefined || postcardText(d.postcardText), "手记草稿应为 1—160 字且不含控制字符。");
    require(d?.mosaicPatch === undefined || (mosaic.validPatch(d.mosaicPatch) && integer(d.mosaicBaseRevision)), "画布草图需要 1—8 个有效格子与原画布版本。");
    require(d?.proposalText === undefined || consent.text(d.proposalText), "提议草稿文本不正确。");
    require(d?.mosaicProposal === undefined || consent.validProposal(d.mosaicProposal), "原提议不完整。");
    require(d?.reviewDecision === undefined || ["accept", "reject"].includes(d.reviewDecision), "审阅决定不正确。");
    require(d?.reviewText === undefined || consent.text(d.reviewText), "审阅理由不正确。");
    require(f.mosaicProposed === undefined || typeof f.mosaicProposed === "boolean", "提议事实应为布尔值。");
    require(f.mosaicReviewed === undefined || typeof f.mosaicReviewed === "boolean", "审阅事实应为布尔值。");
    require(f.mosaicProposal === undefined || f.mosaicProposal === null || consent.validProposal(f.mosaicProposal), "提议记录不完整。");
    require(f.mosaicReview === undefined || f.mosaicReview === null || consent.validReview(f.mosaicReview), "审阅记录不完整。");
    require(object(b.limits) && object(b.used), "预算必须包含 limits 与 used。");
    require(["commands", "wood", "modelCalls"].every((key) => integer(b.limits[key]) && integer(b.used[key])) && number(b.limits.seconds) && number(b.used.seconds), "预算上限与累计值必须是非负数字，次数和木材必须是整数。");
    require(b.limits.commands >= 1 && b.limits.commands <= maxCommands && b.limits.wood <= 12 && b.limits.modelCalls === (workshop || forestry ? 0 : 1) && integer(b.limits.seconds) && b.limits.seconds >= 1 && b.limits.seconds <= 600, `任务预算上限不符合契约（命令 1—${maxCommands}、木材 0—12、时间 1—600 秒）。`);
    require(typeof f.goalReached === "boolean" && typeof f.returned === "boolean" && integer(f.woodClaimed), "到达、返回或领取木材事实的类型不正确。");
    require(f.woodGathered === undefined || integer(f.woodGathered), "采集木材事实须为非负整数。");
    require(f.woodTransferred === undefined || integer(f.woodTransferred), "赠送木材事实须为非负整数。");
    require(f.transferCompleted === undefined || typeof f.transferCompleted === "boolean", "赠送完成事实应为布尔值。");
    require(f.transfer === undefined || f.transfer === null || transferSpec(f.transfer)
      && [f.transfer.commandId, f.transfer.senderActorId, f.transfer.worldInstanceId].every(v => string(v) && v.length > 0)
      && cell(f.transfer.position) && integer(f.transfer.stateVersion)
      && integer(f.transfer.inventoryWoodBefore) && f.transfer.inventoryWoodBefore <= 12
      && integer(f.transfer.inventoryWoodAfter) && f.transfer.inventoryWoodAfter <= 12,
    "赠送完成记录缺少原命令、双方身份或库存依据。");
    require(f.constructionBuilt === undefined || typeof f.constructionBuilt === "boolean", "设施建造事实应为布尔值。");
    require(f.construction === undefined || f.construction === null || object(f.construction)
      && [f.construction.commandId, f.construction.entityId, f.construction.ownerActorId].every(v => string(v) && v.length > 0)
      && Object.hasOwn(structures, f.construction.recipeId) && f.construction.definitionId === structures[f.construction.recipeId].definition
      && cell(f.construction.position) && f.construction.woodSpent === structures[f.construction.recipeId].wood
      && integer(f.construction.stateVersion), "设施建造记录不完整。");
    require(f.activityCompleted === undefined || typeof f.activityCompleted === "boolean", "到访完成事实应为布尔值。");
    require(f.activityVisit === undefined || f.activityVisit === null || (object(f.activityVisit) && string(f.activityVisit.activityId) && string(f.activityVisit.commandId) && integer(f.activityVisit.stateVersion) && cell(f.activityVisit.position) && string(f.activityVisit.visitedAtUtc) && Number.isFinite(Date.parse(f.activityVisit.visitedAtUtc))), "到访回执记录不完整。");
    require(f.postcardShared === undefined || typeof f.postcardShared === "boolean", "手记分享事实应为布尔值。");
    require(f.mosaicPainted === undefined || typeof f.mosaicPainted === "boolean", "画布绘制事实应为布尔值。");
    require(f.mosaicEdit === undefined || f.mosaicEdit === null || mosaic.validEdit(f.mosaicEdit), "画布修改记录不完整。");
    require(f.postcard === undefined || f.postcard === null || (object(f.postcard) && [f.postcard.activityId, f.postcard.authorActorId, f.postcard.commandId, f.postcard.visitCommandId].every(string)
      && postcardText(f.postcard.text) && integer(f.postcard.stateVersion) && cell(f.postcard.position) && string(f.postcard.sharedAtUtc) && Number.isFinite(Date.parse(f.postcard.sharedAtUtc))), "手记分享记录不完整。");
    require([f.startStateVersion, f.endStateVersion].every((v) => v === null || integer(v)), "状态版本必须为非负整数或 null。");
    require(f.verifiedAtUtc === null || (string(f.verifiedAtUtc) && Number.isFinite(Date.parse(f.verifiedAtUtc))), "核实时间须为有效时间字符串或 null。");
    require(Array.isArray(f.createdEntityIds) && f.createdEntityIds.every(string), "新建设施编号应为字符串数组。");
    if (free) {
      const vertex = (p) => Array.isArray(p) && p.length === 2 && p.every(number) && p[0] <= w.width && p[1] <= w.height;
      require(Array.isArray(w.bounds) && same(w.bounds.slice(0, 2), [0, 0]) && same(w.bounds.slice(2), [w.width, w.height]), "连续地图边界不正确。");
      require(object(w.terrain) && w.terrain.version === 1 && object(w.terrain.river) && Array.isArray(w.terrain.river.polygon) && w.terrain.river.polygon.length >= 3 && w.terrain.river.polygon.every(vertex), "连续河道几何不正确。");
      require(Array.isArray(w.terrain.obstacles) && w.terrain.obstacles.every(o => object(o) && cell(o.position) && number(o.radius) && o.radius > 0), "连续障碍几何不正确。");
      require(Array.isArray(w.resourceNodes) && w.resourceNodes.every(n => object(n) && string(n.nodeId) && cell(n.position) && integer(n.initialWood) && integer(n.remainingWood) && n.remainingWood <= n.initialWood), "自然资源记录不正确。");
    } else require(Array.isArray(w.water) && w.water.every(cell) && Array.isArray(w.blocked) && w.blocked.every(cell), "水面或阻挡位置不是图内整数坐标。");
    require(Array.isArray(w.entities) && w.entities.every((e) => object(e) && cell(e.position) && string(e.entityId) && string(e.definitionId)), "地图设施须包含 entityId、definitionId 与图内 position。");
    require(w.activities === undefined || (Array.isArray(w.activities) && w.activities.every((a) => object(a) && string(a.id) && string(a.label) && cell(a.position))), "地图活动地点格式不正确。");
    require(w.mosaic === undefined || w.mosaic === null || mosaic.validBoard(w.mosaic), "画布快照格式不正确。");
    require(w.mosaicProposals === undefined || (Array.isArray(w.mosaicProposals) && w.mosaicProposals.every(consent.validProposal)), "提议快照格式不正确。");
    require(w.recentTransfers === undefined || ["r9", "r10"].includes(m.rulesVersion) && object(w.recentTransfers)
      && w.recentTransfers.limit === 20 && typeof w.recentTransfers.truncated === "boolean"
      && Array.isArray(w.recentTransfers.items) && w.recentTransfers.items.length <= 20
      && w.recentTransfers.items.every((e, i, all) => transferSpec(e) && e.type === "woodTransferred"
        && string(e.actorId) && string(e.commandId) && integer(e.seq) && integer(e.stateVersion)
        && e.seq === e.stateVersion + 1 && e.stateVersion <= f.endStateVersion
        && (e.actorId === m.actorId || e.recipientActorId === m.actorId) && e.actorId !== e.recipientActorId
        && (i === 0 || all[i - 1].seq < e.seq)), "最近交付快照缺少原事件身份、序号或截断标记。");
    require(Array.isArray(data.steps) && data.steps.length <= maxCommands, `步骤必须是数组，最多允许 ${maxCommands} 条。`);
    data.steps.forEach((step, i) => {
      const prefix = `第 ${i + 1} 条步骤`;
      require(object(step) && integer(step.index) && step.index >= 1 && (i === 0 || step.index > data.steps[i - 1].index), `${prefix}的序号须为递增的正整数。`);
      require(string(step.commandId) && object(step.action) && string(step.action.type) && string(step.reason) && string(step.status), `${prefix}缺少命令、动作、原因或状态。`);
      require(step.position === null || cell(step.position), `${prefix}的位置应为有效图内坐标或 null。`);
      require(step.stateVersion === null || integer(step.stateVersion), `${prefix}的状态版本格式不正确。`);
      require(step.inventoryWood === null || integer(step.inventoryWood), `${prefix}的木材库存格式不正确。`);
      if (actorState) {
        require(step.preconditionMode === m.preconditionMode && integer(step.expectedStateVersion)
          && (["walk", "gather", "build"].includes(step.action.type) || ["r9", "r10"].includes(m.rulesVersion) && step.action.type === "transfer" || m.rulesVersion === "r10" && (forestry && forestryAction(step.action) || workshop && workshopAction(step.action) || window.MaterialReport.action(step.action) || window.EntityNoteReport.action(step.action) || window.EntityCanvasReport.action(step.action))), `${prefix}缺少原命令的前置模式或观察版本。`);
        if (["committed", "rejected"].includes(step.status)) {
          const execution = step.execution;
          require(object(execution) && execution.preconditionMode === m.preconditionMode
            && integer(execution.observedStateVersion) && execution.observedStateVersion === step.expectedStateVersion
            && integer(execution.appliedOnStateVersion), `${prefix}的原命令执行依据不完整。`);
          require(step.status === "committed"
            ? execution.appliedOnStateVersion >= step.expectedStateVersion && step.stateVersion === execution.appliedOnStateVersion + 1
            : step.stateVersion === execution.appliedOnStateVersion
              && (execution.appliedOnStateVersion >= step.expectedStateVersion || step.errorCode === "STATE_VERSION_AHEAD"),
          `${prefix}的实际执行版本与终态不一致。`);
        } else require(step.execution === null, `${prefix}结果未确认，不能带有已确认执行依据。`);
      } else require(!Object.hasOwn(step, "preconditionMode") && !Object.hasOwn(step, "execution"),
        `${prefix}的执行模式与原任务不一致。`);
      if (step.action.quantity !== undefined) require(integer(step.action.quantity), `${prefix}的材料数量须为非负整数。`);
      if (step.action.position !== undefined) require(cell(step.action.position), `${prefix}的动作位置不是图内整数坐标。`);
      if (step.action.at !== undefined) require(cell(step.action.at), `${prefix}的建造位置不是有效图内坐标。`);
      if (step.action.type === "walk") require(free && cell(step.action.to) && (step.blocked === undefined || typeof step.blocked === "boolean"), `${prefix}的连续行走目标或碰撞结果不正确。`);
      if (step.action.direction !== undefined) require(string(step.action.direction), `${prefix}的移动方向格式不正确。`);
      if (step.action.definitionId !== undefined) require(string(step.action.definitionId), `${prefix}的配方编号格式不正确。`);
      if (step.action.recipeId !== undefined) require(string(step.action.recipeId), `${prefix}的配方格式不正确。`);
      if (step.action.activityId !== undefined) require(string(step.action.activityId), `${prefix}的活动编号格式不正确。`);
      if (step.action.type === "gather") require(string(step.action.nodeId) && step.action.nodeId.length > 0, `${prefix}缺少采集来源。`);
      if (step.action.type === "transfer") require(["r9", "r10"].includes(m.rulesVersion) && transferSpec(step.action), `${prefix}缺少原收件人或赠送数量。`);
      if (step.entityId !== undefined) require(string(step.entityId) && step.entityId.length > 0, `${prefix}的设施编号格式不正确。`);
      if (step.action.type === "postcard") require(string(step.action.visitCommandId) && postcardText(step.action.text), `${prefix}的手记或到访关联格式不正确。`);
      if (["mosaic", "mosaic_propose"].includes(step.action.type)) require(string(step.action.visitCommandId) && integer(step.action.expectedMosaicRevision) && mosaic.validPatch(step.action.patch), `${prefix}的画布修改格式不正确。`);
      if (step.action.type === "mosaic_propose") require(consent.text(step.action.text), `${prefix}的提议理由格式不正确。`);
      if (step.action.type === "mosaic_review") require(string(step.action.visitCommandId) && string(step.action.proposalActorId) && string(step.action.proposalCommandId) && ["accept", "reject"].includes(step.action.decision) && consent.text(step.action.text), `${prefix}的审阅格式不正确。`);
      for (const key of ["dx", "dy"]) if (step.action[key] !== undefined) require(Number.isSafeInteger(step.action[key]) && Math.abs(step.action[key]) <= 1, `${prefix}的移动偏移格式不正确。`);
    });
    require(string(feedback.summary) && [feedback.issues, feedback.suggestions].every((v) => Array.isArray(v) && v.every(string)), "执行反馈须包含 summary 及字符串数组 issues、suggestions。");
    window.MaterialReport.validate(data, require);
    window.EntityNoteReport.validate(data, require);
    window.EntityCanvasReport.validate(data, require);
    return data;
  }

  function readJson(text) {
    let parsed;
    try { parsed = JSON.parse(text.replace(/^\uFEFF/, "")); }
    catch { throw new Error("文件不是有效 JSON，请检查格式后重新导入。"); }
    return validate(parsed);
  }

  function setMessage(message, tone = "neutral") {
    put("load-message", message);
    $("load-message").dataset.tone = tone;
  }

  function loadingError(error, prefix) {
    const message = error.name === "AbortError" ? "读取超时，请重试或导入自己的报告。" : error.message;
    setMessage(`${prefix}：${message}${report ? " 当前仍显示上一份有效报告。" : " 可以使用上方文件选择器导入自己的报告。"}`, "error");
  }

  async function loadDemo() {
    const current = ++generation;
    request?.abort();
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    setMessage("正在读取本地运行样例，也可以直接导入自己的报告。");
    try {
      const response = await fetch(`/reports/${DEMO_FILE}`, { signal: controller.signal, cache: "no-store", credentials: "omit" });
      require(response.ok, `运行样例暂不可用（HTTP ${response.status}）。`);
      require(Number(response.headers.get("content-length") || 0) <= MAX_BYTES, "报告超过 2 MiB 限制。");
      require(response.body, "浏览器未能读取样例内容。");
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8", { fatal: true });
      let size = 0, text = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BYTES) { await reader.cancel(); throw new Error("报告超过 2 MiB 限制。"); }
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
      const parsed = readJson(text);
      if (current === generation) showReport(parsed, `运行样例 ${DEMO_FILE}`);
    } catch (error) {
      if (current === generation) loadingError(error, "样例未加载");
    } finally { clearTimeout(timeout); }
  }

  async function loadFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    const current = ++generation;
    request?.abort();
    setMessage("正在检查导入的报告……");
    try {
      require(file.size <= MAX_BYTES, "报告超过 2 MiB 限制，请导出较小的任务报告。");
      const parsed = readJson(await file.text());
      if (current === generation) showReport(parsed, file.name);
    } catch (error) {
      if (current === generation) loadingError(error, "导入失败");
    } finally { event.target.value = ""; }
  }

  function showReport(data, source) {
    report = data;
    const { mission: m, decision: d, facts: f, budget: b } = data;
    const workshop = workshopAssess(data);
    const forestry = forestryAssess(data);
    $("empty-state").hidden = true;
    $("report-content").hidden = false;
    put("mission-id", m.id);
    put("mission-objective", m.objective);
    put("actor-id", m.actorId);
    put("world-identity", `${m.worldId} / ${m.rulesVersion}`);
    put("goal-route", m.goal ? `${coord(m.origin)} → ${m.goal.buildRecipeId ? `建造${structures[m.goal.buildRecipeId].label} · ` : ""}${m.goal.label} ${coord(m.goal.target)}${workshop.uses && !m.goal.workshop.returnToOrigin || forestry.uses && !m.goal.forestry.returnToOrigin ? " · 本任务未要求返程" : " → 起点"}` : `${coord(m.origin)} · 尚未选择目标`);
    put("report-status", statuses[m.status][0]);
    $("report-status").dataset.tone = statuses[m.status][1];
    put("mission-reason", `执行器状态原因：${reasonNames[m.reason] || m.reason || "未提供"}`);
    put("provider-kind", d ? providers[d.provider.kind] : "尚无决策");
    put("chosen-goal", d ? `选择目标：${m.goal?.label || d.goalId} / ${d.goalId}` : "目标选择尚未产生有效结果");
    put("decision-reason", d ? d.reason || "未提供选择理由。" : "报告中没有目标选择记录；请查看任务状态与执行反馈。");
    put("model-name", d ? `模型 / 策略：${d.provider.model || "未记录"}` : "未记录模型或策略");
    const tokenFields = d ? [["inputTokens", "input_tokens", "输入"], ["outputTokens", "output_tokens", "输出"], ["cachedInputTokens", "cached_input_tokens", "缓存输入"]]
      .map(([key, alternate, label]) => [d.provider.usage[key] ?? d.provider.usage[alternate], label]).filter(([value]) => integer(value)) : [];
    put("model-usage", d?.provider.kind === "fixed-reference" ? "固定策略 · 无模型 token 消耗" : tokenFields.length ? tokenFields.map(([value, label]) => `${label} ${formatNumber(value)} token`).join(" · ") : "未提供 token 用量");
    put("goal-reached", f.goalReached ? "已到达" : "未核实到达");
    put("returned", f.returned ? f.goalReached ? "已返回" : "位于原起点" : "尚未返回");
    const requiresActivity = Boolean(m.goal?.activityId);
    const visit = f.activityVisit;
    const activityVerified = Boolean(requiresActivity && f.activityCompleted === true && visit && visit.activityId === m.goal.activityId && same(visit.position, m.goal.target)
      && data.steps.some((s) => s.commandId === visit.commandId && s.status === "committed" && s.action.type === "visit" && s.action.activityId === visit.activityId));
    $("activity-fact").hidden = !requiresActivity;
    put("activity-fact", requiresActivity ? activityVerified ? `到访已核实：${m.goal.label} · v${visit.stateVersion}` : "尚未核实本次到访；到达坐标不等于完成活动。" : "");
    $("activity-fact").dataset.verified = String(activityVerified);
    const requiresPostcard = m.sharePostcard === true;
    const card = f.postcard;
    const postcardVerified = Boolean(requiresPostcard && activityVerified && f.postcardShared === true && card && card.authorActorId === m.actorId
      && card.activityId === m.goal.activityId && card.visitCommandId === visit.commandId && card.text === d?.postcardText && same(card.position, m.goal.target)
      && card.stateVersion > visit.stateVersion && data.steps.some((s) => s.commandId === card.commandId && s.status === "committed" && s.stateVersion === card.stateVersion
        && s.action.type === "postcard" && s.action.activityId === card.activityId && s.action.visitCommandId === card.visitCommandId && s.action.text === card.text));
    $("postcard-draft-panel").hidden = !requiresPostcard;
    put("postcard-draft", d?.postcardText || "尚无有效草稿。");
    put("decision-boundary", requiresPostcard ? "模型在行动前选择地点并起草；到访、分享与返回由实际世界响应确认。草稿不是现场感受的证明。" : "模型只选择目标；路径与行动由确定性执行器处理。模型说法不等于执行成功。");
    $("postcard-fact-panel").hidden = !requiresPostcard;
    put("postcard-fact", postcardVerified ? `分享已核实：居民 ${card.authorActorId} · ${m.goal.label} · v${card.stateVersion}` : "尚未核实本次分享；草稿和到访记录不能替代分享事实。");
    $("postcard-fact").dataset.verified = String(postcardVerified);
    $("postcard-shared-text").hidden = !postcardVerified;
    put("postcard-shared-text", postcardVerified ? card.text : "");
    const requiresMosaic = m.paintMosaic === true, edit = f.mosaicEdit;
    const mosaicVerified = Boolean(requiresMosaic && ["r5", "r6"].includes(m.rulesVersion) && activityVerified && f.mosaicPainted === true && edit && edit.authorActorId === m.actorId
      && edit.activityId === m.goal.activityId && edit.visitCommandId === visit.commandId && same(edit.position, m.goal.target)
      && edit.baseRevision === d?.mosaicBaseRevision && mosaic.equalPatch(edit.patch, d?.mosaicPatch) && edit.stateVersion > visit.stateVersion
      && data.steps.some((s) => s.commandId === edit.commandId && s.status === "committed" && s.stateVersion === edit.stateVersion
        && s.action.type === "mosaic" && s.action.activityId === edit.activityId && s.action.visitCommandId === edit.visitCommandId
        && s.action.expectedMosaicRevision === edit.baseRevision && mosaic.equalPatch(s.action.patch, edit.patch)));
    $("mosaic-report-panel").hidden = !requiresMosaic;
    if (requiresMosaic) {
      put("decision-boundary", "模型在出发前读取画布并构图；到访、实际修改与返回分别由世界响应确认。草图不能替代已完成作品。");
      put("mosaic-fact", mosaicVerified ? `绘制已核实：居民 ${edit.authorActorId} · ${edit.patch.length} 格 · 画布第 ${edit.revision} 版 · 世界 v${edit.stateVersion}` : "尚未核实本次绘制；草图、到访或当前画布不能替代本任务原修改记录。");
      $("mosaic-fact").dataset.verified = String(mosaicVerified);
      mosaic.renderBoard($("mosaic-proposal"), mosaic.emptyCells(), { patch: d?.mosaicPatch || [] });
      put("mosaic-proposal-note", d?.mosaicPatch ? `基于画布第 ${d.mosaicBaseRevision} 版，提议修改 ${d.mosaicPatch.length} 格。虚线为行动前草图。` : "尚未产生有效构图。");
      $("mosaic-committed").hidden = !mosaicVerified;
      if (mosaicVerified) {
        const cells = mosaic.emptyCells();
        edit.patch.forEach((c) => { cells[c.y * 5 + c.x] = { ...c, authorActorId: edit.authorActorId, commandId: edit.commandId, stateVersion: edit.stateVersion }; });
        mosaic.renderBoard($("mosaic-committed"), cells);
      }
      put("mosaic-committed-note", mosaicVerified ? `本任务原到访与修改命令一致，画布 ${edit.baseRevision} → ${edit.revision}。` : "没有一致的已提交修改，暂不展示确认作品。");
      $("mosaic-final").hidden = !data.world.mosaic;
      if (data.world.mosaic) mosaic.renderBoard($("mosaic-final"), data.world.mosaic.cells);
      put("mosaic-report-version", data.world.mosaic ? `结束快照 · 第 ${data.world.mosaic.revision} 版` : "缺少画布快照");
      put("mosaic-final-note", data.world.mosaic ? `当前格子的最后作者：${[...new Set(data.world.mosaic.cells.filter((c) => c.authorActorId).map((c) => c.authorActorId))].join("、") || "无人"}。` : "报告没有保存结束画布。");
    }
    const consentVerified = renderConsentReport(data, activityVerified);
    const requiresConstruction = Boolean(m.goal?.buildRecipeId), built = f.construction;
    const constructionVerified = Boolean(requiresConstruction && m.allowBuild === true && f.constructionBuilt === true && built
      && built.recipeId === m.goal.buildRecipeId && built.ownerActorId === m.actorId && same(built.position, m.goal.target)
      && f.createdEntityIds.includes(built.entityId) && b.used.wood >= built.woodSpent
      && data.steps.some(s => s.status === "committed" && s.commandId === built.commandId && s.entityId === built.entityId
        && s.stateVersion === built.stateVersion && s.action.type === "build" && s.action.recipeId === built.recipeId && Array.isArray(s.action.at) && same(s.action.at, built.position))
      && data.world.entities.some(e => e.entityId === built.entityId && e.definitionId === built.definitionId
        && e.definitionVersion === 1 && e.ownerActorId === m.actorId && e.rulesVersion === m.rulesVersion && e.embodiedWood === built.woodSpent && same(e.position, built.position)));
    $("construction-fact").hidden = !requiresConstruction;
    $("construction-fact").dataset.verified = String(constructionVerified);
    put("construction-fact", requiresConstruction ? constructionVerified
      ? `建造已核实：${structures[built.recipeId].label} ${coord(built.position)} 米 · 消耗 ${built.woodSpent} 木材 · v${built.stateVersion} · ${built.entityId}`
      : "尚未核实本次设施建成；到达地点或看到已有设施不能代替原建造记录。" : "");
    const requiresTransfer = Boolean(m.goal?.transfer), given = f.transfer;
    const giftSteps = data.steps.filter(s => s.action.type === "transfer" && s.status === "committed");
    const transferVerified = Boolean(requiresTransfer && m.allowTransfer === true && f.transferCompleted === true && given
      && given.worldInstanceId === m.worldInstanceId && given.senderActorId === m.actorId
      && given.recipientActorId !== given.senderActorId
      && Math.hypot(given.position[0] - m.goal.target[0], given.position[1] - m.goal.target[1]) <= m.arrivalTolerance
      && given.recipientActorId === m.goal.transfer.recipientActorId && given.quantity === m.goal.transfer.quantity
      && given.resource === m.goal.transfer.resource && given.inventoryWoodBefore - given.quantity === given.inventoryWoodAfter
      && f.woodTransferred === given.quantity && b.used.wood >= given.quantity && giftSteps.length === 1
      && giftSteps.some(s => s.commandId === given.commandId && s.stateVersion === given.stateVersion
        && s.action.recipientActorId === given.recipientActorId && s.action.quantity === given.quantity
        && s.action.resource === given.resource && s.inventoryWood === given.inventoryWoodAfter && same(s.position, given.position)));
    $("transfer-fact").hidden = !requiresTransfer;
    $("transfer-fact").dataset.verified = String(transferVerified);
    put("transfer-fact", requiresTransfer ? transferVerified
      ? `赠送已核实：${given.senderActorId} → ${given.recipientActorId} · ${given.quantity} 木材 · v${given.stateVersion}`
      : "尚未核实本次赠送；当前余额或对方作品不能代替原交付记录。" : "");
    const recentTransfers = data.world.recentTransfers;
    $("recent-transfers").hidden = !recentTransfers?.items.length;
    put("recent-transfers", recentTransfers?.items.length
      ? `最近交付记录${recentTransfers.truncated ? "（更早记录未包含）" : ""}：` + recentTransfers.items.slice(-3)
        .map(e => `${e.actorId} → ${e.recipientActorId} · ${e.quantity} 木材 · v${e.stateVersion}`).join("；") : "");
    if (d?.provider.kind === "fixed-reference") put("decision-boundary", "目标由固定策略选择，路径与行动由确定性执行器处理；完成事实以记录中的世界响应为准。");
    put("model-budget-label", d?.provider.kind === "fixed-reference" ? "目标选择次数" : "模型调用");
    put("model-budget-note", d?.provider.kind === "fixed-reference" ? "固定策略 · 外部模型 0 次" : "高层目标选择");
    $("goal-reached").dataset.verified = String(f.goalReached);
    $("returned").dataset.verified = String(f.returned);
    put("verified-at", f.verifiedAtUtc ? `${new Date(f.verifiedAtUtc).toISOString().replace("T", " ").replace(".000Z", " UTC").replace(/Z$/, " UTC")}` : "未记录核实时间");
    put("state-versions", `${f.startStateVersion ?? "未知"} → ${f.endStateVersion ?? "未知"}`);
    put("created-summary", `${f.woodGathered === undefined ? "" : `采集 ${f.woodGathered} · 领取 `}${f.woodClaimed} 单位木材${m.rulesVersion === "r10" ? ` · 预约领取 ${f.materialWoodHarvested ?? 0}` : ""}${["r9", "r10"].includes(m.rulesVersion) ? ` · 赠送 ${f.woodTransferred ?? 0}` : ""} / ${f.createdEntityIds.length} 个设施`);
    const canvas = window.EntityCanvasReport.assess(data);
    window.EntityCanvasReport.render(data, canvas);
    const notes = window.EntityNoteReport.assess(data);
    $("entity-note-panel").hidden = !notes.uses;
    $("entity-note-fact").dataset.verified = String(notes.verified);
    put("entity-note-draft", notes.uses ? `任务原文：${m.goal.entityNote.text}` : "");
    put("entity-note-reference", notes.uses ? `目标：${m.goal.entityNote.entityId} · 引用：${m.goal.entityNote.replyToNoteId ?? "独立留言"}` : "");
    put("entity-note-fact", notes.verified ? `已核对发表记录：居民 ${f.entityNote.authorActorId} · v${f.entityNote.stateVersion}` : "尚未确认发表；到达或任务正文不能代替原手记事实。");
    put("entity-note-text", notes.verified ? f.entityNote.text : "");
    const material = window.MaterialReport.assess(data);
    $("material-fact").hidden = !material.uses;
    $("material-fact").dataset.verified = String(material.verified);
    put("material-fact", material.uses ? material.verified
      ? "材料入口领取已核实：原预约 → 亲自领取 3 木材；建造另行确认。"
      : material.reserved && material.consistent ? `已确认原预约 · 领取 ${material.count} / 3 木材；尚未全部领取。`
      : "尚未核实本任务材料领取；排队、余额或来源存量不能代替原领取事实。" : "");
    const sourceDescription = window.MaterialReport.sourceDescription(data);
    $("material-source-policy").hidden = sourceDescription === "";
    put("material-source-policy", sourceDescription);
    $("query-budget-item").hidden = b.limits.queries === undefined;
    let workshopPanel = $("workshop-report-fact");
    if (!workshopPanel) {
      workshopPanel = node("div", ""); workshopPanel.id = "workshop-report-fact";
      $("construction-fact").after(workshopPanel);
    }
    workshopPanel.hidden = !workshop.uses;
    workshopPanel.dataset.verified = String(workshop.verified);
    workshopPanel.replaceChildren();
    if (workshop.uses) {
      const action = m.goal.workshop.action, result = f.workshopAction;
      workshopPanel.append(node("p", "", workshop.verified
        ? `原动作已核对回执、事件和详情：${workshopNames[action.type]} · 命令 ${result.commandId} · v${result.stateVersion}`
        : "工坊原动作尚未核实；当前工具、箱内余额或完成标记不能代替原回执、事件和详情。"));
      workshopPanel.append(node("p", "", `配方用材 ${b.used.wood} / ${b.limits.wood} · 存取周转 ${b.used.woodMoved} / ${b.limits.woodMoved} · 存入 ${f.woodDeposited} · 取出 ${f.woodWithdrawn}`));
      if (workshop.verified) workshopPanel.append(node("p", "", `本人库存 ${result.inventoryWoodBefore} → ${result.inventoryWood}${result.storedWood === null ? "" : ` · 本人箱 ${result.storedWoodBefore} → ${result.storedWood}`} · 实体 ${result.entity.entityId}${result.tool ? ` · 本人工具 ${result.tool.toolId}` : ""}`));
      workshopPanel.append(node("p", "", f.returned ? "已确认位于原起点。" : m.goal.workshop.returnToOrigin
        ? "原动作和返程分别核实；返程尚未完成。" : "任务明确未要求返程；尚未返回原起点。"));
      put("goal-reached", workshop.verified ? "原工坊动作已核实" : "原工坊动作未核实");
      $("goal-reached").dataset.verified = String(workshop.verified);
      put("decision-boundary", "任务明确指定单一工坊动作和独立权限；未调用选择器或模型。原动作、返程、未知结果分别核对。");
      put("model-budget-label", "模型调用");
      put("model-budget-note", "固定动作 · 未调用选择器");
    }
    let forestryPanel = $("forestry-report-fact");
    if (!forestryPanel) {
      forestryPanel = node("div", ""); forestryPanel.id = "forestry-report-fact";
      $("construction-fact").after(forestryPanel);
    }
    forestryPanel.hidden = !forestry.uses;
    forestryPanel.dataset.verified = String(forestry.verified);
    forestryPanel.replaceChildren();
    if (forestry.uses) {
      const action = m.goal.forestry.action, result = f.forestryAction, c = data.world.forestry;
      forestryPanel.append(node("p", "", forestry.verified
        ? `原动作已核对回执、事件和详情：${forestryNames[action.type]} · 命令 ${result.commandId} · v${result.stateVersion}`
        : "林业原动作尚未核实；排队、成熟树木或当前余额不能代替原回执、事件和详情。"));
      forestryPanel.append(node("p", "", `${forestry.verified ? "" : "报告计数（待核实）："}木斧用材 ${b.used.wood} / ${b.limits.wood} · ${forestry.verified ? "实际收获木材" : "收获木材记录"} ${f.woodHarvested} / ${b.limits.woodHarvested} · 领取树种 ${f.seedsCollected} / ${b.limits.seedsCollected} · 种植消耗 ${f.seedsPlanted} / ${b.limits.seedsPlanted} · 收获树种 ${f.seedsHarvested} / ${b.limits.seedsHarvested}`));
      if (forestry.verified) {
        forestryPanel.append(node("p", "", `本人木材 ${result.inventoryWoodBefore} → ${result.inventoryWood} · 本人树种 ${result.seedsBefore} → ${result.seeds}${result.tool ? ` · 本人木斧 ${result.tool.toolId}` : ""}${result.reservation ? ` · 原预约 ${result.reservation.reservationId}（${forestStateNames[result.reservation.status]}）` : ""}${result.plant ? ` · 原树木 ${result.plant.plantId}（${forestStateNames[result.plant.state]}）` : ""}`));
        if (action.type === "reserve_forest") forestryPanel.append(node("p", "", "本次只确认已排队；未据此宣称获配林地、已种植或已收获。"));
        if (action.type === "plant_tree") forestryPanel.append(node("p", "", "本次只确认种植；成熟须经真实服务时间，木材须另行收获。"));
      }
      if (forestry.consistent) {
        forestryPanel.append(node("p", "", `最近观察 v${data.world.observedStateVersion} · 苗圃 ${c.nursery.stockSeeds} 颗（已预留 ${c.nursery.reservedSeeds}）· 本人树种 ${c.seeds}。成熟木材仍在树上，未计为居民收获。`));
        for (const plot of c.plots) {
          const tree = c.plants.find(p => p.plotId === plot.plotId);
          forestryPanel.append(node("p", "", `林地 ${plot.plotId} ${coord(plot.position)} · ${tree ? `${tree.state === "mature" ? "成熟" : "生长中"} · 原树木 ${tree.plantId} · 树上木材 ${tree.standingWood}` : "空地"}`));
        }
      }
      forestryPanel.append(node("p", "", !forestry.consistent ? "返回位置记录待复核。" : f.returned ? "已确认位于原起点。" : m.goal.forestry.returnToOrigin ? "返程尚未完成。" : "任务明确未要求返程；尚未返回原起点。"));
      if (!forestry.consistent) { put("returned", "返回记录待复核"); $("returned").dataset.verified = "false"; }
      put("goal-reached", forestry.verified ? "原林业动作已核实" : "原林业动作未核实");
      $("goal-reached").dataset.verified = String(forestry.verified);
      put("decision-boundary", "任务明确指定原林业动作、对象与独立权限；等待原预约或树木不授权更换租约、补种或自动续租。");
      put("model-budget-label", "模型调用"); put("model-budget-note", "固定动作 · 未调用选择器");
    }
    const warnings = [];
    if (!forestry.consistent) warnings.push("林业原动作三方证据、对象、材料或预算不一致；完成标记待复核。");
    if (!workshop.consistent) warnings.push("工坊原动作三方证据、权限、前后库存或预算不一致；完成标记待复核。");
    if (!canvas.consistent) warnings.push("地画汇总与原目标、版本、草图或作者记录不一致。");
    if (!canvas.budgetConsistent) warnings.push("地画任务预算与原步骤数、必要查询或累计上限不一致；整体完成待复核。");
    if (!notes.consistent) warnings.push("手记汇总与原命令、正文、引用或作者记录不一致。");
    if (!material.consistent) warnings.push("材料入口汇总与原预约、领取步骤或身份不一致。");
    const cuts = data.steps.filter((s) => s.action.type === "gather" && s.status === "committed").length;
    const gatheringConsistent = (f.woodGathered ?? 0) === cuts && (cuts === 0 || m.allowGather === true && ["r7", "r8", "r9", "r10"].includes(m.rulesVersion));
    const transferConsistent = (f.woodTransferred ?? 0) === giftSteps.reduce((sum, s) => sum + s.action.quantity, 0)
      && (giftSteps.length === 0 || transferVerified);
    const committedPositions = data.steps.filter(s => s.status === "committed" && s.position).map(s => s.position);
    const near = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]) <= .06;
    const constructionVisited = !requiresConstruction || constructionVerified
      && data.steps.slice(data.steps.findIndex(s => s.commandId === built.commandId))
        .some(s => s.status === "committed" && s.position && near(s.position, m.goal.target));
    const walkConsistent = forestry.uses ? forestry.complete : workshop.uses ? workshop.complete : !continuous(data.world) || m.goal && [m.origin, ...committedPositions].some(p => near(p, m.goal.target)) && near(committedPositions.at(-1) || m.origin, m.origin) && !data.steps.some(s => s.status === "committed" && s.blocked === true);
    const incomplete = forestry.uses && !forestry.complete || workshop.uses && !workshop.complete || canvas.uses && (!canvas.verified || !canvas.budgetConsistent) || notes.uses && !notes.verified || material.uses && !material.verified || !walkConsistent || !constructionVisited || !gatheringConsistent || !transferConsistent || !f.goalReached || !f.returned && !(workshop.uses && m.goal.workshop.returnToOrigin === false || forestry.uses && m.goal.forestry.returnToOrigin === false) || !m.goal || requiresTransfer && !transferVerified || requiresConstruction && !constructionVerified || requiresActivity && !activityVerified || requiresPostcard && !postcardVerified || requiresMosaic && !mosaicVerified || (m.proposeMosaic || m.reviewMosaicProposal) && !consentVerified;
    if (m.status === "completed" && incomplete) warnings.push("报告标记为已完成，但到达、返回、目标、到访或本次创作事实不完整，不能据此认定任务成功。");
    if (d && m.goal && d.goalId !== m.goal.id) warnings.push("模型选择与执行目标编号不一致，请复核原始报告。");
    if (d?.provider.kind === "test-double") warnings.push("这份报告使用测试替身，不是一次真实模型运行；仅供客户端或执行器测试。");
    if (!gatheringConsistent) warnings.push("采集汇总与原采集步骤或任务权限不一致，请复核原始记录。");
    if (!transferConsistent) warnings.push("赠送汇总与原交付步骤、身份或任务权限不一致，请复核原始记录。");
    if (m.status === "completed" && !walkConsistent) warnings.push(forestry.uses ? "林业原动作或任务要求的返程尚未得到一致证据支持。" : workshop.uses ? "工坊动作或任务要求的返程尚未得到一致证据支持。" : "连续行走记录未支持在 0.06 米内到达并返回，或包含碰撞截停。");
    if (m.status === "completed" && constructionVerified && !constructionVisited) warnings.push("建设完成后的记录未支持到达设施中心。");
    for (const [key, prefix] of [["commands", "command"], ["wood", "wood"], ["modelCalls", "model"], ["seconds", "seconds"], ...(b.limits.queries === undefined ? [] : [["queries", "queries"]])]) {
      put(`${prefix}-budget`, `${formatNumber(b.used[key])} / ${formatNumber(b.limits[key])}`);
      const progress = $(`${prefix}-progress`);
      progress.max = b.limits[key] || 1;
      progress.value = Math.min(b.used[key], progress.max);
      progress.setAttribute("aria-valuetext", `已用 ${formatNumber(b.used[key])}，上限 ${formatNumber(b.limits[key])}`);
      progress.parentElement.dataset.over = String(b.used[key] > b.limits[key]);
      if (b.used[key] > b.limits[key]) warnings.push(`${{ commands: "命令", wood: "木材", modelCalls: "模型调用", seconds: "时间", queries: "查询" }[key]}累计值超过报告上限，请复核执行记录。`);
    }
    put("report-warning", warnings.join(" "));
    $("report-warning").hidden = warnings.length === 0;
    if (m.status === "completed" && incomplete) {
      put("report-status", "完成标记待复核");
      $("report-status").dataset.tone = "warning";
    }
    renderSteps();
    put("feedback-summary", data.feedback.summary || "报告未提供执行总结。");
    $("feedback-lists").replaceChildren();
    for (const [key, label] of [["issues", "遇到的问题"], ["suggestions", "后续建议"]]) {
      if (!data.feedback[key].length) continue;
      const section = node("div");
      section.append(node("h3", "", label));
      const list = node("ul");
      data.feedback[key].forEach((item) => list.append(node("li", "", item)));
      section.append(list);
      $("feedback-lists").append(section);
    }
    const w = data.world;
    put("map-summary", continuous(w)
      ? `${w.width} × ${w.height} 米 · 连续自然地形。起点 ${coord(m.origin)}；目标 ${m.goal ? coord(m.goal.target) : "未选择"}；到达容差 0.06 米。${workshop.uses || forestry.uses ? `地形、设施与资源为最近实际观察 v${w.observedStateVersion}，可能早于最后动作；` : "地形与资源显示结束快照，"}轨迹按步骤回看。设施：${w.entities.map(e => `${e.definitionId} ${coord(e.position)}`).join("、") || "无"}。`
      : `${w.width} × ${w.height}。起点 ${coord(m.origin)}；目标 ${m.goal ? coord(m.goal.target) : "未选择"}。水面：${w.water.map(coord).join("、") || "无"}。阻挡：${w.blocked.map(coord).join("、") || "无"}。设施：${w.entities.map((e) => `${e.definitionId} ${coord(e.position)}`).join("、") || "无"}。`);
    $("replay-slider").max = String(data.steps.length);
    $("replay-slider").disabled = data.steps.length === 0;
    selectStep(data.steps.length);
    put("report-source", `记录来源：${source}`);
    setMessage(`已加载：${source} · ${data.steps.length} 条步骤 · 本地历史记录，非实时世界。`);
  }

  function renderConsentReport(data, activityVerified) {
    const { mission: m, decision: d, facts: f } = data;
    const proposing = m.proposeMosaic === true, reviewing = Boolean(m.reviewMosaicProposal);
    $("consent-report-panel").hidden = !proposing && !reviewing;
    if (!proposing && !reviewing) return true;
    const visit = f.activityVisit, proposal = proposing ? f.mosaicProposal : d?.mosaicProposal, review = f.mosaicReview;
    let verified = false;
    if (m.rulesVersion === "r6" && activityVerified && visit && d) {
      if (proposing && f.mosaicProposed === true && consent.validProposal(proposal)) {
        verified = proposal.authorActorId === m.actorId && proposal.visitCommandId === visit.commandId && proposal.stateVersion > visit.stateVersion
          && proposal.text === d.proposalText && proposal.baseRevision === d.mosaicBaseRevision && mosaic.equalPatch(proposal.patch, d.mosaicPatch)
          && data.steps.some((s) => s.status === "committed" && s.stateVersion === proposal.stateVersion && s.action.type === "mosaic_propose"
            && consent.proposalMatches(proposal, s.action, m.actorId, s.commandId, s.stateVersion - 1));
      }
      if (reviewing && f.mosaicReviewed === true && consent.validReview(review) && consent.validProposal(proposal)) {
        verified = review.authorActorId === m.actorId && review.visitCommandId === visit.commandId && review.stateVersion > visit.stateVersion
          && proposal.authorActorId === m.reviewMosaicProposal.proposalActorId && proposal.commandId === m.reviewMosaicProposal.proposalCommandId
          && review.decision === d.reviewDecision && review.text === d.reviewText
          && data.steps.some((s) => s.status === "committed" && s.stateVersion === review.stateVersion && s.action.type === "mosaic_review"
            && consent.reviewMatches(review, s.action, m.actorId, s.commandId, s.stateVersion - 1, proposal));
        if (verified && review.decision === "accept") verified = f.mosaicPainted === true && mosaic.validEdit(f.mosaicEdit)
          && ["authorActorId", "commandId", "visitCommandId", "baseRevision", "revision", "stateVersion", "paintedAtUtc"].every((k) => f.mosaicEdit[k] === review.mosaicEdit[k])
          && mosaic.equalPatch(f.mosaicEdit.patch, review.mosaicEdit.patch);
        if (verified && review.decision === "reject") verified = f.mosaicPainted !== true && !f.mosaicEdit;
      }
    }
    $("consent-report-fact").dataset.verified = String(verified);
    put("consent-report-state", proposing ? "提出建议" : verified ? review.decision === "accept" ? "同意并改图" : "拒绝并保留" : "审阅待核实");
    put("consent-report-fact", !verified ? "尚未核实本任务的原提议或审阅；草稿与到访不能代替实际提交。" : proposing
      ? `提议已核实：居民 ${proposal.authorActorId} 向居民 ${proposal.targetActorId} 提出 ${proposal.patch.length} 格修改，尚未因此改图。`
      : review.decision === "accept" ? `同意与改图已核实：居民 ${review.authorActorId} 提交 ${review.mosaicEdit.patch.length} 格修改 · 画布第 ${review.mosaicEdit.revision} 版`
        : `拒绝已核实：居民 ${review.authorActorId} 保留原图，没有产生绘制记录。`);
    const patch = proposal?.patch || d?.mosaicPatch || [];
    mosaic.renderBoard($("consent-report-patch"), mosaic.emptyCells(), { patch });
    put("consent-report-origin", proposal ? `提议人 ${proposal.authorActorId} · 原格最后作者 ${proposal.targetActorId} · 基于画布第 ${proposal.baseRevision} 版` : d?.mosaicPatch ? `行动前草图 · 画布第 ${d.mosaicBaseRevision} 版` : "尚无有效提议。");
    put("consent-report-proposal-text", proposal?.text || d?.proposalText || "没有已保存的提议文本。");
    put("consent-report-review-text", reviewing ? `${verified ? "实际审阅理由" : "行动前的审阅草案"}：${verified ? review.text : d?.reviewText || "尚未产生"}` : "这份任务只负责发表提议；对方之后是否同意，要看独立的审阅记录。");
    put("consent-report-attribution", verified && reviewing && review.decision === "accept" ? `构思由居民 ${proposal.authorActorId} 提出，实际同意和改图由居民 ${review.authorActorId} 提交。` : "提议与决定分别记录，不自动替对方同意。");
    $("consent-report-final").hidden = !data.world.mosaic;
    if (data.world.mosaic) mosaic.renderBoard($("consent-report-final"), data.world.mosaic.cells);
    put("consent-report-final-note", data.world.mosaic ? `结束快照 · 画布第 ${data.world.mosaic.revision} 版；之后的世界可能继续变化。` : "未保存结束快照。");
    put("decision-boundary", "模型在行动前提出建议或决定；现场到访、原提议、实际审阅与改图分别由世界确认。对方的文字不能授予权限。");
    return verified;
  }

  function actionLabel(action) {
    const label = forestryNames[action.type] || workshopNames[action.type] || actionNames[action.type] || action.type;
    if (forestryAction(action)) return `${label}${action.reservationId ? ` · 原预约 ${action.reservationId}` : ""}${action.plantId ? ` · 原树木 ${action.plantId}` : ""}${action.plotId ? ` · 林地 ${action.plotId}` : ""}${action.toolId ? ` · 本人木斧 ${action.toolId}` : ""}`;
    if (action.type === "build_workshop") return `${label} · ${action.recipeId === "workbench.v1" ? "工作台" : "私人储物箱"} ${coord(action.at)}`;
    if (action.type === "craft_tool") return `${label} · 工作台 ${action.entityId}`;
    if (["deposit_wood", "withdraw_wood"].includes(action.type)) return `${label} · ${action.quantity} 木材 · ${action.entityId}`;
    if (["visit", "postcard", "mosaic", "mosaic_propose", "mosaic_review"].includes(action.type)) return `${label} · ${report.world.activities?.find((a) => a.id === action.activityId)?.label || action.activityId || "活动地点"}`;
    if (action.type === "claim" && action.quantity !== undefined) return `${label} · ${action.quantity} 单位`;
    if (action.type === "gather") return `${label} · ${action.nodeId}`;
    if (action.type === "transfer") return `${label} · 给 ${action.recipientActorId} ${action.quantity} 木材`;
    if (action.type === "walk") return `${label} · 朝 ${coord(action.to)} 米`;
    if (action.type === "move" && action.direction) return `${label} · ${{ up: "向上", down: "向下", left: "向左", right: "向右", north: "向北", south: "向南", west: "向西", east: "向东" }[action.direction] || action.direction}`;
    if (action.type === "move" && Number.isSafeInteger(action.dx) && Number.isSafeInteger(action.dy)) return `${label} · ${{ "1,0": "向右", "-1,0": "向左", "0,1": "向下", "0,-1": "向上" }[`${action.dx},${action.dy}`] || `偏移 (${action.dx}, ${action.dy})`}`;
    if (action.type === "build") {
      const recipe = action.definitionId || action.recipeId;
      const position = action.position || action.at;
      return `${label}${recipe ? ` · ${["bridge", "bridge.v1"].includes(recipe) ? "桥" : recipe}` : ""}${position ? ` ${coord(position)}` : ""}`;
    }
    return label;
  }

  function renderSteps() {
    const list = $("steps-list");
    list.replaceChildren();
    stepButtons = [];
    put("step-count", `${report.steps.length} 条记录`);
    if (!report.steps.length) list.append(node("li", "no-steps", "尚无执行步骤。模型选择失败或任务尚未开始时，报告可能没有行动记录。"));
    report.steps.forEach((step, i) => {
      const item = node("li", "step");
      const button = node("button", "step-button");
      button.type = "button";
      button.setAttribute("aria-label", `回看第 ${step.index} 步：${actionLabel(step.action)}，${stepStatuses[step.status] || step.status}`);
      button.append(node("span", "step-number", String(step.index).padStart(2, "0")));
      const content = node("span", "step-content");
      const top = node("span", "step-top");
      top.append(node("span", "step-title", actionLabel(step.action)));
      const status = node("span", "step-status", stepStatuses[step.status] || step.status);
      status.dataset.tone = step.status === "committed" ? "success" : "warning";
      top.append(status);
      content.append(top, node("span", "step-reason", step.reason || "未记录原因"), node("span", "step-meta", `记录位置 ${step.position ? coord(step.position) : "未知"} · 库存木材 ${step.inventoryWood ?? "未知"} · 版本 ${step.stateVersion ?? "未知"}`), node("span", "step-command", `命令 ${step.commandId}`));
      button.append(content);
      button.addEventListener("click", () => selectStep(i + 1));
      item.append(button);
      list.append(item);
      stepButtons.push(button);
    });
  }

  function selectStep(value) {
    if (!report) return;
    const index = Math.max(0, Math.min(report.steps.length, Number(value)));
    $("replay-slider").value = String(index);
    $("replay-prev").disabled = index === 0;
    $("replay-next").disabled = index === report.steps.length;
    const step = report.steps[index - 1];
    put("replay-counter", index === 0 ? "任务起点" : `${index} / ${report.steps.length}`);
    const description = step ? `第 ${step.index} 步 · ${actionLabel(step.action)} · ${stepStatuses[step.status] || step.status} · ${step.position ? `记录位置 ${coord(step.position)}` : "位置未记录"}${["pending", "unknown"].includes(step.status) ? "（动作结果未确认）" : ""}` : `任务开始 · 起点 ${coord(report.mission.origin)}`;
    put("replay-description", description + (step?.blocked ? " · 碰撞截停" : ""));
    $("replay-slider").setAttribute("aria-valuetext", description);
    $("replay-canvas").setAttribute("aria-label", `历史地图，${description}`);
    stepButtons.forEach((button, i) => {
      if (i === index - 1) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    drawMap(index);
  }

  function drawMap(index) {
    const canvas = $("replay-canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { world: w, mission: m, steps } = report;
    const inset = 34, size = 652, cellSize = size / Math.max(w.width, w.height);
    const offsetX = inset + (size - w.width * cellSize) / 2, offsetY = inset + (size - w.height * cellSize) / 2;
    const free = continuous(w), shift = free ? 0 : .5;
    const center = (p) => [offsetX + (p[0] + shift) * cellSize, offsetY + (p[1] + shift) * cellSize];
    ctx.clearRect(0, 0, 720, 720);
    ctx.fillStyle = "#edf1e5";
    ctx.fillRect(0, 0, 720, 720);
    const water = new Set((w.water || []).map((p) => p.join(",")));
    const blocked = new Set((w.blocked || []).map((p) => p.join(",")));
    if (free) {
      ctx.fillStyle = "#dce5cd"; ctx.fillRect(offsetX, offsetY, w.width * cellSize, w.height * cellSize);
      ctx.fillStyle = "#afd0d2"; ctx.beginPath();
      w.terrain.river.polygon.forEach((p, i) => i ? ctx.lineTo(...center(p)) : ctx.moveTo(...center(p)));
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "#8ebbc0"; ctx.lineWidth = 2; ctx.stroke();
      for (const rock of w.terrain.obstacles) {
        const [x, y] = center(rock.position);
        const tree = w.forestry?.plants?.find(p => p.plantId === rock.id);
        ctx.fillStyle = rock.kind === "forestry_nursery" ? "#a8893c" : rock.kind === "forestry_tree" ? tree?.state === "mature" ? "#225e37" : "#78a356" : "#8e987f";
        ctx.beginPath(); ctx.arc(x, y, rock.radius * cellSize, 0, Math.PI * 2); ctx.fill();
      }
      if (forestryAssess(report).consistent && w.forestry?.plots) for (const plot of w.forestry.plots) {
        const [x, y] = center(plot.position);
        ctx.strokeStyle = "#668754"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        ctx.strokeRect(x - 1.5 * cellSize, y - 1.5 * cellSize, 3 * cellSize, 3 * cellSize); ctx.setLineDash([]);
      }
      for (const tree of w.resourceNodes) {
        const [x, y] = center(tree.position), alive = tree.remainingWood > 0;
        ctx.fillStyle = alive ? "#567e4f" : "#a18a65";
        ctx.beginPath(); ctx.arc(x, y, (alive ? .65 : .22) * cellSize, 0, Math.PI * 2); ctx.fill();
        if (alive) { ctx.fillStyle = "#f6f8ef"; ctx.font = "12px system-ui"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(tree.remainingWood), x, y); }
      }
      ctx.strokeStyle = "#6c7b5f"; ctx.lineWidth = 2; ctx.beginPath();
      ctx.moveTo(offsetX, offsetY + w.height * cellSize + 16); ctx.lineTo(offsetX + 5 * cellSize, offsetY + w.height * cellSize + 16); ctx.stroke();
      ctx.fillStyle = "#6c7b5f"; ctx.font = "13px system-ui"; ctx.textAlign = "left";
      ctx.fillText("5 米", offsetX, offsetY + w.height * cellSize + 34);
    }
    for (let y = 0; !free && y < w.height; y++) {
      for (let x = 0; x < w.width; x++) {
        const key = `${x},${y}`, px = offsetX + x * cellSize, py = offsetY + y * cellSize;
        ctx.fillStyle = water.has(key) ? (x + y) % 2 ? "#afd0d2" : "#b9d8d7" : (x + y) % 2 ? "#dce5cd" : "#e4ead6";
        ctx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
        if (water.has(key) && cellSize > 18) {
          ctx.strokeStyle = "#8ebbc0";
          ctx.lineWidth = 1.5;
          for (let row = 1; row < 4; row++) {
            ctx.beginPath(); ctx.moveTo(px + cellSize * .24, py + cellSize * row / 4); ctx.lineTo(px + cellSize * .72, py + cellSize * row / 4); ctx.stroke();
          }
        }
        if (blocked.has(key) && !water.has(key)) {
          ctx.fillStyle = "#7b866c"; ctx.fillRect(px + cellSize * .15, py + cellSize * .15, cellSize * .7, cellSize * .7);
          ctx.fillStyle = "#8e987f"; ctx.fillRect(px + cellSize * .15, py + cellSize * .15, cellSize * .7, cellSize * .12);
        }
      }
    }
    if (!free && w.width <= 20 && w.height <= 20) {
      ctx.fillStyle = "#6c7b5f"; ctx.font = "13px system-ui"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (let x = 0; x < w.width; x++) ctx.fillText(String(x), offsetX + (x + .5) * cellSize, offsetY - 16);
      for (let y = 0; y < w.height; y++) ctx.fillText(String(y), offsetX - 16, offsetY + (y + .5) * cellSize);
    }
    for (const entity of w.entities) {
      const [x, y] = center(entity.position);
      const dimensions = { bridge: [2.4, .8], platform: [1, 1], workbench: [1, .5], wooden_chest: [.5, .5] }[entity.definitionId];
      if (free && !dimensions) continue;
      const halfX = free ? dimensions[0] : .38;
      const halfY = free ? dimensions[1] : .3;
      ctx.fillStyle = "#bd9966"; ctx.fillRect(x - cellSize * halfX, y - cellSize * halfY, cellSize * halfX * 2, cellSize * halfY * 2);
      ctx.strokeStyle = "#8e704c"; ctx.lineWidth = Math.max(1, cellSize * .025);
      for (let j = -2; j <= 2; j++) {
        ctx.beginPath(); ctx.moveTo(x + j * cellSize * halfX / 3, y - cellSize * halfY); ctx.lineTo(x + j * cellSize * halfX / 3, y + cellSize * halfY); ctx.stroke();
      }
    }
    ctx.strokeStyle = "#53784dcc"; ctx.lineWidth = Math.max(2, cellSize * .055); ctx.lineJoin = "round"; ctx.setLineDash([7, 6]);
    ctx.beginPath();
    let last = m.origin;
    ctx.moveTo(...center(last));
    for (const step of steps.slice(0, index)) {
      if (!step.position || free && step.status !== "committed") { last = null; continue; }
      if (last) ctx.lineTo(...center(step.position));
      else ctx.moveTo(...center(step.position));
      last = step.position;
    }
    ctx.stroke(); ctx.setLineDash([]);
    const [ox, oy] = center(m.origin);
    ctx.strokeStyle = "#697d51"; ctx.lineWidth = Math.max(2, cellSize * .035);
    ctx.beginPath(); ctx.arc(ox, oy, cellSize * .33, 0, Math.PI * 2); ctx.stroke();
    if (m.goal) {
      const [gx, gy] = center(m.goal.target), r = cellSize * .22;
      ctx.fillStyle = "#b86f46"; ctx.beginPath(); ctx.moveTo(gx, gy - r); ctx.lineTo(gx + r, gy); ctx.lineTo(gx, gy + r); ctx.lineTo(gx - r, gy); ctx.closePath(); ctx.fill();
    }
    const current = index === 0 ? m.origin : steps[index - 1].position;
    if (current) {
      const [x, y] = center(current), overlap = m.goal && same(current, m.goal.target);
      ctx.fillStyle = "#2e624b"; ctx.strokeStyle = "#fafcf4"; ctx.lineWidth = Math.max(2, cellSize * .045);
      ctx.beginPath(); ctx.arc(x, y, cellSize * (overlap ? .16 : .21), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#fbfcf4"; ctx.beginPath(); ctx.arc(x, y - cellSize * .035, cellSize * .055, 0, Math.PI * 2); ctx.fill();
    }
  }

  $("report-file").addEventListener("change", loadFile);
  $("load-demo").addEventListener("click", loadDemo);
  $("replay-slider").addEventListener("input", (event) => selectStep(event.target.value));
  $("replay-prev").addEventListener("click", () => selectStep(Number($("replay-slider").value) - 1));
  $("replay-next").addEventListener("click", () => selectStep(Number($("replay-slider").value) + 1));
  async function loadComparison() {
    if (["postcards", "postcards-reply", "mosaic", "mosaic-reply"].includes(SAMPLE)) return;
    try {
      const response = await fetch("/reports/activity-comparison.json", { credentials: "omit", cache: "no-store" });
      if (!response.ok) return; // This optional evidence bundle is absent before ITER-0004.
      require(Number(response.headers.get("content-length") || 0) <= MAX_BYTES && response.body, "对照报告超过限制或无法读取。");
      const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true });
      let text = "", bytes = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > MAX_BYTES) { await reader.cancel(); throw new Error("对照报告超过限制。"); }
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
      const data = JSON.parse(text);
      require(data.schemaVersion === 1 && data.kind === "activity-choice-comparison" && Array.isArray(data.cases) && data.cases.length <= 8, "对照报告格式不正确。");
      const cards = data.cases.map((item) => {
        require(string(item.id) && string(item.objective) && Array.isArray(item.runs) && item.runs.length === 2, "对照场景格式不正确。");
        const card = node("article", "comparison-case");
        card.append(node("h3", "", item.id), node("p", "comparison-objective", item.objective));
        const pair = node("div", "comparison-pair");
        for (const run of item.runs) {
          require(["fixed-reference", "codex-exec"].includes(run.kind), "对照策略类型不正确。");
          const tile = node("section", "comparison-run");
          tile.append(node("h4", "", run.kind === "codex-exec" ? "GPT-6 目标选择" : "固定成本基线"));
          if (run.report) {
            const r = validate(run.report);
            const matches = r.mission.goal?.id === item.expectedGoalId;
            tile.append(node("p", "", `选择：${r.mission.goal?.label || "未产生有效选择"} · ${matches ? "符合本例目的" : "未符合本例目的"}`));
            tile.append(node("p", "", `到访${r.facts.activityCompleted === true ? "已确认" : "未确认"} · ${r.facts.returned ? "在原起点" : "未返回"} · ${statuses[r.mission.status][0]}`));
            tile.append(node("p", "", `命令 ${r.budget.used.commands} · 木材 ${r.budget.used.wood} · 外部模型 ${run.kind === "codex-exec" ? r.budget.used.modelCalls : 0} 次`));
            const button = node("button", "button comparison-open", "查看这段旅程"); button.type = "button";
            button.addEventListener("click", () => { ++generation; request?.abort(); showReport(r, `${item.id} / ${run.kind}`); $("report-content").scrollIntoView({ block: "start" }); });
            tile.append(button);
          } else tile.append(node("p", "", "本次运行未产生报告；未重试。"));
          pair.append(tile);
        }
        card.append(pair); return card;
      });
      $("comparison-cases").replaceChildren(...cards);
      put("comparison-summary", `${data.cases.length} 个预设目的，两种策略使用独立且等价的初始世界。固定基线只按可行性、木材与命令数选择；本组记录用于检查具体取舍，不代表综合能力排名。`);
      $("comparison-panel").hidden = false;
    } catch {
      $("comparison-panel").hidden = false;
      put("comparison-summary", "对照记录无法读取，请重新加载页面。当前任务报告仍可单独查看。");
    }
  }
  $("postcard-report-links").hidden = !["postcards", "postcards-reply"].includes(SAMPLE);
  $("mosaic-report-links").hidden = !["mosaic", "mosaic-reply"].includes(SAMPLE);
  $("consent-report-links").hidden = !["consent", "consent-review"].includes(SAMPLE);
  $("inbox-report-links").hidden = !["inbox", "inbox-review"].includes(SAMPLE);
  loadDemo();
  loadComparison();
})();
