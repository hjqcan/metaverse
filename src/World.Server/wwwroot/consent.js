(() => {
  "use strict";
  const mosaic = window.MosaicUI;
  const id = (v) => typeof v === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(v);
  const integer = (v) => Number.isSafeInteger(v) && v >= 0;
  const text = (v) => typeof v === "string" && Array.from(v).length >= 1 && Array.from(v).length <= 160 && /[^\p{White_Space}]/u.test(v) && !/[\p{Cc}\p{Cs}]/u.test(v);
  const position = (v) => Array.isArray(v) && v.length === 2 && v[0] === 1 && v[1] === 6;
  const common = (v, date) => v && v.activityId === "garden" && [v.authorActorId, v.commandId, v.visitCommandId].every(id)
    && integer(v.stateVersion) && position(v.position) && typeof v[date] === "string" && Number.isFinite(Date.parse(v[date]));
  function validReview(r) {
    if (!common(r, "reviewedAtUtc") || !id(r.proposalActorId) || !id(r.proposalCommandId) || !text(r.text) || !["accept", "reject"].includes(r.decision)) return false;
    if (r.decision === "reject") return r.mosaicEdit === null;
    const e = r.mosaicEdit;
    return mosaic.validEdit(e) && e.authorActorId === r.authorActorId && e.commandId === r.commandId && e.visitCommandId === r.visitCommandId
      && e.stateVersion === r.stateVersion && e.paintedAtUtc === r.reviewedAtUtc;
  }
  function validProposal(p) {
    return common(p, "proposedAtUtc") && id(p.targetActorId) && p.authorActorId !== p.targetActorId && integer(p.baseRevision) && mosaic.validPatch(p.patch) && text(p.text)
      && (p.review === undefined || p.review === null || reviewOf(p.review, p));
  }
  function reviewOf(r, p) {
    return validReview(r) && r.authorActorId === p.targetActorId && r.proposalActorId === p.authorActorId && r.proposalCommandId === p.commandId
      && r.stateVersion > p.stateVersion && (r.decision === "reject" || r.mosaicEdit.baseRevision === p.baseRevision && mosaic.equalPatch(r.mosaicEdit.patch, p.patch));
  }
  function proposalMatches(p, a, actor, command, version) {
    return validProposal(p) && p.authorActorId === actor && p.commandId === command && p.visitCommandId === a.visitCommandId && p.activityId === a.activityId
      && p.baseRevision === a.expectedMosaicRevision && mosaic.equalPatch(p.patch, a.patch) && p.text === a.text && p.stateVersion === version + 1;
  }
  function reviewMatches(r, a, actor, command, version, p) {
    return validProposal(p) && reviewOf(r, p) && r.authorActorId === actor && r.commandId === command && r.visitCommandId === a.visitCommandId
      && r.activityId === a.activityId && r.proposalActorId === a.proposalActorId && r.proposalCommandId === a.proposalCommandId
      && r.decision === a.decision && r.text === a.text && r.stateVersion === version + 1;
  }
  // Uses the original draft board; polling must never silently retarget another author.
  function draftMode(draft, actor) {
    if (!draft?.patch?.length) return { kind: "direct", target: null };
    const authors = draft.patch.map((c) => draft.baseCells[c.y * 5 + c.x].authorActorId);
    if (authors.every((a) => a === null || a === actor)) return { kind: "direct", target: null };
    if (authors.every((a) => a && a !== actor && a === authors[0])) return { kind: "proposal", target: authors[0] };
    return { kind: "mixed", target: null };
  }
  window.ConsentUI = Object.freeze({ text, validProposal, validReview, reviewOf, proposalMatches, reviewMatches, draftMode });
})();
