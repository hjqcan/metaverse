(() => {
  "use strict";

  const WORLD = "foundation-01";
  const API = `/v1/worlds/${WORLD}`;
  const TOKEN_KEY = "foundation.v1.token";
  const PENDING_KEY = "foundation.v1.pending";
  const POLL_MS = 1500;
  const REQUEST_MS = 6500;
  const $ = (id) => document.getElementById(id);
  const mosaic = window.MosaicUI;
  const consent = window.ConsentUI;
  const inboxApi = window.MosaicInbox;
  const renderEntry = window.EntryGuideUI.create($("entry-panel"), (id) => {
    if (!observationHealthy) return;
    const place = observation?.entryGuide?.places.find(p => p.id === id);
    if (!place) return;
    if (place.activityId) ui["activity-select"].value = place.activityId;
    selectCell(place.position);
  });
  const ui = Object.fromEntries([
    "token-input", "connect-button", "disconnect-button", "connection-status", "world-canvas",
    "actor-position", "inventory-wood", "depot-wood", "depot-position", "state-version",
    "claim-quantity", "claim-button", "build-button", "selected-cell", "selection-detail",
    "feedback", "pending-panel", "pending-status", "pending-detail", "query-command-button",
    "retry-command-button", "move-up", "move-down", "move-left", "move-right", "snapshot-status",
    "resident-title", "resident-avatar", "audit-status", "world-summary", "event-list", "event-cursor",
    "cell-x", "cell-y", "recipe-select", "recipe-cost", "build-copy", "rules-version",
    "page-title", "scenario-copy", "map-title", "water-legend", "bridge-legend",
    "activities-panel", "activity-catalog", "activity-select", "visit-button", "activity-hint", "visit-history",
    "postcards-panel", "postcard-location", "postcard-list", "postcard-feed-label", "postcard-text", "postcard-count", "postcard-button", "postcard-hint",
    "mosaic-panel", "mosaic-version", "mosaic-public", "mosaic-editor", "mosaic-palette", "mosaic-authors", "mosaic-draft-count", "mosaic-draft-note", "mosaic-publish", "mosaic-clear", "mosaic-hint", "mosaic-public-note", "proposal-compose", "proposal-text", "proposal-count", "consent-panel", "consent-list",
    "gather-panel", "gather-node", "gather-hint", "gather-button", "claim-section", "resource-source-label", "tree-legend", "depot-legend", "goal-legend", "wall-label",
    "inbox-scope", "inbox-status", "inbox-counts", "inbox-message", "inbox-newest", "inbox-newer", "inbox-older", "inbox-visit", "inbox-location"
  ].map((id) => [id, $(id)]));
  const isInt = (n) => Number.isSafeInteger(n) && n >= 0;
  const isCell = (p) => Array.isArray(p) && p.length === 2 && p.every((n) => isInt(n) && n < 8);
  const sameCell = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];
  const coord = (p) => `(${p[0]}, ${p[1]})`;
  const supportedRules = new Set(["r1", "r2", "r3", "r4", "r5", "r6", "r7"]);
  const validPostcardText = (text) => typeof text === "string" && Array.from(text).length >= 1 && Array.from(text).length <= 160 && /[^\p{White_Space}]/u.test(text) && !/[\p{Cc}\p{Cs}]/u.test(text);
  const validPostcard = (p) => p && typeof p.activityId === "string" && typeof p.authorActorId === "string" && typeof p.commandId === "string" && typeof p.visitCommandId === "string" && validPostcardText(p.text) && isInt(p.stateVersion) && isCell(p.position) && Number.isFinite(Date.parse(p.sharedAtUtc));
  const recipeDefinitions = { "platform.v1": "platform", "bridge.v1": "bridge" };
  const entityName = (definitionId) => definitionId === "bridge" ? "桥" : definitionId === "platform" ? "平台" : "设施";
  const knownRejections = new Set(["NO_PUBLIC_DEPOT", "GATHERING_UNAVAILABLE", "RESOURCE_NOT_FOUND", "RESOURCE_DEPLETED", "STALE_STATE", "RULES_VERSION_MISMATCH", "IDEMPOTENCY_CONFLICT", "CELL_OCCUPIED", "INSUFFICIENT_RESOURCE", "UNREACHABLE", "NOT_AT_ACTIVITY", "ACTIVITY_NOT_FOUND", "ACTIVITY_UNAVAILABLE", "POSTCARD_UNAVAILABLE", "VISIT_REQUIRED", "VISIT_ALREADY_SHARED", "MOSAIC_UNAVAILABLE", "MOSAIC_LOCATION_UNAVAILABLE", "VISIT_ALREADY_PAINTED", "MOSAIC_CHANGED", "MOSAIC_UNCHANGED", "MOSAIC_CONSENT_REQUIRED", "MOSAIC_CONSENT_UNAVAILABLE", "VISIT_ALREADY_PROPOSED", "MOSAIC_PROPOSAL_TARGET_INVALID", "MOSAIC_PROPOSAL_NOT_FOUND", "MOSAIC_REVIEW_FORBIDDEN", "MOSAIC_PROPOSAL_REVIEWED"]);
  const errorText = {
    STALE_STATE: "世界已更新，请等待重新观察后再次操作。",
    RULES_VERSION_MISMATCH: "世界规则版本已变化，请刷新页面后重试。",
    IDEMPOTENCY_CONFLICT: "命令 ID 对应另一份载荷，本次请求被拒绝。",
    CELL_OCCUPIED: "选择格已有设施，请选择另一格。",
    INSUFFICIENT_RESOURCE: "木材不足，无法完成这次操作。",
    UNREACHABLE: "无法到达：请检查墙、未铺桥水面、地图边界或与目标的距离。",
    INVALID_REQUEST: "请求格式被拒绝，原命令已保留。",
    IDENTITY_OVERRIDE: "身份字段被拒绝，原命令已保留。",
    WORLD_NOT_FOUND: "未找到这个世界，请检查本机服务。"
  };

  let storageError = false;
  let pendingByActor = Object.create(null);
  let token = "";
  let generation = 0;
  let identity = null;
  let observation = null;
  let observationHealthy = false;
  let eventsHealthy = false;
  // This is only a lower bound for accepting observations, never a displayed/predicted version.
  let observationFloor = 0;
  let selected = null;
  let pending = null;
  let commandBusy = false;
  let connecting = false;
  let connection = "disconnected";
  let recoveryNeeded = true;
  let eventCursor = 0;
  let publicEvents = [];
  let syncPromise = null;
  let pollTimer = null;
  let draftKey = null;
  let mosaicKey = null;
  let mosaicDraft = null;
  let selectedColor = "river";
  let proposalDraftKey = null;
  let inbox = newInbox();
  const requests = new Set();

  class SessionChanged extends Error {}
  class Unauthorized extends Error {}
  class ReadFailure extends Error {}

  function feedback(message, tone = "neutral") {
    ui.feedback.textContent = message;
    ui.feedback.dataset.tone = tone;
  }

  function storageSet(key, value) {
    try {
      if (value === null) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, value);
      return true;
    } catch {
      storageError = true;
      return false;
    }
  }

  function loadStorage() {
    try {
      token = sessionStorage.getItem(TOKEN_KEY) || "";
      const saved = JSON.parse(sessionStorage.getItem(PENDING_KEY) || "{}");
      if (!saved || typeof saved !== "object" || Array.isArray(saved)) throw new Error("Invalid pending store");
      for (const [actorId, item] of Object.entries(saved)) {
        if (!item || item.worldId !== WORLD || item.actorId !== actorId || typeof item.body !== "string") throw new Error("Invalid pending record");
        const body = JSON.parse(item.body);
        if (!/^[A-Za-z0-9_-]{1,128}$/.test(item.commandId) || body.commandId !== item.commandId || body.schemaVersion !== 1 || !supportedRules.has(body.rulesVersion) || !isInt(body.expectedStateVersion) || !["move", "claim", "gather", "build", "visit", "postcard", "mosaic", "mosaic_propose", "mosaic_review"].includes(body.action?.type)) throw new Error("Invalid pending body");
        if (body.action.type === "mosaic_review" && !consent.validProposal(item.proposal)) throw new Error("Missing original proposal");
        pendingByActor[actorId] = item;
      }
    } catch {
      storageError = true;
      feedback("此标签页的恢复记录无法读取。为避免重复动作，已暂停新操作，请保留标签页并检查浏览器存储。", "error");
    }
  }

  function persistPending() {
    return storageSet(PENDING_KEY, JSON.stringify(pendingByActor));
  }

  function context() { return { generation, token }; }
  function current(ctx) { return ctx.generation === generation && ctx.token === token; }

  function resetSession(nextToken) {
    generation += 1;
    for (const controller of requests) controller.abort();
    requests.clear();
    clearTimeout(pollTimer);
    syncPromise = null;
    token = nextToken;
    identity = null;
    observation = null;
    observationHealthy = false;
    eventsHealthy = false;
    observationFloor = 0;
    selected = null;
    pending = null;
    commandBusy = false;
    eventCursor = 0;
    publicEvents = [];
    recoveryNeeded = true;
    inbox = newInbox();
    ui["consent-list"].replaceChildren();
    ui["inbox-scope"].value = "received";
    ui["inbox-status"].value = "pending";
    ui["inbox-counts"].textContent = "计数尚未确认，待办数量未知。";
    ui["inbox-message"].textContent = "等待连接。";
    ui["inbox-location"].textContent = "花园位于 (1, 6)，请先走到现场。";
    proposalDraftKey = null;
    ui["proposal-text"].value = "";
    ui["token-input"].value = "";
  }

  function unauthorized() {
    const hadPending = Object.keys(pendingByActor).length > 0;
    resetSession("");
    storageSet(TOKEN_KEY, null);
    connecting = false;
    connection = "unauthorized";
    feedback(`会话无效、过期或已撤销，请粘贴有效 token 重新连接。${hadPending ? "未决命令已保留；同一居民重新连接后可查询。" : ""}`, "error");
    render();
  }

  async function request(path, options, ctx, relevant = () => true) {
    if (!current(ctx) || !ctx.token || !relevant()) throw new SessionChanged();
    const controller = new AbortController();
    requests.add(controller);
    const timeout = setTimeout(() => controller.abort(), REQUEST_MS);
    try {
      const response = await fetch(path, {
        ...options,
        headers: { Accept: "application/json", Authorization: `Bearer ${ctx.token}`, ...(options?.headers || {}) },
        cache: "no-store", credentials: "same-origin", redirect: "error", signal: controller.signal
      });
      if (!current(ctx) || !relevant()) throw new SessionChanged();
      if (response.status === 401) {
        unauthorized();
        throw new Unauthorized();
      }
      const data = await response.json();
      if (!current(ctx) || !relevant()) throw new SessionChanged();
      return { status: response.status, ok: response.ok, data };
    } catch (error) {
      if (!current(ctx) && !(error instanceof Unauthorized)) throw new SessionChanged();
      throw error;
    } finally {
      clearTimeout(timeout);
      requests.delete(controller);
    }
  }

  function explain(data) {
    const code = data?.error?.code;
    const message = typeof data?.error?.message === "string" ? data.error.message : errorText[code];
    return message ? `${message}${code ? `（${code}）` : ""}` : "服务暂时无法确认结果。";
  }

  function validObservation(d) {
    return d && d.schemaVersion === 1 && supportedRules.has(d.rulesVersion) && !d.error && isInt(d.stateVersion) && isInt(d.eventCursor)
      && typeof d.identity?.actorId === "string" && typeof d.identity?.sessionId === "string"
      && d.self?.actorId === d.identity.actorId && isCell(d.self.position) && isInt(d.self.inventory?.wood)
      && d.world?.id === WORLD && d.world.width === 8 && d.world.height === 8
      && Array.isArray(d.world.blocked) && d.world.blocked.every(isCell) && isCell(d.world.goal)
      && (d.world.water === undefined || (Array.isArray(d.world.water) && d.world.water.every(isCell)))
      && (d.world.scenarioId === undefined || typeof d.world.scenarioId === "string")
      && (d.recipes === undefined || (Array.isArray(d.recipes) && d.recipes.every((r) => r && typeof r.id === "string" && typeof r.definitionId === "string" && isInt(r.woodCost))))
      && (d.rulesVersion !== "r2" || (d.world.scenarioId === "passage-v1" && Array.isArray(d.world.water) && Array.isArray(d.recipes)))
      && (!["r3", "r4", "r5", "r6", "r7"].includes(d.rulesVersion) || (d.world.scenarioId === ({r3: "activities-v1", r4: "postcards-v1", r5: "mosaic-v1", r6: "consent-v1", r7: "wilderness-v1"})[d.rulesVersion] && Array.isArray(d.world.water) && Array.isArray(d.recipes)
        && Array.isArray(d.activities) && d.activities.every((a) => a && typeof a.id === "string" && typeof a.label === "string" && typeof a.description === "string" && isCell(a.position))
        && new Set(d.activities.map((a) => a.id)).size === d.activities.length
        && Array.isArray(d.self.visits) && d.self.visits.length <= 100 && d.self.visits.every((v) => v && typeof v.activityId === "string" && typeof v.commandId === "string" && isInt(v.stateVersion) && isCell(v.position) && Number.isFinite(Date.parse(v.visitedAtUtc)))))
      && (!["r4", "r5", "r6"].includes(d.rulesVersion) || (Array.isArray(d.postcards) && d.postcards.length <= 50 && d.postcards.every(validPostcard)
        && Array.isArray(d.self.postcards) && d.self.postcards.length <= 100 && d.self.postcards.every((p) => validPostcard(p) && p.authorActorId === d.self.actorId)))
      && (!["r5", "r6"].includes(d.rulesVersion) || (mosaic.validBoard(d.mosaic) && d.mosaic.cells.every((c) => c.stateVersion === null || c.stateVersion <= d.stateVersion)
        && Array.isArray(d.mosaicEdits) && d.mosaicEdits.length <= 50 && d.mosaicEdits.every(mosaic.validEdit)
        && Array.isArray(d.self.mosaicEdits) && d.self.mosaicEdits.length <= 100 && d.self.mosaicEdits.every((e) => mosaic.validEdit(e) && e.authorActorId === d.self.actorId)))
      && (d.rulesVersion !== "r6" || (Array.isArray(d.mosaicProposals) && d.mosaicProposals.length <= 50 && d.mosaicProposals.every(consent.validProposal)
        && Array.isArray(d.self.mosaicProposals) && d.self.mosaicProposals.length <= 100 && d.self.mosaicProposals.every((p) => consent.validProposal(p) && p.authorActorId === d.self.actorId)
        && Array.isArray(d.self.mosaicReviews) && d.self.mosaicReviews.length <= 100 && d.self.mosaicReviews.every((r) => consent.validReview(r) && r.authorActorId === d.self.actorId)))
      && (d.rulesVersion !== "r7" || (d.gathering?.version === 1 && d.gathering.quantityPerAction === 1
        && d.depot?.available === false && d.depot.wood === 0 && Array.isArray(d.resourceNodes)
        && d.resourceNodes.every(n => n && typeof n.nodeId === "string" && n.kind === "tree" && isCell(n.position)
          && isInt(n.initialWood) && isInt(n.remainingWood) && n.remainingWood <= n.initialWood)
        && new Set(d.resourceNodes.map(n => n.nodeId)).size === d.resourceNodes.length
        && new Set(d.resourceNodes.map(n => n.position.join(','))).size === d.resourceNodes.length
        && d.resourceNodes.filter(n => n.remainingWood > 0).every(n => d.world.blocked.some(p => sameCell(p,n.position)))))
      && isCell(d.depot?.position) && isInt(d.depot.wood)
      && Array.isArray(d.residents) && d.residents.every((r) => typeof r.actorId === "string" && isCell(r.position))
      && Array.isArray(d.entities) && d.entities.every((e) => typeof e.entityId === "string" && isCell(e.position));
  }

  function isPassage() {
    return observation?.rulesVersion === "r2" && observation.world.scenarioId === "passage-v1" || isActivities();
  }

  function isWilderness() { return observation?.rulesVersion === "r7" && observation.world.scenarioId === "wilderness-v1"; }
  function resourceNodes() { return isWilderness() ? observation.resourceNodes : []; }
  function selectedTree() { return resourceNodes().find(n => sameCell(n.position, selected)); }
  function isConsent() { return observation?.rulesVersion === "r6" && observation.world.scenarioId === "consent-v1"; }
  function isMosaic() { return observation?.rulesVersion === "r5" && observation.world.scenarioId === "mosaic-v1" || isConsent(); }
  function isPostcards() { return observation?.rulesVersion === "r4" && observation.world.scenarioId === "postcards-v1" || isMosaic(); }
  function isActivities() { return observation?.rulesVersion === "r3" && observation.world.scenarioId === "activities-v1" || isPostcards() || isWilderness(); }
  function activities() { return isActivities() ? observation.activities : []; }
  function activityName(id) { return activities().find((a) => a.id === id)?.label || id; }
  function selectedActivity() { return activities().find((a) => a.id === ui["activity-select"].value); }

  function waterCells() { return observation?.world.water || []; }
  function isWater(cell) { return waterCells().some((p) => sameCell(p, cell)); }
  function wallCells() { return observation ? observation.world.blocked.filter((p) => !isWater(p) && !resourceNodes().some(n => n.remainingWood > 0 && sameCell(n.position, p))) : []; }

  function availableRecipes() {
    if (!observation) return [];
    // Only the legacy r1 service may omit its single, frozen platform recipe.
    const recipes = observation.recipes ?? [{ id: "platform.v1", definitionId: "platform", woodCost: 3 }];
    return recipes.filter((r, index) => Object.hasOwn(recipeDefinitions, r.id)
      && r.definitionId === recipeDefinitions[r.id] && (r.id !== "bridge.v1" || isPassage())
      && recipes.findIndex((other) => other.id === r.id) === index);
  }

  function selectedRecipe() { return availableRecipes().find((r) => r.id === ui["recipe-select"].value); }

  async function observe(ctx) {
    const response = await request(`${API}/observation`, {}, ctx);
    if (!response.ok || !validObservation(response.data)) throw new ReadFailure(response.ok ? "观察响应不符合当前世界契约。" : explain(response.data));
    const data = response.data;
    if (identity && (identity.actorId !== data.identity.actorId || identity.sessionId !== data.identity.sessionId)) throw new ReadFailure("会话身份发生变化，请重新连接。");
    const lowerBound = Math.max(observationFloor, observation?.stateVersion || 0);
    if (data.stateVersion < lowerBound) throw new ReadFailure("较旧的观察已忽略，正在等待最新世界状态。");
    identity = data.identity;
    observation = data;
    observationFloor = data.stateVersion;
    observationHealthy = true;
    // Bind recovery to the observed Actor, never to the token string or a historical receipt session.
    pending = pendingByActor[identity.actorId] || null;
    prepareInbox();
    render();
  }

  function newInbox() {
    return { mode: null, query: { scope: "received", status: "pending", before: null, limit: 20 }, history: [],
      page: null, deferredPage: null, healthy: false, loading: false, error: "", serial: 0, flight: null };
  }

  function prepareInbox() {
    const mode = !isConsent() ? null : inboxApi.supported(observation) ? "full"
      : observation.mosaicProposalInbox == null ? "legacy" : "unsupported";
    if (mode !== inbox.mode) {
      inbox = newInbox(); inbox.mode = mode;
      ui["consent-list"].replaceChildren();
    }
    if (mode === "legacy") {
      applyInboxPage(inboxApi.legacyPage(observation, inbox.query));
      inbox.error = "";
    }
    if (mode === "unsupported") inbox.error = "收件箱能力版本无法确认，尚未更新；审阅已暂停。";
  }

  function inboxReady() {
    return inbox.healthy && !inbox.loading && inboxApi.sameQuery(inbox.page?.query, inbox.query) && observationHealthy
      && inbox.page.stateVersion >= observationFloor;
  }

  function applyInboxPage(page) {
    const focused = document.activeElement;
    const editing = focused?.matches("textarea") && ui["consent-list"].contains(focused) ? focused.closest("article") : null;
    if (editing && inboxApi.sameQuery(inbox.page?.query, page.query)
      && !page.items.some((p) => p.authorActorId === editing.dataset.proposer && p.commandId === editing.dataset.command)) {
      // A new first-page item can displace the row being edited. Keep the old, at-most-20
      // rows until focus leaves, explicitly stale and unable to authorize review.
      inbox.deferredPage = page; inbox.healthy = false;
    } else {
      inbox.page = page; inbox.deferredPage = null; inbox.healthy = true;
    }
  }

  async function refreshInbox(ctx = context()) {
    if (!current(ctx) || !isConsent() || !identity) return;
    if (inbox.mode !== "full") { prepareInbox(); renderConsent(); return; }
    const state = inbox;
    if (state.flight) return state.flight;
    const serial = ++state.serial, query = { ...state.query }, actor = { ...identity };
    const active = () => current(ctx) && state === inbox && serial === state.serial;
    state.loading = true; state.healthy = false; state.error = "";
    renderConsent();
    const running = (async () => {
      try {
        const params = new URLSearchParams({ scope: query.scope, status: query.status, limit: String(query.limit) });
        if (query.before !== null) params.set("before", String(query.before));
        const response = await request(`${API}/mosaic-proposals?${params}`, {}, ctx, active);
        if (!active()) return;
        const floor = Math.max(observationFloor, observation.stateVersion, state.page?.stateVersion || 0);
        if (!response.ok || !inboxApi.validPage(response.data, query, actor, floor)) {
          throw new ReadFailure(response.ok ? "收件箱响应与身份、筛选或世界版本不一致。" : explain(response.data));
        }
        applyInboxPage(response.data);
        // A newer inbox cannot authorize review against an older canvas observation.
        if (response.data.stateVersion > observation.stateVersion) {
          observationFloor = Math.max(observationFloor, response.data.stateVersion);
          observationHealthy = false;
        }
      } catch (error) {
        if (!active() || error instanceof SessionChanged || error instanceof Unauthorized) return;
        state.healthy = false;
        state.deferredPage = null;
        state.error = `${error instanceof ReadFailure ? error.message : "连接中断、请求超时或响应无法读取。"} 收件箱未更新；保留上次内容，审阅已暂停。`;
      } finally {
        if (active()) { state.loading = false; state.flight = null; render(); }
      }
    })();
    state.flight = running;
    return running;
  }

  function changeInbox(action) {
    if (!isConsent()) return;
    if (action === "older") {
      if (!inboxReady() || inbox.page.nextBefore === null || inbox.loading) return;
      inbox.history.push(inbox.query.before);
      inbox.query.before = inbox.page.nextBefore;
    } else if (action === "newer") {
      if (!inbox.history.length) return;
      inbox.query.before = inbox.history.pop();
    } else {
      const scope = ui["inbox-scope"].value, status = ui["inbox-status"].value;
      if (!inboxApi.scopes.includes(scope) || !inboxApi.statuses.includes(status)) return;
      inbox.query = { scope, status, before: null, limit: 20 }; inbox.history = [];
    }
    // Invalidate before starting another request; neither a late success nor failure may repaint it.
    inbox.serial += 1; inbox.flight = null; inbox.deferredPage = null; inbox.healthy = false; inbox.error = "";
    void refreshInbox();
  }

  async function readEvents(ctx) {
    const after = eventCursor;
    const response = await request(`${API}/events?after=${after}`, {}, ctx);
    if (response.status === 409 && response.data?.error?.code === "CURSOR_AHEAD") {
      await observe(ctx);
      eventCursor = observation.eventCursor;
      publicEvents = [];
      eventsHealthy = false;
      throw new ReadFailure("事件游标已重新对齐，正在重新读取公共事件。");
    }
    const d = response.data;
    if (!response.ok || d?.schemaVersion !== 1 || d.rulesVersion !== observation.rulesVersion || d.error || d.identity?.actorId !== identity?.actorId || !isInt(d.stateVersion) || !Array.isArray(d.events) || !isInt(d.nextCursor) || d.nextCursor < after) throw new ReadFailure(response.ok ? "公共事件响应无法确认。" : explain(d));
    let previous = after;
    for (const event of d.events) {
      if (!isInt(event.seq) || event.seq <= previous || event.seq > d.nextCursor || !isInt(event.stateVersion)) throw new ReadFailure("公共事件顺序异常，已暂停新操作。");
      previous = event.seq;
    }
    if ((d.events.length === 0 && d.nextCursor !== after) || (d.events.length && d.nextCursor !== previous)) throw new ReadFailure("公共事件游标异常，已暂停新操作。");
    for (const event of d.events) {
      // Render only the frozen public event fields; never dump server objects or private receipts.
      if (["worldSeeded", "moved", "claimed", "gathered", "built", "visited", "postcard_shared", "mosaic_painted", "mosaic_proposed", "mosaic_reviewed"].includes(event.type)) {
        publicEvents.push({ seq: event.seq, stateVersion: event.stateVersion, actorId: event.actorId, type: event.type, position: isCell(event.position) ? event.position : null, quantity: isInt(event.quantity) ? event.quantity : null, definitionId: ["platform", "bridge"].includes(event.definitionId) ? event.definitionId : null, activityId: typeof event.activityId === "string" ? event.activityId : "", targetActorId: typeof event.targetActorId === "string" ? event.targetActorId : "", decision: ["accept", "reject"].includes(event.decision) ? event.decision : null });
      }
    }
    publicEvents = publicEvents.slice(-12);
    // Only the event response's nextCursor advances the normal polling cursor.
    eventCursor = d.nextCursor;
    eventsHealthy = true;
    if (d.stateVersion > observation.stateVersion) {
      observationFloor = Math.max(observationFloor, d.stateVersion);
      observationHealthy = false;
      await observe(ctx);
    }
  }

  function settledReceipt(response, original) {
    const d = response.data;
    const action = JSON.parse(original.body).action;
    if (response.status === 200 && action.type === "gather" && (d?.result?.action !== "gather"
      || d.result.nodeId !== action.nodeId || d.result.quantity !== 1 || !isInt(d.result.remainingWood)
      || !isInt(d.result.inventoryWood) || !isCell(d.result.position)
      || d.stateVersion !== JSON.parse(original.body).expectedStateVersion + 1)) return false;
    if (response.status === 200 && action.type === "mosaic_propose" && (d?.result?.action !== action.type || !consent.proposalMatches(d.result, action, original.actorId, original.commandId, JSON.parse(original.body).expectedStateVersion))) return false;
    if (response.status === 200 && action.type === "mosaic_review" && (d?.result?.action !== action.type || !consent.reviewMatches(d.result, action, original.actorId, original.commandId, JSON.parse(original.body).expectedStateVersion, original.proposal))) return false;
    if (response.status === 200 && action.type === "mosaic" && (d?.result?.action !== "mosaic" || !mosaic.validEdit(d.result)
      || d.result.authorActorId !== original.actorId || d.result.commandId !== original.commandId || d.result.activityId !== action.activityId
      || d.result.visitCommandId !== action.visitCommandId || d.result.baseRevision !== action.expectedMosaicRevision || !mosaic.equalPatch(d.result.patch, action.patch)
      || d.result.stateVersion !== d.stateVersion || d.stateVersion !== JSON.parse(original.body).expectedStateVersion + 1)) return false;
    if (response.status === 200 && action.type === "visit" && (d?.result?.action !== "visit" || d.result.activityId !== action.activityId || !isCell(d.result.position) || !Number.isFinite(Date.parse(d.result.visitedAtUtc)))) return false;
    if (response.status === 200 && action.type === "postcard" && (d?.result?.action !== "postcard" || !validPostcard(d.result)
      || d.result.authorActorId !== original.actorId || d.result.commandId !== original.commandId || d.result.activityId !== action.activityId
      || d.result.visitCommandId !== action.visitCommandId || d.result.text !== action.text || d.result.stateVersion !== d.stateVersion
      || d.stateVersion <= JSON.parse(original.body).expectedStateVersion
      || !sameCell(d.result.position, activities().find((a) => a.id === action.activityId)?.position))) return false;
    return d?.schemaVersion === 1 && d.commandId === original.commandId && d.identity?.actorId === original.actorId && isInt(d.stateVersion)
      && ((response.status === 200 && d.status === "committed" && !d.error)
        || ([403, 404, 409, 422].includes(response.status) && d.status === "rejected" && knownRejections.has(d.error?.code)));
  }

  function acceptReceipt(response, original) {
    const d = response.data;
    if (!pending || pending.commandId !== original.commandId || identity?.actorId !== original.actorId) return false;
    delete pendingByActor[original.actorId];
    pending = null;
    persistPending();
    observationHealthy = false;
    observationFloor = Math.max(observationFloor, d.stateVersion);
    if (d.status === "committed") {
      const action = JSON.parse(original.body).action;
      const result = action.type === "move" ? "移动已确认" : action.type === "gather" ? "砍取 1 单位木材已确认" : action.type === "claim" ? `领取 ${action.quantity} 单位木材已确认` : action.type === "visit" ? `到访${activityName(action.activityId)}已确认` : action.type === "postcard" ? `在${activityName(action.activityId)}分享手记已确认` : action.type === "mosaic_propose" ? "修改提议已发表，画布尚未改变" : action.type === "mosaic_review" ? action.decision === "accept" ? "已同意提议并确认改图" : "已拒绝提议，画布保持原样" : action.type === "mosaic" ? `花园画布的 ${action.patch.length} 格修改已确认` : `在 ${coord(action.at)} 建造${entityName(recipeDefinitions[action.recipeId])}已确认`;
      if (action.type === "postcard") {
        const key = postcardDraftKey(original.actorId, action.activityId);
        storageSet(key, null);
        if (draftKey === key) ui["postcard-text"].value = "";
      }
      if (["mosaic", "mosaic_propose"].includes(action.type)) {
        const key = mosaicDraftKey(original.actorId);
        storageSet(key, null);
        if (mosaicKey === key) mosaicDraft = null;
      }
      if (action.type === "mosaic_propose") {
        storageSet(`foundation.v1.proposal-text.${original.actorId}`, null);
        if (identity?.actorId === original.actorId) ui["proposal-text"].value = "";
      }
      if (action.type === "mosaic_review") storageSet(reviewDraftKey(original.actorId, action.proposalActorId, action.proposalCommandId), null);
      feedback(`${result}。位置与资源以最新观察为准。`, "success");
    } else {
      feedback(`操作被拒绝：${explain(d)} 已保留原有资源，正在重新观察。`, "error");
    }
    render();
    return true;
  }

  async function lookupPending(ctx) {
    const original = pending;
    if (!original || original.actorId !== identity?.actorId) return;
    const response = await request(`${API}/commands/${encodeURIComponent(original.commandId)}`, {}, ctx);
    if (settledReceipt(response, original)) {
      acceptReceipt(response, original);
      return;
    }
    if (response.status === 404 && response.data?.error?.code === "COMMAND_NOT_FOUND") {
      feedback("尚未查到这条命令（404）：结果仍未知，原 ID 与载荷已保留。可查询结果或原样重试。", "warning");
      return;
    }
    throw new ReadFailure(`命令结果仍待确认。${explain(response.data)}`);
  }

  function markOffline(message) {
    observationHealthy = false;
    eventsHealthy = false;
    connection = "offline";
    recoveryNeeded = true;
    feedback(`${message || "连接中断或读取失败。"}${pending ? "未决动作已保留，请勿创建替代命令。" : "新动作已暂停。"} 正在尝试恢复连接。`, "warning");
    render();
  }

  async function synchronize(ctx) {
    const wasRecovering = recoveryNeeded;
    try {
      await observe(ctx);
      if (wasRecovering && pending) {
        await lookupPending(ctx);
        if (!observationHealthy) await observe(ctx);
      }
      await readEvents(ctx);
      await refreshInbox(ctx);
      if (!current(ctx)) return;
      connection = "connected";
      connecting = false;
      recoveryNeeded = false;
      if (wasRecovering && !pending && ui.feedback.dataset.tone !== "error" && ui.feedback.dataset.tone !== "success") feedback(`已连接居民 ${identity.actorId}。世界观察已同步，可以自由探索。`, "success");
      render();
    } catch (error) {
      if (error instanceof SessionChanged || error instanceof Unauthorized || !current(ctx)) return;
      connecting = false;
      markOffline(error instanceof ReadFailure ? error.message : "连接中断、请求超时或响应无法读取。");
    }
  }

  async function refresh() {
    if (!token || commandBusy) return;
    if (syncPromise) return syncPromise;
    clearTimeout(pollTimer);
    const ctx = context();
    const running = synchronize(ctx);
    syncPromise = running;
    try { await running; }
    finally {
      if (syncPromise === running) syncPromise = null;
      if (current(ctx) && token) pollTimer = setTimeout(refresh, POLL_MS);
    }
  }

  async function refreshAfterCommand(ctx) {
    if (!current(ctx)) return;
    if (syncPromise) await syncPromise;
    if (current(ctx)) await refresh();
  }

  async function connect(nextToken) {
    if (!nextToken) {
      feedback("请粘贴本机 a1 token 后连接。", "warning");
      ui["token-input"].focus();
      return;
    }
    resetSession(nextToken);
    storageSet(TOKEN_KEY, nextToken);
    connecting = true;
    connection = "connecting";
    feedback("正在验证居民身份并读取已提交的世界状态。", "neutral");
    render();
    await refresh();
  }

  function canAct() {
    return Boolean(token && identity && observation && observationHealthy && eventsHealthy && !pending && !commandBusy && !connecting && !storageError);
  }

  async function postPending(ctx) {
    const original = pending;
    try {
      const response = await request(`${API}/commands`, { method: "POST", headers: { "Content-Type": "application/json" }, body: original.body }, ctx);
      if (settledReceipt(response, original)) acceptReceipt(response, original);
      else {
        feedback(`结果尚未确定：${explain(response.data)} 原命令已保留，请查询结果或原样重试。`, "warning");
        if (response.status >= 500) markOffline("服务暂时无法确认命令结果。");
      }
    } catch (error) {
      if (error instanceof SessionChanged || error instanceof Unauthorized || !current(ctx)) return;
      markOffline("动作响应未收到，执行结果未知。");
    } finally {
      if (current(ctx)) {
        commandBusy = false;
        render();
        await refreshAfterCommand(ctx);
      }
    }
  }

  async function submitAction(action, proposal = null) {
    if (!canAct()) return;
    const commandId = `web_${crypto.randomUUID()}`;
    const body = JSON.stringify({ schemaVersion: 1, rulesVersion: observation.rulesVersion, commandId, expectedStateVersion: observation.stateVersion, action });
    pending = { worldId: WORLD, actorId: identity.actorId, sessionId: identity.sessionId, commandId, body, ...(proposal ? { proposal: structuredClone(proposal) } : {}) };
    pendingByActor[identity.actorId] = pending;
    // Save the exact original body BEFORE sending; retries never regenerate IDs or versions.
    if (!persistPending()) {
      feedback("无法保存恢复记录，命令尚未发送。已暂停新动作，请检查此标签页的 sessionStorage。", "error");
      render();
      return;
    }
    commandBusy = true;
    clearTimeout(pollTimer);
    feedback("命令已保存，正在等待世界确认。", "neutral");
    render();
    await postPending(context());
  }

  async function resolvePending(retry) {
    if (!token || !identity || !pending || commandBusy || connecting) return;
    if (pending.actorId !== identity.actorId) return;
    if (retry && !persistPending()) {
      feedback("恢复记录无法写入，原样重试已暂停。", "error");
      render();
      return;
    }
    const ctx = context();
    commandBusy = true;
    clearTimeout(pollTimer);
    feedback(retry ? "正在使用原 ID、原版本与原载荷重试。" : "正在查询这条原命令的回执。", "neutral");
    render();
    if (retry) return postPending(ctx);
    try { await lookupPending(ctx); }
    catch (error) {
      if (error instanceof SessionChanged || error instanceof Unauthorized || !current(ctx)) return;
      markOffline(error instanceof ReadFailure ? error.message : "命令查询暂时失败。");
    } finally {
      if (current(ctx)) {
        commandBusy = false;
        render();
        await refreshAfterCommand(ctx);
      }
    }
  }

  function render() {
    renderEntry(observation, observationHealthy && connection === "connected");
    const labels = { disconnected: "未连接", connecting: "正在连接", connected: "已连接", offline: "连接中断", unauthorized: "会话已失效" };
    ui["connection-status"].textContent = labels[connection];
    ui["connection-status"].dataset.status = connection;
    ui["connect-button"].disabled = connecting;
    ui["connect-button"].textContent = token ? "重新连接 ↗" : "连接世界 ↗";
    ui["token-input"].required = !token;
    ui["token-input"].placeholder = token ? "已保存 · 可粘贴其他 token" : "粘贴本机 token";
    ui["disconnect-button"].hidden = !token;
    const fresh = Boolean(observation && observationHealthy && eventsHealthy);
    ui["snapshot-status"].textContent = !observation ? "等待观察" : fresh ? "已确认观察" : "上次观察 · 待同步";
    ui["snapshot-status"].dataset.fresh = String(fresh);
    ui["actor-position"].textContent = observation ? coord(observation.self.position) : "—";
    ui["inventory-wood"].textContent = observation ? observation.self.inventory.wood : "—";
    ui["depot-wood"].textContent = observation ? isWilderness() ? resourceNodes().reduce((sum,n)=>sum+n.remainingWood,0) : observation.depot.wood : "—";
    ui["resource-source-label"].textContent = isWilderness() ? "野生木材" : "公共储备";
    ui["depot-position"].textContent = observation ? isWilderness() ? "到树旁采集，才成为库存" : `位于 ${coord(observation.depot.position)}` : "位置待确认";
    ui["state-version"].textContent = observation ? observation.stateVersion : "—";
    ui["resident-title"].textContent = identity ? `居民 ${identity.actorId}` : "等待入驻";
    ui["resident-avatar"].textContent = identity?.actorId || "?";
    ui["audit-status"].textContent = observation?.resourceAudit?.conserved === true ? "材料守恒" : observation ? "核算待确认" : "等待观察";
    ui["rules-version"].textContent = observation ? `规则 ${observation.rulesVersion}${isWilderness() ? " · 原始开局与采集" : isConsent() ? " · 画布协商修改" : isMosaic() ? " · 花园共同画布" : isPostcards() ? " · 共同手记" : isActivities() ? " · 地点与旅程" : isPassage() ? " · 两地通行" : ""}` : "规则待确认";
    ui["page-title"].textContent = isWilderness() ? "空手入原野，亲手建起生活。" : isConsent() ? "一起画，也一起决定。" : isMosaic() ? "留一点颜色，等下一个人。" : isPostcards() ? "你来过，也留下一点什么。" : isActivities() ? "选一处风景，留下你的足迹。" : isPassage() ? "搭一座桥，去另一片土地。" : "走一走，也建一点什么。";
    ui["scenario-copy"].textContent = isWilderness() ? "居民散落在河流两岸，最初没有现成库存或建筑。从身旁的树木采集材料，搭起第一座木台，或造桥走向彼此。" : isConsent() ? "添上自己的颜色，也尊重别人留下的笔触。想修改对方的格子，先写一份提议，等对方决定。" : isMosaic() ? "到花园，一起画一幅小画。读懂先来者留下的形状，添上你的颜色，让共同的作品慢慢生长。" : isPostcards() ? "走到花园、河岸或观景台，读读先到的人留下的话。记录到访后，也能把一句话留给后来者。" : isActivities() ? "花园、河岸步道与彼岸观景台。沿途走走，到现场记录一次到访；跨河的桥由居民共同建设。" : isPassage() ? "河道两格宽，逐段铺桥后就能往返两岸。桥向所有居民开放，探索不消耗木材。" : "两名居民，一片共享的陆地。探索不需要劳动；创造从有限的材料开始。";
    $("map-description").textContent = isWilderness() ? "点选树木后在身旁采集，或选择空地搭建。坐标从左上角 (0, 0) 开始。" : "点击一格选择建造位置。坐标从左上角 (0, 0) 开始。";
    ui["map-title"].textContent = isWilderness() ? "散落的原野" : isPassage() ? "两地之间" : "共同的土地";
    $("resident-report-link").href = isConsent() ? "resident.html?sample=consent-review" : isMosaic() ? "resident.html?sample=mosaic" : isPostcards() ? "resident.html?sample=postcards" : isActivities() ? "resident.html?sample=activities" : "resident.html";
    ui["water-legend"].hidden = ui["bridge-legend"].hidden = !isPassage();
    ui["claim-section"].hidden = isWilderness();
    ui["depot-legend"].hidden = ui["goal-legend"].hidden = !observation || isWilderness();
    ui["tree-legend"].hidden = !isWilderness();
    ui["wall-label"].textContent = isWilderness() ? "岩壁" : "墙";
    renderGather();
    renderRecipes();
    renderActivities();
    renderPostcards();
    renderMosaic();
    renderConsent();
    const enabled = canAct();
    for (const direction of ["up", "down", "left", "right"]) ui[`move-${direction}`].disabled = !enabled;
    ui["claim-button"].disabled = !enabled;
    ui["build-button"].disabled = !enabled || !selected || !selectedRecipe();
    ui["recipe-select"].disabled = !enabled || !availableRecipes().length;
    ui["pending-panel"].hidden = !pending;
    ui["pending-status"].textContent = pending ? commandBusy ? "动作处理中 · 请等待确认" : "有一个未决动作 · 新动作已暂停" : "没有未决动作";
    ui["pending-detail"].textContent = pending ? `${pending.actorId} / ${pending.commandId} · 原请求已保留` : "";
    ui["query-command-button"].disabled = ui["retry-command-button"].disabled = !pending || !identity || !token || commandBusy || connecting;
    ui["event-cursor"].textContent = eventCursor;
    if (storageError) feedback("此标签页的恢复存储不可用，已暂停新动作。未决请求仍保留在内存中，请勿关闭标签页。", "error");
    renderSelection();
    renderEvents();
    renderWorldDescription();
    drawWorld();
  }

  function renderGather() {
    ui["gather-panel"].hidden = !isWilderness();
    const nodes = resourceNodes(), selector = ui["gather-node"];
    const options = [{value:"",text:"选择一处树木"}, ...nodes.map(n => ({value:n.nodeId,text:`树木 ${coord(n.position)} · ${n.remainingWood ? `余 ${n.remainingWood} 木材` : "已采空"}`}))];
    if (JSON.stringify(options) !== selector.dataset.options) {
      selector.replaceChildren(...options.map(o => new Option(o.text,o.value)));selector.dataset.options=JSON.stringify(options);
    }
    const tree = selectedTree();selector.value=tree?.nodeId || "";selector.disabled=!canAct();
    const distance=tree ? Math.abs(tree.position[0]-observation.self.position[0])+Math.abs(tree.position[1]-observation.self.position[1]) : null;
    ui["gather-button"].disabled=!canAct() || !tree || tree.remainingWood===0 || distance!==1;
    ui["gather-hint"].textContent=!tree ? "选一棵树，走到上下左右相邻一格再砍取。" : tree.remainingWood===0 ? "这里已采空，树桩处现在可以通行或搭建。" : distance===1 ? `这棵树还可采 ${tree.remainingWood} 木材；每次确认后记入你的库存。` : `与你相距 ${distance} 格，请先走到树旁。`;
  }

  function renderRecipes() {
    const select = ui["recipe-select"];
    const recipes = availableRecipes();
    const options = recipes.length ? recipes.map((r) => ({ value: r.id, text: entityName(r.definitionId) }))
      : [{ value: "", text: observation ? "暂无可用配方" : "连接后读取配方" }];
    // Leave the native select intact during polling so keyboard focus stays usable.
    if (select.options.length !== options.length || options.some((option, index) => select.options[index].value !== option.value || select.options[index].text !== option.text)) {
      const previous = select.value;
      select.replaceChildren(...options.map((option) => new Option(option.text, option.value)));
      if (options.some((option) => option.value === previous)) select.value = previous;
    }
    const recipe = selectedRecipe();
    ui["recipe-cost"].textContent = recipe ? `${recipe.woodCost} 木材 / ${recipe.definitionId === "bridge" ? "段" : "个"}` : "成本待确认";
    ui["build-copy"].textContent = !recipe ? "可用配方与材料成本由世界服务提供。"
      : recipe.definitionId === "bridge" ? "在身旁一格水面铺桥，也可站在桥上接着铺。建成后所有居民都能免费通行。"
        : "在当前或相邻的空地建造平台。平台只能建在陆地上。";
  }

  function renderActivities() {
    ui["activities-panel"].hidden = !isActivities();
    const catalog = activities();
    const select = ui["activity-select"];
    if (select.options.length !== catalog.length || catalog.some((a, i) => select.options[i].value !== a.id || select.options[i].text !== a.label)) {
      const previous = select.value;
      select.replaceChildren(...catalog.map((a) => new Option(a.label, a.id)));
      if (catalog.some((a) => a.id === previous)) select.value = previous;
    }
    const signature = JSON.stringify(catalog);
    if (ui["activity-catalog"].dataset.catalog !== signature) {
      ui["activity-catalog"].dataset.catalog = signature;
      ui["activity-catalog"].replaceChildren(...catalog.map((a, i) => {
        const item = document.createElement("article");
        const title = document.createElement("h3"), description = document.createElement("p");
        title.textContent = `${i + 1}. ${a.label} ${coord(a.position)}`;
        description.textContent = a.description;
        item.append(title, description); return item;
      }));
    }
    const choice = selectedActivity();
    const at = choice && sameCell(choice.position, observation?.self.position);
    select.disabled = !catalog.length;
    ui["visit-button"].disabled = !canAct() || !at;
    ui["activity-hint"].textContent = !choice ? "连接活动世界后读取地点。" : at
      ? `你已到达${choice.label}。确认后留下到访记录；不发放资源或奖励。`
      : `请先走到${choice.label} ${coord(choice.position)}，然后记录到访。选择地点不会自动移动。`;
    const visits = isActivities() ? observation.self.visits : [];
    ui["visit-history"].textContent = visits.length ? `最近确认的到访：${visits.slice(-3).reverse().map((v) => `${activityName(v.activityId)} · v${v.stateVersion}`).join("；")}。`
      : "尚无已确认到访。到达坐标后仍需确认记录。";
  }

  function postcardDraftKey(actor, activity) { return `foundation.v1.postcard-draft.${actor}.${activity}`; }

  function unusedVisit(activity) {
    if (!isPostcards() || !activity) return null;
    const used = new Set(observation.self.postcards.map((p) => p.visitCommandId));
    return [...observation.self.visits].reverse().find((v) => v.activityId === activity.id && !used.has(v.commandId)) || null;
  }

  function renderPostcards() {
    ui["postcards-panel"].hidden = !isPostcards();
    const activity = selectedActivity();
    if (!isPostcards() || !activity) {
      draftKey = null;
      ui["postcard-text"].value = "";
      return;
    }
    const nextKey = postcardDraftKey(identity.actorId, activity.id);
    if (nextKey !== draftKey) {
      draftKey = nextKey;
      try { ui["postcard-text"].value = sessionStorage.getItem(draftKey) || ""; }
      catch { storageError = true; ui["postcard-text"].value = ""; }
      const original = pending && JSON.parse(pending.body).action;
      if (original?.type === "postcard" && original.activityId === activity.id) ui["postcard-text"].value = original.text;
    }
    ui["postcard-location"].textContent = activity.label;
    ui["postcard-feed-label"].textContent = `${activity.label}的手记 · 世界最近 50 篇中`;
    const cards = observation.postcards.filter((p) => p.activityId === activity.id).slice().reverse();
    const signature = JSON.stringify([identity.actorId, cards]);
    if (ui["postcard-list"].dataset.content !== signature) {
      ui["postcard-list"].dataset.content = signature;
      ui["postcard-list"].replaceChildren();
      if (!cards.length) {
        const empty = document.createElement("p");
        empty.className = "postcard-empty";
        empty.textContent = "这里还没有手记。也许第一句话，就从你开始。";
        ui["postcard-list"].append(empty);
      }
      for (const card of cards) {
        const article = document.createElement("article"), meta = document.createElement("p"), text = document.createElement("p");
        article.className = "postcard";
        article.dataset.commandId = card.commandId;
        meta.className = "postcard-meta";
        meta.textContent = `${card.authorActorId === identity.actorId ? "你 · " : ""}居民 ${card.authorActorId} · v${card.stateVersion}`;
        text.className = "postcard-message";
        text.textContent = card.text;
        article.append(meta, text);
        ui["postcard-list"].append(article);
      }
    }
    const at = sameCell(activity.position, observation.self.position), visit = unusedVisit(activity);
    const text = ui["postcard-text"].value, count = Array.from(text).length;
    ui["postcard-count"].textContent = `${count} / 160 字`;
    ui["postcard-count"].dataset.invalid = String(count > 160 || Boolean(text && !validPostcardText(text)));
    ui["postcard-text"].disabled = Boolean(pending || commandBusy);
    ui["postcard-button"].disabled = !canAct() || !at || !visit || !validPostcardText(text);
    ui["postcard-hint"].textContent = pending ? "正在确认原动作，草稿已保留。"
      : !at ? `请先走到${activity.label} ${coord(activity.position)}，记录到访后再分享。`
        : !visit ? "先在上方记录一次到访；每次到访可以分享一篇手记。"
          : !validPostcardText(text) ? "写下 1—160 字的一段话，不含换行或控制字符。"
            : "你已到访这里，可以分享。分享不消耗木材，也不发放奖励。";
  }

  function mosaicDraftKey(actor) { return `foundation.v1.mosaic-draft.${actor}`; }
  function unusedMosaicVisit() {
    if (!isMosaic()) return null;
    const used = new Set(observation.self.mosaicEdits.map((e) => e.visitCommandId));
    return [...observation.self.visits].reverse().find((v) => v.activityId === "garden" && !used.has(v.commandId)) || null;
  }
  function paintDraft(x, y) {
    if (!isMosaic() || pending || commandBusy || storageError) return;
    const board = observation.mosaic;
    if (mosaicDraft && mosaicDraft.baseRevision !== board.revision) return;
    const draft = mosaicDraft || { baseRevision: board.revision, baseCells: structuredClone(board.cells), patch: [] };
    const patch = draft.patch.filter((c) => c.x !== x || c.y !== y);
    if (draft.baseCells[y * 5 + x].color !== selectedColor) patch.push({ x, y, color: selectedColor });
    if (patch.length > 8) { feedback("每次最多改 8 格；先取消一格草稿，或发表后再次到访。", "warning"); return; }
    mosaicDraft = patch.length ? { ...draft, patch: mosaic.canonical(patch) } : null;
    storageSet(mosaicKey, mosaicDraft ? JSON.stringify(mosaicDraft) : null);
    renderMosaic();
    renderConsent();
  }
  function renderMosaic() {
    ui["mosaic-panel"].hidden = !isMosaic();
    if (!isMosaic()) { mosaicKey = null; mosaicDraft = null; return; }
    const board = observation.mosaic;
    const key = mosaicDraftKey(identity.actorId);
    if (key !== mosaicKey) {
      mosaicKey = key; mosaicDraft = null;
      try {
        const saved = JSON.parse(sessionStorage.getItem(key) || "null");
        if (saved) {
          if (!isInt(saved.baseRevision) || !mosaic.validPatch(saved.patch) || !mosaic.validBoard({ ...board, revision: saved.baseRevision, cells: saved.baseCells })) throw new Error("Invalid draft");
          mosaicDraft = saved;
        }
      } catch { storageError = true; }
    }
    const stale = Boolean(mosaicDraft && mosaicDraft.baseRevision !== board.revision);
    const locked = Boolean(pending || commandBusy || storageError || stale);
    if (!ui["mosaic-palette"].children.length) {
      for (const color of mosaic.palette) {
        const button = document.createElement("button"), swatch = document.createElement("i");
        button.type = "button"; button.className = "mosaic-swatch"; button.dataset.color = color.id;
        swatch.style.backgroundColor = color.hex; swatch.setAttribute("aria-hidden", "true");
        button.append(swatch, document.createTextNode(color.label));
        button.addEventListener("click", () => { selectedColor = color.id; renderMosaic(); });
        ui["mosaic-palette"].append(button);
      }
    }
    for (const button of ui["mosaic-palette"].children) {
      button.setAttribute("aria-pressed", String(button.dataset.color === selectedColor)); button.disabled = locked;
    }
    mosaic.renderBoard(ui["mosaic-public"], board.cells);
    mosaic.renderBoard(ui["mosaic-editor"], mosaicDraft?.baseCells || board.cells, { patch: mosaicDraft?.patch || [], interactive: true, disabled: locked, onCell: paintDraft });
    ui["mosaic-version"].textContent = `花园 · 画布第 ${board.revision} 版`;
    const authors = [...new Set(board.cells.filter((c) => c.authorActorId).map((c) => c.authorActorId))];
    ui["mosaic-authors"].textContent = authors.length ? `当前格子的最后作者：${authors.map((a) => `居民 ${a}`).join("、")}` : "还没有人动笔。第一种颜色，由你来选。";
    ui["mosaic-draft-count"].textContent = `${mosaicDraft?.patch.length || 0} / 8 格`;
    ui["mosaic-draft-note"].textContent = mosaicDraft ? `基于画布第 ${mosaicDraft.baseRevision} 版 · 虚线格尚未发表${stale ? " · 共同画布已经变化" : ""}` : "选择一种颜色，再点格子。空白可擦除，选择原色可取消该格草稿。";
    const mode = isConsent() ? consent.draftMode(mosaicDraft, identity.actorId) : { kind: "direct" };
    const nextTextKey = `foundation.v1.proposal-text.${identity.actorId}`;
    if (proposalDraftKey !== nextTextKey) { proposalDraftKey = nextTextKey; try { ui["proposal-text"].value = sessionStorage.getItem(nextTextKey) || ""; } catch { storageError = true; } }
    ui["proposal-compose"].hidden = mode.kind !== "proposal";
    ui["proposal-text"].disabled = Boolean(pending || commandBusy);
    ui["proposal-count"].textContent = `${Array.from(ui["proposal-text"].value).length} / 160 字`;
    ui["mosaic-public-note"].textContent = isConsent() ? "本人和无人署名的格子可以直接画；修改他人留下的格子，要先由对方同意。将鼠标停在格子上查看最后作者。" : "向这个世界的居民公开，之后也能被别人修改。将鼠标停在格子上可查看最后作者。";
    ui["mosaic-publish"].textContent = mode.kind === "proposal" ? "提交修改提议" : "发表这次绘制";
    const at = sameCell(observation.self.position, [1, 6]), visit = mode.kind === "proposal" ? unusedProposalVisit() : unusedMosaicVisit();
    ui["mosaic-publish"].disabled = !canAct() || !at || !visit || !mosaicDraft || stale || mode.kind === "mixed" || mode.kind === "proposal" && !consent.text(ui["proposal-text"].value);
    ui["mosaic-clear"].disabled = Boolean(pending || commandBusy || !mosaicDraft);
    ui["mosaic-hint"].dataset.conflict = String(stale);
    ui["mosaic-hint"].textContent = pending ? "正在确认原动作；草图与命令都已保留。"
      : mode.kind === "mixed" ? "草图混合了不同来源。自己的格子与他人的格子请分开修改；一次提议只针对同一位居民的格子。"
      : stale ? "共同画布已有新版本。旧草图没有发表；先清除草稿，按当前画布重新创作。"
        : !at ? "你可以先画草图。走到花园 (1, 6)，在下方记录到访后发表。"
          : !visit ? "先在下方记录一次花园到访；每次到访可以发表一次绘制。"
            : !mosaicDraft ? "选色并点击格子，最多改 8 格。虚线只表示草图，不改变共同画布。"
              : mode.kind === "proposal" ? `这份草图会发给居民 ${mode.target}。写明修改理由后提交，尚不会改变画布。` : "已到访花园，可以发表。绘制不消耗木材，也不发放奖励。";
  }

  function unusedProposalVisit() {
    if (!isConsent()) return null;
    const used = new Set(observation.self.mosaicProposals.map((p) => p.visitCommandId));
    return [...observation.self.visits].reverse().find((v) => v.activityId === "garden" && !used.has(v.commandId)) || null;
  }
  function reviewDraftKey(actor, author, command) { return `foundation.v1.review-text.${actor}.${author}.${command}`; }
  function latestGardenVisit() { return observation?.self.visits?.slice().reverse().find((v) => v.activityId === "garden") || null; }
  function renderConsent() {
    ui["consent-panel"].hidden = !isConsent();
    if (!isConsent()) return;
    const scopeLabels = { received: "发给我的", sent: "我提出的", all: "全部提议" };
    const statusLabels = { pending: "等待决定", reviewed: "已处理", all: "全部状态" };
    const page = inbox.page, ready = inboxReady(), limited = inbox.mode === "legacy";
    const proposals = page?.items || [], at = sameCell(observation.self.position, [1, 6]);
    ui["inbox-scope"].value = inbox.query.scope;
    ui["inbox-status"].value = inbox.query.status;
    ui["inbox-counts"].textContent = page
      ? `${scopeLabels[page.query.scope]} · ${limited ? "仅最近 50 条公开提议内计数，非完整待办" : "完整库计数"}：等待决定 ${page.counts.pending} · 已处理 ${page.counts.reviewed} · 合计 ${page.counts.all}${ready ? "" : "（上次读取，尚未更新）"}`
      : "计数尚未确认，待办数量未知。";
    const range = page ? `${scopeLabels[page.query.scope]} / ${statusLabels[page.query.status]} · 本页 ${proposals.length} 条${page.query.before === null ? " · 最新页" : ` · 提议版本 < ${page.query.before}`}` : "尚无已确认列表";
    ui["inbox-message"].textContent = inbox.error || (inbox.loading
      ? `正在读取收件箱；${page ? `下方保留上次内容（${range}）` : "待办数量尚未确认"}。`
      : inbox.deferredPage ? `列表已有变化，暂留正在编辑的提议与选区；离开理由框后更新列表，草稿会保留。${range}（上次内容，审阅已暂停）。`
        : !ready ? `收件箱未更新；${range}。等待世界观察同步，审阅已暂停。`
        : `${limited ? "当前服务仅提供最近 50 条公开提议，可能遗漏更早待办；以下筛选和分页也仅覆盖这 50 条。" : "按提议发表时间从新到旧，每页最多 20 条。"}${range}。`);
    ui["inbox-message"].dataset.tone = inbox.error || !ready && !inbox.loading ? "warning" : "neutral";
    ui["inbox-location"].textContent = `当前位置 ${coord(observation.self.position)}${observationHealthy ? "" : "（上次观察）"} · 花园 (1, 6)。${!at ? "请用地图下方方向按钮走到花园，再记录本人到访。" : !latestGardenVisit() ? "你已在花园；先记录本人到访，再决定提议。" : !unusedMosaicVisit() ? "你已记录到访；本次绘制名额已用，同意前需再记录到访，仍可拒绝。" : "你已记录本人到访，可填写理由后同意或拒绝。"}`;
    ui["inbox-visit"].disabled = !canAct() || !at;
    ui["inbox-newest"].disabled = inbox.loading && inbox.query.before === null;
    ui["inbox-newer"].disabled = !inbox.history.length;
    ui["inbox-older"].disabled = !ready || inbox.loading || page.nextBefore === null;

    const make = (tag, cls, text) => { const el = document.createElement(tag); el.className = cls; if (text !== undefined) el.textContent = text; return el; };
    const root = ui["consent-list"];
    const existing = new Map([...root.querySelectorAll("article")].map((el) => [`${el.dataset.proposer}/${el.dataset.command}`, el]));
    const focused = root.contains(document.activeElement) ? document.activeElement : null;
    const selection = focused?.tagName === "TEXTAREA" ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
    const desired = [];
    for (const proposal of proposals) {
      const id = `${proposal.authorActorId}/${proposal.commandId}`;
      let article = existing.get(id);
      if (!article) {
        article = make("article", "consent-entry");
        article.dataset.proposer = proposal.authorActorId; article.dataset.command = proposal.commandId;
        const preview = make("div", "mosaic-grid"), body = make("div", "consent-body");
        const title = make("h3", ""), meta = make("p", "mosaic-meta"), original = make("p", "consent-copy");
        const state = make("p", "consent-state"), reviewedText = make("p", "consent-copy");
        body.append(title, meta, original, state, reviewedText);
        article._inboxView = { preview, title, meta, original, state, reviewedText };
        if (proposal.targetActorId === identity.actorId) {
          const actor = identity.actorId, key = reviewDraftKey(actor, proposal.authorActorId, proposal.commandId);
          const form = make("div", "consent-review"), label = make("label", "consent-review-label", "你的决定与理由");
          const input = make("textarea", "consent-review-text"); input.rows = 2;
          input.id = `review-${proposal.authorActorId}-${proposal.commandId}`; label.htmlFor = input.id;
          input.placeholder = "说明为什么同意或保留原图，最多 160 字。";
          try { input.value = sessionStorage.getItem(key) || ""; } catch { storageError = true; }
          input.addEventListener("input", () => { if (identity?.actorId === actor) storageSet(key, input.value || null); renderConsent(); });
          const hint = make("p", "consent-review-hint"); hint.setAttribute("role", "status");
          form.append(label, input, hint);
          for (const decision of ["accept", "reject"]) {
            const button = make("button", `button ${decision === "accept" ? "primary" : "quiet"}`, decision === "accept" ? "同意并改图" : "拒绝，保留原图");
            button.type = "button"; button.dataset.review = decision;
            button.addEventListener("click", () => {
              // The complete validated inbox item is authoritative even outside observation's recent 50.
              const currentProposal = inboxReady() && inbox.page.items.find((p) => p.authorActorId === proposal.authorActorId && p.commandId === proposal.commandId);
              const visit = decision === "accept" ? unusedMosaicVisit() : latestGardenVisit();
              if (identity?.actorId !== actor || !canAct() || !visit || !currentProposal || currentProposal.review || currentProposal.targetActorId !== actor || !sameCell(observation.self.position, [1, 6]) || !consent.text(input.value)) return;
              if (decision === "accept" && observation.mosaic.revision !== currentProposal.baseRevision) return;
              submitAction({ type: "mosaic_review", activityId: "garden", visitCommandId: visit.commandId, proposalActorId: currentProposal.authorActorId, proposalCommandId: currentProposal.commandId, decision, text: input.value }, currentProposal);
            });
            form.append(button);
          }
          body.append(form); Object.assign(article._inboxView, { form, input, hint });
        }
        article.append(preview, body);
      }
      const view = article._inboxView, review = proposal.review;
      mosaic.renderBoard(view.preview, mosaic.emptyCells(), { patch: proposal.patch });
      view.title.textContent = `居民 ${proposal.authorActorId} → 居民 ${proposal.targetActorId}`;
      view.meta.textContent = `建议改 ${proposal.patch.length} 格 · 基于画布第 ${proposal.baseRevision} 版 · 提议版本 ${proposal.stateVersion} · 虚线只是提议`;
      view.original.textContent = proposal.text;
      view.state.textContent = review ? review.decision === "accept" ? `已同意并改图 · 由居民 ${review.authorActorId} 提交 · 画布第 ${review.mosaicEdit.revision} 版` : `已拒绝 · 居民 ${review.authorActorId} 保留了原图` : "等待对方决定 · 共同画布尚未因此改变";
      view.reviewedText.hidden = !review; view.reviewedText.textContent = review?.text || "";
      if (view.input) {
        const stale = proposal.baseRevision !== observation.mosaic.revision;
        const available = ready && canAct() && !review && at && latestGardenVisit() && consent.text(view.input.value);
        view.form.hidden = Boolean(review);
        view.input.disabled = Boolean(pending || commandBusy);
        view.form.querySelector('[data-review="accept"]').disabled = !available || stale || !unusedMosaicVisit();
        view.form.querySelector('[data-review="reject"]').disabled = !available;
        view.hint.textContent = pending ? "正在确认原决定，请等待。" : !ready ? "收件箱尚未更新，审阅已暂停；已输入的理由保留。" : !canAct() ? "世界观察尚未就绪，审阅已暂停。" : !at ? "走到花园并使用上方按钮记录到访后作出决定。" : !latestGardenVisit() ? "先使用上方按钮记录一次花园到访。" : stale ? "画布已经变化：这份提议只能拒绝，不能覆盖新图。" : !unusedMosaicVisit() ? "本次绘制名额已用；同意前需记录新的到访，仍可拒绝。" : `理由 ${Array.from(view.input.value).length} / 160 字。只有同意才会改变图案。`;
      }
      desired.push(article);
    }
    if (!proposals.length) {
      const empty = root.querySelector(".consent-empty") || make("p", "consent-empty");
      empty.textContent = !page ? "等待收件箱读取，待办数量未知。" : !ready ? "上次列表为空，当前收件箱尚未更新。" : page.query.before !== null ? "这个游标范围内暂无符合筛选的提议，可返回较新页或回到最新。" : `当前范围暂无${statusLabels[page.query.status]}的提议。${limited ? "这不代表更早记录中没有待办。" : ""}`;
      desired.push(empty);
    }
    // Insert new rows around surviving nodes; never detach all rows during polling or typing.
    const keep = new Set(desired);
    for (const child of [...root.children]) if (!keep.has(child)) child.remove();
    let cursor = root.firstElementChild;
    for (const node of desired) {
      if (node === cursor) cursor = cursor.nextElementSibling;
      else root.insertBefore(node, cursor);
    }
    if (focused?.isConnected && !focused.disabled && !focused.closest("[hidden]")) {
      if (document.activeElement !== focused) focused.focus({ preventScroll: true });
      if (selection && (focused.selectionStart !== selection[0] || focused.selectionEnd !== selection[1] || focused.selectionDirection !== selection[2])) focused.setSelectionRange(...selection);
    }
  }

  function renderSelection() {
    ui["selected-cell"].textContent = selected ? coord(selected) : "尚未选择";
    if (!selected) {
      ui["selection-detail"].textContent = "选择配方和格点后建造；是否可建造由世界服务确认。";
      return;
    }
    const labels = [];
    if (observation) {
      const blocked = observation.world.blocked.some((p) => sameCell(p, selected));
      const tree=selectedTree();
      labels.push(tree?.remainingWood > 0 ? `树木，尚余 ${tree.remainingWood} 木材` : isWater(selected) ? blocked ? "水面，尚不可通行" : "水面，服务已确认可通行" : blocked ? isWilderness() ? "岩壁，无法通行或建造" : "墙体，无法通行或建造" : "可通行陆地");
      if (!isWilderness() && sameCell(observation.depot.position, selected)) labels.push("公共储备点");
      if (!isWilderness() && sameCell(observation.world.goal, selected)) labels.push("探索目标");
      for (const activity of activities()) if (sameCell(activity.position, selected)) labels.push(activity.label);
      const entity = observation.entities.find((e) => sameCell(e.position, selected));
      if (entity) labels.push(`已有${entityName(entity.definitionId)}`);
      const distance = Math.abs(selected[0] - observation.self.position[0]) + Math.abs(selected[1] - observation.self.position[1]);
      labels.push(`与你相距 ${distance} 格${distance > 1 ? "，建造需在 1 格内" : ""}`);
    }
    ui["selection-detail"].textContent = `${labels.join(" · ") || "已选择格点"}。最终以服务确认结果为准。`;
  }

  function renderEvents() {
    const list = ui["event-list"];
    list.replaceChildren();
    if (!publicEvents.length) {
      const empty = document.createElement("li");
      empty.className = "empty-events";
      empty.textContent = identity ? "暂无已读取的公共事件。" : "世界的故事，会从连接后的第一条公共事件开始。";
      list.append(empty);
      return;
    }
    for (const event of [...publicEvents].reverse()) {
      const row = document.createElement("li");
      const number = document.createElement("span");
      number.className = "event-number";
      number.textContent = `#${String(event.seq).padStart(3, "0")}`;
      const text = document.createElement("span");
      text.className = "event-message";
      const who = event.actorId === identity?.actorId ? "你" : `居民 ${event.actorId || "—"}`;
      const definitionId = event.definitionId || observation?.entities.find((e) => sameCell(e.position, event.position))?.definitionId;
      text.textContent = event.type === "worldSeeded" ? isWilderness() ? "居民散落原野，木材仍在树上，尚无公共储备。" : "小世界诞生，公共储备已就绪。"
        : event.type === "moved" ? `${who} 移动到 ${event.position ? coord(event.position) : "新位置"}。`
          : event.type === "gathered" ? `${who} 在 ${event.position ? coord(event.position) : "树木旁"} 砍取了 ${event.quantity} 单位木材。`
          : event.type === "claimed" ? `${who} 领取了${event.quantity === null ? "" : ` ${event.quantity} 单位`}木材。`
            : event.type === "visited" ? `${who} 到访了${activityName(event.activityId)}。`
            : event.type === "postcard_shared" ? `${who} 在${activityName(event.activityId)}留下了一篇手记。`
            : event.type === "mosaic_proposed" ? `${who} 提出了一份画布修改建议，等待居民 ${event.targetActorId} 决定。`
            : event.type === "mosaic_reviewed" ? `${who} ${event.decision === "accept" ? "同意提议并修改了画布" : "拒绝提议，保留原图"}。`
            : event.type === "mosaic_painted" ? `${who} 为花园共同画布添上了一笔。`
            : `${who} 在${event.position ? ` ${coord(event.position)}` : "世界中"} 建造了${entityName(definitionId)}。`;
      const version = document.createElement("span");
      version.className = "event-version";
      version.textContent = `v${event.stateVersion}`;
      row.append(number, text, version);
      list.append(row);
    }
  }

  function renderWorldDescription() {
    if (!observation) {
      ui["world-summary"].textContent = "连接世界后显示已确认的地图与居民位置。";
      ui["world-canvas"].setAttribute("aria-label", "8 乘 8 世界地图，等待已确认观察");
      return;
    }
    const d = observation;
    const text = `8 × 8 ${isWilderness() ? "原野" : isPassage() ? "两地通行世界" : "陆地"}。${isWilderness() ? "岩壁" : "墙"}：${wallCells().map(coord).join("、") || "无"}。水面：${waterCells().map(coord).join("、") || "无"}。不可通行：${d.world.blocked.map(coord).join("、") || "无"}。${isWilderness() ? `野生树木：${resourceNodes().map(n=>`${coord(n.position)} 余 ${n.remainingWood} 木材`).join("；")}。无公共储备` : `储备：${coord(d.depot.position)}。目标：${coord(d.world.goal)}`}。居民：${d.residents.map((r) => `${r.actorId} ${coord(r.position)}`).join("；")}。设施：${d.entities.map((e) => `${entityName(e.definitionId)} ${coord(e.position)}`).join("、") || "无"}。`;
    const activityText = isActivities() ? `活动地点：${activities().map((a) => `${a.label} ${coord(a.position)}`).join("、")}。` : "";
    ui["world-summary"].textContent = text + activityText;
    ui["world-canvas"].setAttribute("aria-label", `世界版本 ${d.stateVersion}。${text}${activityText}${selected ? `选择格 ${coord(selected)}。` : ""}`);
  }

  function selectCell(cell) {
    if (!isCell(cell)) return;
    selected = cell;
    ui["cell-x"].value = cell[0];
    ui["cell-y"].value = cell[1];
    render();
  }

  function mapGeometry() {
    const size = ui["world-canvas"].getBoundingClientRect().width;
    const margin = size < 400 ? 23 : 29;
    return { size, margin, unit: (size - margin * 2) / 8 };
  }

  function drawWorld() {
    const canvas = ui["world-canvas"];
    const { size, margin, unit } = mapGeometry();
    if (!size) return;
    const ratio = window.devicePixelRatio || 1;
    const pixels = Math.round(size * ratio);
    if (canvas.width !== pixels || canvas.height !== pixels) canvas.width = canvas.height = pixels;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(pixels / size, 0, 0, pixels / size, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#eef1e5";
    ctx.fillRect(0, 0, size, size);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `${Math.max(9, unit * .19)}px system-ui,sans-serif`;
    for (let i = 0; i < 8; i++) {
      ctx.fillStyle = "#909e83";
      ctx.fillText(i, margin + unit * (i + .5), margin * .48);
      ctx.fillText(i, margin * .46, margin + unit * (i + .5));
    }
    for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
      const px = margin + x * unit, py = margin + y * unit;
      const water = isWater([x, y]);
      ctx.fillStyle = water ? ((x + y) % 2 ? "#abd0d7" : "#b7dae0") : observation ? ((x + y) % 2 ? "#dce6cc" : "#e2e9d4") : ((x + y) % 2 ? "#e2e6da" : "#e7eadf");
      ctx.fillRect(px + .65, py + .65, unit - 1.3, unit - 1.3);
      if (water) {
        ctx.strokeStyle = "#7db5c1";
        ctx.lineWidth = Math.max(1, unit * .025);
        for (const offset of [.3, .65]) {
          ctx.beginPath();
          ctx.moveTo(px + unit * .2, py + unit * offset);
          ctx.quadraticCurveTo(px + unit * .4, py + unit * (offset + .09), px + unit * .6, py + unit * offset);
          ctx.stroke();
        }
      } else if (observation && (x * 5 + y * 3) % 7 === 0) {
        ctx.strokeStyle = "#bfcea9";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px + unit * .74, py + unit * .8);
        ctx.lineTo(px + unit * .71, py + unit * .73);
        ctx.moveTo(px + unit * .76, py + unit * .8);
        ctx.lineTo(px + unit * .8, py + unit * .72);
        ctx.stroke();
      }
    }
    if (!observation) {
      ctx.fillStyle = "#eef1e5e8";
      ctx.fillRect(margin, size * .4, size - margin * 2, size * .2);
      ctx.fillStyle = "#71816a";
      ctx.font = "13px system-ui,sans-serif";
      ctx.fillText("连接后显示已确认的世界", size / 2, size / 2);
      return;
    }
    const center = (p) => [margin + (p[0] + .5) * unit, margin + (p[1] + .5) * unit];
    for (const wall of wallCells()) {
      const [x, y] = center(wall);
      if (isWilderness()) {
        ctx.fillStyle="#657263";ctx.beginPath();ctx.moveTo(x-unit*.43,y+unit*.39);ctx.lineTo(x-unit*.45,y-unit*.12);ctx.lineTo(x-unit*.24,y-unit*.43);ctx.lineTo(x+unit*.24,y-unit*.4);ctx.lineTo(x+unit*.44,y+unit*.06);ctx.lineTo(x+unit*.3,y+unit*.43);ctx.closePath();ctx.fill();
        ctx.fillStyle="#84907b";ctx.beginPath();ctx.moveTo(x-unit*.24,y-unit*.43);ctx.lineTo(x+unit*.24,y-unit*.4);ctx.lineTo(x+unit*.12,y-unit*.06);ctx.lineTo(x-unit*.16,y+unit*.05);ctx.closePath();ctx.fill();continue;
      }
      ctx.fillStyle = "#51624e";
      ctx.fillRect(x - unit * .43, y - unit * .39, unit * .86, unit * .84);
      ctx.fillStyle = "#718169";
      ctx.fillRect(x - unit * .43, y - unit * .43, unit * .86, unit * .7);
      ctx.strokeStyle = "#84927a";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x - unit * .4, y - unit * .08); ctx.lineTo(x + unit * .4, y - unit * .08);
      ctx.moveTo(x, y - unit * .4); ctx.lineTo(x, y - unit * .08);
      ctx.stroke();
    }
    for (const tree of resourceNodes()) {
      const [x,y]=center(tree.position);
      ctx.fillStyle="#8b6844";ctx.fillRect(x-unit*.07,y-unit*.02,unit*.14,unit*.33);
      if (tree.remainingWood > 0) {
        ctx.fillStyle="#3b7252";ctx.beginPath();ctx.arc(x,y-unit*.12,unit*.29,0,Math.PI*2);ctx.fill();
        ctx.fillStyle="#579064";ctx.beginPath();ctx.arc(x-unit*.09,y-unit*.2,unit*.16,0,Math.PI*2);ctx.fill();
        ctx.fillStyle="#fffdf3";ctx.font=`600 ${Math.max(10,unit*.24)}px system-ui,sans-serif`;ctx.fillText(String(tree.remainingWood),x,y-unit*.08);
      } else {ctx.fillStyle="#b68b58";ctx.beginPath();ctx.ellipse(x,y+unit*.13,unit*.16,unit*.08,0,0,Math.PI*2);ctx.fill();}
    }
    for (const entity of observation.entities) {
      const [x, y] = center(entity.position);
      if (entity.definitionId === "bridge") {
        ctx.fillStyle = "#b18653";
        ctx.fillRect(x - unit * .5, y - unit * .22, unit, unit * .44);
        ctx.strokeStyle = "#e9cf9d";
        ctx.lineWidth = Math.max(1, unit * .025);
        for (let i = 0; i < 6; i++) {
          const plank = x - unit * .45 + i * unit * .18;
          ctx.beginPath(); ctx.moveTo(plank, y - unit * .2); ctx.lineTo(plank, y + unit * .2); ctx.stroke();
        }
        ctx.fillStyle = "#715b3e";
        for (const dy of [-.3, .24]) ctx.fillRect(x - unit * .5, y + unit * dy, unit, unit * .06);
        for (const dx of [-.4, .34]) for (const dy of [-.34, .24]) ctx.fillRect(x + unit * dx, y + unit * dy, unit * .06, unit * .1);
        continue;
      }
      ctx.fillStyle = "#927754";
      ctx.fillRect(x - unit * .38, y - unit * .32, unit * .76, unit * .72);
      for (let i = 0; i < 4; i++) {
        ctx.fillStyle = i % 2 ? "#d7b787" : "#e0c599";
        ctx.fillRect(x - unit * .38, y - unit * .38 + i * unit * .18, unit * .76, unit * .15);
      }
      ctx.fillStyle = "#876d4b";
      for (const dx of [-.3, .3]) for (const dy of [-.3, .24]) ctx.fillRect(x + unit * dx, y + unit * dy, 2, 2);
    }
    if (!isWilderness()) {
      const [x, y] = center(observation.depot.position);
      ctx.fillStyle = "#a48350";
      ctx.fillRect(x - unit * .31, y - unit * .29, unit * .62, unit * .58);
      ctx.fillStyle = "#d0af72";
      ctx.fillRect(x - unit * .34, y - unit * .34, unit * .68, unit * .15);
      ctx.strokeStyle = "#ebcf95";
      ctx.lineWidth = Math.max(1, unit * .035);
      ctx.strokeRect(x - unit * .24, y - unit * .2, unit * .48, unit * .4);
      ctx.beginPath(); ctx.moveTo(x, y - unit * .2); ctx.lineTo(x, y + unit * .2); ctx.stroke();
    }
    if (!isActivities()) {
      const [x, y] = center(observation.world.goal);
      ctx.strokeStyle = "#9b754e";
      ctx.lineWidth = Math.max(2, unit * .04);
      ctx.beginPath(); ctx.moveTo(x - unit * .15, y + unit * .28); ctx.lineTo(x - unit * .15, y - unit * .32); ctx.stroke();
      ctx.fillStyle = "#bd714a";
      ctx.beginPath(); ctx.moveTo(x - unit * .15, y - unit * .33); ctx.lineTo(x + unit * .29, y - unit * .17); ctx.lineTo(x - unit * .15, y); ctx.fill();
      ctx.fillStyle = "#c0cba8";
      ctx.beginPath(); ctx.ellipse(x, y + unit * .32, unit * .27, unit * .06, 0, 0, Math.PI * 2); ctx.fill();
    }
    for (const [index, activity] of activities().entries()) {
      const [x, y] = center(activity.position);
      if (isWilderness()) {
        ctx.strokeStyle="#9d8059";ctx.lineWidth=Math.max(1,unit*.025);ctx.setLineDash([unit*.07,unit*.06]);ctx.strokeRect(x-unit*.42,y-unit*.42,unit*.84,unit*.84);ctx.setLineDash([]);
        ctx.fillStyle="#f7f3e6";ctx.beginPath();ctx.arc(x+unit*.3,y+unit*.3,unit*.13,0,Math.PI*2);ctx.fill();ctx.fillStyle="#755f41";ctx.font=`600 ${Math.max(9,unit*.19)}px system-ui,sans-serif`;ctx.fillText(String(index+1),x+unit*.3,y+unit*.3);continue;
      }
      ctx.fillStyle = selectedActivity()?.id === activity.id ? "#b16d45" : "#9d8059";
      ctx.beginPath(); ctx.moveTo(x, y - unit * .34); ctx.lineTo(x + unit * .31, y); ctx.lineTo(x, y + unit * .34); ctx.lineTo(x - unit * .31, y); ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#fffdf3"; ctx.font = `600 ${Math.max(10, unit * .24)}px system-ui,sans-serif`;
      ctx.fillText(String(index + 1), x, y);
    }
    for (const resident of observation.residents) {
      let [x, y] = center(resident.position);
      const othersHere = observation.residents.filter((r) => sameCell(r.position, resident.position));
      const self = resident.actorId === identity.actorId;
      const radius = unit * (othersHere.length > 1 ? .195 : .24);
      if (othersHere.length > 1) x += (othersHere.indexOf(resident) === 0 ? -.2 : .2) * unit;
      y -= unit * .04;
      ctx.fillStyle = "#516b4330";
      ctx.beginPath(); ctx.ellipse(x, y + radius + unit * .07, radius * .9, unit * .07, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = self ? "#2d7055" : "#497d99";
      ctx.strokeStyle = "#fffef5";
      ctx.lineWidth = Math.max(2, unit * .045);
      ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#fffdf3";
      ctx.font = `600 ${Math.max(9, radius * .94)}px system-ui,sans-serif`;
      ctx.fillText(resident.actorId.replace(/^a/, ""), x, y + .5);
      if (self) {
        ctx.fillStyle = "#2d7055";
        ctx.beginPath(); ctx.moveTo(x - unit * .06, y - radius - unit * .14); ctx.lineTo(x + unit * .06, y - radius - unit * .14); ctx.lineTo(x, y - radius - unit * .06); ctx.fill();
      }
    }
    if (selected) {
      const [x, y] = center(selected);
      ctx.strokeStyle = "#235e47";
      ctx.lineWidth = Math.max(2, unit * .04);
      ctx.setLineDash([unit * .1, unit * .055]);
      ctx.strokeRect(x - unit * .44, y - unit * .44, unit * .88, unit * .88);
      ctx.setLineDash([]);
    }
  }

  $("connection-form").addEventListener("submit", (event) => {
    event.preventDefault();
    connect(ui["token-input"].value.trim() || token);
  });
  ui["disconnect-button"].addEventListener("click", () => {
    const hasPending = Object.keys(pendingByActor).length > 0;
    resetSession("");
    storageSet(TOKEN_KEY, null);
    connection = "disconnected";
    connecting = false;
    feedback(`已断开此标签页。${hasPending ? "未决命令仍保留，同一居民重新连接后可查询。" : "重新粘贴 token 即可继续。"}`);
    render();
  });
  const directions = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  for (const [name, [dx, dy]] of Object.entries(directions)) ui[`move-${name}`].addEventListener("click", () => submitAction({ type: "move", dx, dy }));
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.repeat || event.isComposing) return;
    if (event.target instanceof Element && event.target.closest("input, textarea, select, #entry-panel, #mosaic-panel, #consent-panel, [contenteditable]:not([contenteditable='false'])")) return;
    const name = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" }[event.key];
    if (!name || !canAct()) return;
    event.preventDefault();
    const [dx, dy] = directions[name];
    submitAction({ type: "move", dx, dy });
  });
  ui["gather-node"].addEventListener("change", () => {
    const node=resourceNodes().find(n=>n.nodeId===ui["gather-node"].value);
    if(node)selectCell(node.position);
  });
  ui["gather-button"].addEventListener("click", () => {
    const node=selectedTree();if(node&&!ui["gather-button"].disabled)submitAction({type:"gather",nodeId:node.nodeId});
  });
  ui["claim-button"].addEventListener("click", () => {
    const quantity = ui["claim-quantity"].valueAsNumber;
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 12) {
      feedback("领取数量需要是 1 至 12 的整数。", "warning");
      ui["claim-quantity"].focus();
      return;
    }
    submitAction({ type: "claim", quantity });
  });
  ui["recipe-select"].addEventListener("change", render);
  ui["activity-select"].addEventListener("change", () => {
    const activity = selectedActivity();
    if (activity) selectCell(activity.position);
  });
  ui["visit-button"].addEventListener("click", () => {
    const activity = selectedActivity();
    if (activity && sameCell(activity.position, observation?.self.position)) submitAction({ type: "visit", activityId: activity.id });
  });
  ui["inbox-scope"].addEventListener("change", () => changeInbox("filter"));
  ui["consent-list"].addEventListener("focusout", () => queueMicrotask(() => {
    if (inbox.deferredPage) { applyInboxPage(inbox.deferredPage); renderConsent(); }
  }));
  ui["inbox-status"].addEventListener("change", () => changeInbox("filter"));
  ui["inbox-newest"].addEventListener("click", () => changeInbox("newest"));
  ui["inbox-newer"].addEventListener("click", () => changeInbox("newer"));
  ui["inbox-older"].addEventListener("click", () => changeInbox("older"));
  ui["inbox-visit"].addEventListener("click", () => {
    if (isConsent() && canAct() && sameCell(observation.self.position, [1, 6])) submitAction({ type: "visit", activityId: "garden" });
  });
  ui["postcard-text"].addEventListener("input", () => {
    if (draftKey) storageSet(draftKey, ui["postcard-text"].value || null);
    renderPostcards();
  });
  $("postcard-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const activity = selectedActivity(), visit = unusedVisit(activity), text = ui["postcard-text"].value;
    if (activity && visit && sameCell(activity.position, observation?.self.position) && validPostcardText(text)) {
      submitAction({ type: "postcard", activityId: activity.id, visitCommandId: visit.commandId, text });
    }
  });
  ui["proposal-text"].addEventListener("input", () => { if (proposalDraftKey) storageSet(proposalDraftKey, ui["proposal-text"].value || null); renderMosaic(); });
  ui["mosaic-clear"].addEventListener("click", () => {
    if (!isMosaic() || pending || commandBusy) return;
    mosaicDraft = null; storageSet(mosaicKey, null); renderMosaic();
  });
  ui["mosaic-publish"].addEventListener("click", () => {
    const mode = isConsent() ? consent.draftMode(mosaicDraft, identity?.actorId) : { kind: "direct" };
    const visit = mode.kind === "proposal" ? unusedProposalVisit() : unusedMosaicVisit();
    if (isMosaic() && canAct() && visit && mosaicDraft && mode.kind !== "mixed" && mosaicDraft.baseRevision === observation.mosaic.revision && sameCell(observation.self.position, [1, 6])) {
      const action = { type: "mosaic", activityId: "garden", visitCommandId: visit.commandId, expectedMosaicRevision: mosaicDraft.baseRevision, patch: mosaic.canonical(mosaicDraft.patch) };
      if (mode.kind === "proposal") { if (!consent.text(ui["proposal-text"].value)) return; action.type = "mosaic_propose"; action.text = ui["proposal-text"].value; }
      submitAction(action);
    }
  });
  ui["build-button"].addEventListener("click", () => {
    const recipe = selectedRecipe();
    if (selected && recipe) submitAction({ type: "build", recipeId: recipe.id, at: [...selected] });
  });
  ui["query-command-button"].addEventListener("click", () => resolvePending(false));
  ui["retry-command-button"].addEventListener("click", () => resolvePending(true));
  $("selection-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const cell = [ui["cell-x"].valueAsNumber, ui["cell-y"].valueAsNumber];
    if (isCell(cell)) selectCell(cell);
    else feedback("选择格坐标需要是 0 至 7 的整数。", "warning");
  });
  ui["world-canvas"].addEventListener("click", (event) => {
    const bounds = ui["world-canvas"].getBoundingClientRect();
    const { margin, unit } = mapGeometry();
    selectCell([Math.floor((event.clientX - bounds.left - margin) / unit), Math.floor((event.clientY - bounds.top - margin) / unit)]);
  });
  window.addEventListener("online", () => { if (token) { recoveryNeeded = true; refresh(); } });
  window.addEventListener("offline", () => { if (token) markOffline("浏览器当前离线。"); });
  window.addEventListener("resize", drawWorld);
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(drawWorld).observe(ui["world-canvas"].parentElement);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && token) refresh(); });
  loadStorage();
  render();
  if (token) connect(token);
})();
