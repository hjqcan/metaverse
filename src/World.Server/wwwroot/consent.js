(() => {
  "use strict";
  const mosaic = window.MosaicUI;
  const id = (v) => typeof v === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(v);
  const integer = (v) => Number.isSafeInteger(v) && v >= 0;
  function textIssue(value) {
    if (typeof value !== "string" || !/[^\p{White_Space}]/u.test(value)) return "请填写 1—160 字的理由，不能全是空白。";
    if (Array.from(value).length > 160) return "理由超过 160 字，请删减后再提交。";
    if (/[\p{Cc}\p{Cs}]/u.test(value)) return "理由不能换行或包含控制字符，请合并为一段文字。";
    return "";
  }
  const text = (value) => textIssue(value) === "";
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

  function presentation(proposal, board) {
    const review = proposal.review, accepted = review?.decision === "accept";
    const stale = !review && proposal.baseRevision < board.revision;
    const awaiting = !review && proposal.baseRevision > board.revision;
    const currentBase = !review && !stale && !awaiting;
    const cells = currentBase ? board.cells : mosaic.emptyCells();
    if (accepted) {
      const edit = review.mosaicEdit;
      for (const cell of edit.patch) cells[cell.y * 5 + cell.x] = { ...cell,
        authorActorId: edit.authorActorId, commandId: edit.commandId, stateVersion: edit.stateVersion };
    }
    return {
      stale, awaiting, cells, patch: accepted ? [] : proposal.patch,
      label: accepted ? "此次确认改动" : review ? "未采纳的改动" : stale ? "原提议（已过期）" : awaiting ? "提议（等待画布同步）" : "同意后（预览）",
      note: currentBase ? "虚线标出此次修改，其余格保持当前颜色。"
        : accepted ? "只展示本次确认的格子；后来的变化请看当前画布。"
          : review ? "只展示被拒绝的改动，这些颜色没有因此提交。"
            : awaiting ? "画布还未同步到提议基准，暂时只显示提议的格子。"
            : "只展示旧提议的格子，不代表原画布；不能按旧基准改图。",
      changes: proposal.patch.map((cell) => {
        const current = board.cells[cell.y * 5 + cell.x], nextColor = mosaic.colors[cell.color].label;
        const currentColor = mosaic.colors[current.color].label;
        const change = currentBase ? `${currentColor} → ${nextColor}`
          : accepted ? `本次确认${nextColor}；当前${currentColor}`
            : `提议${nextColor}${review ? "（未采纳）" : stale ? "（已过期）" : "（等待同步）"}；当前${currentColor}`;
        return `格 (${cell.x}, ${cell.y})：${change} · 当前最后作者：${current.authorActorId ? `居民 ${current.authorActorId}` : "无人署名"}`;
      })
    };
  }
  window.ConsentUI = Object.freeze({ text, textIssue, validProposal, validReview, reviewOf, proposalMatches, reviewMatches, draftMode, presentation });
})();
