(() => {
  "use strict";
  const integer = (n) => Number.isSafeInteger(n) && n >= 0;
  const scopes = ["received", "sent", "all"], statuses = ["pending", "reviewed", "all"];
  const sameQuery = (a, b) => Boolean(a && b && ["scope", "status", "before", "limit"].every((k) => a[k] === b[k]));
  const inScope = (p, scope, actor) => scope === "all" || (scope === "received" ? p.targetActorId : p.authorActorId) === actor;
  const inStatus = (p, status) => status === "all" || (status === "reviewed") === Boolean(p.review);
  const supported = (o) => o?.rulesVersion === "r6" && o.mosaicProposalInbox?.version === 1 && o.mosaicProposalInbox.maxPageSize === 20;

  // A page is usable for review only after the envelope, query and every complete record agree.
  function validPage(d, query, identity, floor) {
    if (!d || d.schemaVersion !== 1 || d.rulesVersion !== "r6" || d.error
      || d.identity?.actorId !== identity.actorId || d.identity?.sessionId !== identity.sessionId
      || !integer(d.stateVersion) || d.stateVersion < floor || !integer(d.eventCursor)
      || !sameQuery(d.query, query) || !scopes.includes(query.scope) || !statuses.includes(query.status)
      || !d.counts || !["pending", "reviewed", "all"].every((k) => integer(d.counts[k]))
      || d.counts.all !== d.counts.pending + d.counts.reviewed
      || !Array.isArray(d.items) || d.items.length > query.limit) return false;
    let previous = query.before ?? Infinity;
    const keys = new Set();
    for (const p of d.items) {
      if (!window.ConsentUI.validProposal(p) || !Object.hasOwn(p, "review") || p.review === undefined
        || p.stateVersion <= 0 || p.stateVersion >= previous || p.stateVersion > d.stateVersion
        || p.review && p.review.stateVersion > d.stateVersion
        || !inScope(p, query.scope, identity.actorId) || !inStatus(p, query.status)) return false;
      const key = `${p.authorActorId}/${p.commandId}`;
      if (keys.has(key)) return false;
      keys.add(key); previous = p.stateVersion;
    }
    if (d.nextBefore !== null && (!integer(d.nextBefore) || d.nextBefore <= 0
      || d.items.length !== query.limit || d.nextBefore !== previous)) return false;
    return d.counts[query.status] >= d.items.length + (d.nextBefore === null ? 0 : 1);
  }

  function legacyPage(observation, query) {
    const scoped = observation.mosaicProposals.filter((p) => inScope(p, query.scope, observation.identity.actorId));
    const pending = scoped.filter((p) => !p.review).length;
    const matching = scoped.filter((p) => inStatus(p, query.status) && (query.before === null || p.stateVersion < query.before))
      .sort((a, b) => b.stateVersion - a.stateVersion);
    const items = matching.slice(0, query.limit);
    return { query: { ...query }, counts: { pending, reviewed: scoped.length - pending, all: scoped.length }, items,
      nextBefore: matching.length > items.length ? items.at(-1).stateVersion : null, stateVersion: observation.stateVersion };
  }

  window.MosaicInbox = Object.freeze({ supported, validPage, legacyPage, sameQuery, scopes, statuses });
})();
