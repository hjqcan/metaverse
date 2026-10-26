(() => {
  "use strict";
  const roster = {a1:"local-operator", a1_alias:"local-operator", a2:"declared-late", a3:"declared-third"};
  const colors = ["blank","leaf","river","sun","rose","ink"];
  const hex = ["#F4F0E6","#42745B","#477FA3","#E4B858","#C86A70","#37444D"];
  const fields = ["entityId","capabilityVersion","authorActorId","operatorId","commandId","baseRevision","revision","patch","stateVersion","eventCursor","paintedAtUtc","position","inventoryWood"];
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const integer = x => Number.isSafeInteger(x) && x >= 0;
  const point = x => Array.isArray(x) && x.length === 2 && x.every(Number.isFinite);
  const id = x => typeof x === "string" && /^e[0-9a-f]{32}$/.test(x);
  const instance = x => typeof x === "string" && /^w_[0-9a-f]{32}$/.test(x);
  const equal = (a,b) => Array.isArray(a) ? Array.isArray(b) && a.length === b.length && a.every((v,i) => equal(v,b[i]))
    : object(a) ? object(b) && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => equal(a[k],b[k])) : a === b;
  const target = x => object(x) && id(x.entityId) && x.definitionId === "platform" && x.definitionVersion === 1
    && x.rulesVersion === "r10" && Object.hasOwn(roster,x.ownerActorId) && x.embodiedWood === 3 && point(x.position);
  const canonical = x => [...x].sort((a,b) => a.y - b.y || a.x - b.x);
  const patch = (x, ordered = false) => Array.isArray(x) && x.length >= 1 && x.length <= 8 && x.every((p,i) => object(p)
    && Object.keys(p).length === 3 && integer(p.x) && integer(p.y) && p.x < 5 && p.y < 5 && colors.includes(p.color)
    && !x.slice(0,i).some(previous => previous.x === p.x && previous.y === p.y)
    && (!ordered || i === 0 || x[i-1].y * 5 + x[i-1].x < p.y * 5 + p.x));
  const edit = x => object(x) && fields.every(k => Object.hasOwn(x,k)) && id(x.entityId) && x.capabilityVersion === 1
    && Object.hasOwn(roster,x.authorActorId) && x.operatorId === roster[x.authorActorId] && typeof x.commandId === "string" && x.commandId.length > 0
    && integer(x.baseRevision) && integer(x.revision) && x.revision === x.baseRevision + 1 && patch(x.patch,true)
    && integer(x.stateVersion) && x.stateVersion > 0 && x.eventCursor === x.stateVersion + 1
    && typeof x.paintedAtUtc === "string" && Number.isFinite(Date.parse(x.paintedAtUtc))
    && point(x.position) && integer(x.inventoryWood) && x.inventoryWood <= 12;
  const goal = x => object(x) && Object.keys(x).length === 3 && id(x.entityId) && integer(x.expectedCanvasRevision) && patch(x.patch);
  const action = x => object(x) && Object.keys(x).length === 5 && x.type === "paint_entity_canvas" && x.capabilityVersion === 1
    && goal({entityId:x.entityId, expectedCanvasRevision:x.expectedCanvasRevision, patch:x.patch});
  const record = x => edit(x) && instance(x.worldInstanceId);
  function capability(x) {
    return object(x) && x.capability === "entity-canvas-v1" && x.version === 1 && x.width === 5 && x.height === 5
      && x.reach === 1.6 && x.maxPatchCells === 8 && x.paintRule === "unowned-or-author-v1" && target(x.target)
      && object(x.adoption) && Object.keys(x.adoption).length === 3 && instance(x.adoption.worldInstanceId)
      && integer(x.adoption.stateVersion) && x.adoption.stateVersion > 0 && x.adoption.eventCursor === x.adoption.stateVersion + 1
      && integer(x.revision) && x.editCount === x.revision && Array.isArray(x.cells) && x.cells.length === 25
      && x.cells.every((c,i) => object(c) && c.x === i % 5 && c.y === Math.floor(i / 5) && colors.includes(c.color)
        && (c.authorActorId === null ? c.color === "blank" && c.commandId === null && c.stateVersion === null
          : Object.hasOwn(roster,c.authorActorId) && typeof c.commandId === "string" && c.commandId.length > 0
            && integer(c.stateVersion) && c.stateVersion > x.adoption.stateVersion))
      && Array.isArray(x.palette) && x.palette.length === 6 && x.palette.every((p,i) => object(p) && p.id === colors[i] && p.hex === hex[i] && typeof p.label === "string")
      && Array.isArray(x.recentEdits) && x.recentEdits.length === Math.min(x.editCount,50)
      && x.recentEdits.every((e,i) => edit(e) && e.entityId === x.target.entityId && e.revision === x.revision - x.recentEdits.length + i + 1);
  }
  function validate(data, require) {
    const {mission:m,facts:f,budget:b,world:w,steps} = data, uses = m.goal?.entityCanvas !== undefined;
    require(m.allowEntityCanvas === undefined || typeof m.allowEntityCanvas === "boolean", "平台地画权限应为布尔值。");
    require(!uses || m.rulesVersion === "r10" && m.preconditionMode === "actor-state-v1" && goal(m.goal.entityCanvas)
      && !m.goal.buildRecipeId && !m.goal.materialAccess && !m.goal.transfer && !m.goal.activityId && !m.goal.entityNote
      && !m.allowBuild && !m.allowGather && !m.allowTransfer && !m.allowMaterialAccess && !m.allowEntityNotes
      && !m.sharePostcard && !m.paintMosaic && !m.proposeMosaic && !m.reviewMosaicProposal, "平台地画需要独立原平台、原版本和固定草图。");
    require(!uses || integer(b.limits.queries) && b.limits.queries >= 1 && b.limits.queries <= 5000 && integer(b.used.queries), "平台地画缺少累计查询预算。");
    require(f.entityCanvasPainted === undefined || typeof f.entityCanvasPainted === "boolean", "地画完成事实应为布尔值。");
    require(f.entityCanvasEdit === undefined || f.entityCanvasEdit === null || record(f.entityCanvasEdit), "原地画修改事实不完整。");
    require(w.entityCanvas === undefined || w.entityCanvas === null || capability(w.entityCanvas), "平台地画快照格式不正确。");
    if (w.entityCanvas) require(w.entityCanvas.adoption.worldInstanceId === w.instanceId
      && w.entities.some(entity => equal(entity,w.entityCanvas.target))
      && w.entityCanvas.adoption.stateVersion <= f.endStateVersion
      && w.entityCanvas.cells.every(c => c.stateVersion === null || c.stateVersion <= f.endStateVersion)
      && w.entityCanvas.recentEdits.every(e => e.stateVersion <= f.endStateVersion), "地画快照与原世界或观察版本不一致。");
    for (const s of steps.filter(s => s.action.type === "paint_entity_canvas")) {
      require(uses && action(s.action), "地画动作缺少原平台目标。");
      if (s.status === "committed") require(record(s.entityCanvasEvidence), "地画步骤缺少原修改依据。");
    }
  }
  function assess(data) {
    const {mission:m,facts:f,world:w,steps,budget:b} = data, uses = Boolean(m.goal?.entityCanvas);
    const claims = steps.filter(s => s.action.type === "paint_entity_canvas" && s.status === "committed");
    const e = f.entityCanvasEdit, s = claims[0], originalTarget = w.entities.find(t => t.entityId === m.goal?.entityCanvas?.entityId);
    const verified = Boolean(uses && m.allowEntityCanvas === true && f.entityCanvasPainted === true && record(e) && claims.length === 1
      && target(originalTarget) && equal(originalTarget.position,m.goal.target)
      && e.worldInstanceId === m.worldInstanceId && e.worldInstanceId === w.instanceId && e.authorActorId === m.actorId && e.operatorId === roster[m.actorId]
      && e.entityId === m.goal.entityCanvas.entityId && e.baseRevision === m.goal.entityCanvas.expectedCanvasRevision && equal(e.patch,canonical(m.goal.entityCanvas.patch))
      && s.commandId === e.commandId && s.stateVersion === e.stateVersion && s.inventoryWood === e.inventoryWood && equal(s.position,e.position)
      && Math.hypot(e.position[0]-originalTarget.position[0],e.position[1]-originalTarget.position[1]) <= 1.600001
      && equal(s.action,{type:"paint_entity_canvas",capabilityVersion:1,...m.goal.entityCanvas}) && equal(s.entityCanvasEvidence,e)
      && s.evidenceSource === "original_receipt_edit_and_event");
    // Public reports have no full query log. Check only the observable lower
    // bound and command counts; this cannot authenticate all failed reads.
    const budgetConsistent = !uses || b.used.commands === steps.length && new Set(steps.map(s => s.commandId)).size === steps.length
      && b.used.queries >= (claims.length ? 4 : 1) && Object.keys(b.limits).every(k => b.used[k] <= b.limits[k]);
    return {uses,verified,budgetConsistent,consistent:verified || f.entityCanvasPainted !== true && !e && claims.length === 0};
  }
  function render(data, assessment) {
    const $ = id => document.getElementById(id), {mission:m,facts:f,world:w} = data;
    $("entity-canvas-panel").hidden = !assessment.uses;
    $("entity-canvas-fact").dataset.verified = String(assessment.verified);
    $("entity-canvas-fact").textContent = assessment.verified
      ? `本次修改已核对 · 居民 ${f.entityCanvasEdit.authorActorId} · #${f.entityCanvasEdit.revision} · ${f.entityCanvasEdit.patch.length} 格 · 无木材支出`
      : "尚未确认本次绘制；当前颜色和到达地点不能代替原修改事实。";
    $("entity-canvas-original").textContent = assessment.uses ? `原草图基准 #${m.goal.entityCanvas.expectedCanvasRevision}：`
      + m.goal.entityCanvas.patch.map(p => `(${p.x},${p.y}) ${p.color}`).join("；") : "";
    const cap = w.entityCanvas;
    $("entity-canvas-grid").replaceChildren();
    $("entity-canvas-current").textContent = capability(cap)
      ? `最后观察的图 #${cap.revision} · 平台建造者 ${cap.target.ownerActorId} · 修改 ${cap.editCount} 次（最近列表最多50次）`
        + (assessment.verified && cap.revision < f.entityCanvasEdit.revision ? "。此快照早于本次确认，尚未再次观察。" : "") : "当前图未提供。";
    if (capability(cap)) for (const cell of cap.cells) {
      const tile = document.createElement("div");
      tile.className = "entity-canvas-cell";
      tile.style.backgroundColor = hex[colors.indexOf(cell.color)];
      tile.dataset.color = cell.color;
      tile.dataset.author = cell.authorActorId || "";
      tile.textContent = cell.authorActorId || "无人";
      tile.title = `(${cell.x},${cell.y}) · ${cell.color} · 作者 ${cell.authorActorId || "无人"}`;
      tile.setAttribute("aria-label",tile.title);
      $("entity-canvas-grid").append(tile);
    }
  }
  window.EntityCanvasReport = {validate,assess,action,render};
})();
