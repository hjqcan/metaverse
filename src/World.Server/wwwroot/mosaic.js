(() => {
  "use strict";
  const palette = [
    { id: "blank", label: "空白", hex: "#F4F0E6" }, { id: "leaf", label: "叶绿", hex: "#42745B" },
    { id: "river", label: "河蓝", hex: "#477FA3" }, { id: "sun", label: "日黄", hex: "#E4B858" },
    { id: "rose", label: "花红", hex: "#C86A70" }, { id: "ink", label: "墨色", hex: "#37444D" }
  ];
  const colors = Object.fromEntries(palette.map((c) => [c.id, c]));
  const integer = (n) => Number.isSafeInteger(n) && n >= 0;
  const tile = (c) => c && integer(c.x) && c.x < 5 && integer(c.y) && c.y < 5 && Object.hasOwn(colors, c.color);
  const validPatch = (p) => Array.isArray(p) && p.length >= 1 && p.length <= 8 && p.every(tile)
    && p.every((c) => Object.keys(c).sort().join(",") === "color,x,y") && new Set(p.map((c) => `${c.x},${c.y}`)).size === p.length;
  const canonical = (p) => p.map(({ x, y, color }) => ({ x, y, color })).sort((a, b) => a.y - b.y || a.x - b.x);
  const equalPatch = (a, b) => validPatch(a) && validPatch(b) && JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  const validBoard = (m) => m && m.activityId === "garden" && m.width === 5 && m.height === 5 && integer(m.revision)
    && Array.isArray(m.palette) && m.palette.length === 6 && m.palette.every((p, i) => p?.id === palette[i].id && p.label === palette[i].label && typeof p.hex === "string" && p.hex.toUpperCase() === palette[i].hex)
    && Array.isArray(m.cells) && m.cells.length === 25 && m.cells.every((c, i) => tile(c) && c.x === i % 5 && c.y === Math.floor(i / 5)
      && (c.authorActorId === null && c.commandId === null && c.stateVersion === null && c.color === "blank"
        || typeof c.authorActorId === "string" && typeof c.commandId === "string" && integer(c.stateVersion)));
  const validEdit = (e) => e && e.activityId === "garden" && [e.authorActorId, e.commandId, e.visitCommandId].every((v) => typeof v === "string" && v.length > 0)
    && integer(e.baseRevision) && e.revision === e.baseRevision + 1 && validPatch(e.patch) && integer(e.stateVersion)
    && typeof e.paintedAtUtc === "string" && Number.isFinite(Date.parse(e.paintedAtUtc))
    && Array.isArray(e.position) && e.position.length === 2 && e.position[0] === 1 && e.position[1] === 6;
  const emptyCells = () => Array.from({ length: 25 }, (_, i) => ({ x: i % 5, y: Math.floor(i / 5), color: "blank", authorActorId: null, commandId: null, stateVersion: null }));

  // Stable nodes preserve keyboard focus across world polling. Styles only use this fixed palette.
  function renderBoard(root, cells, { patch = [], interactive = false, disabled = false, onCell = null } = {}) {
    const tag = interactive ? "BUTTON" : "DIV";
    if (root.children.length !== 25 || root.firstElementChild.tagName !== tag) {
      root.replaceChildren(...Array.from({ length: 25 }, () => {
        const el = document.createElement(tag.toLowerCase());
        el.className = "mosaic-cell";
        if (interactive) el.type = "button";
        return el;
      }));
    }
    root.setAttribute("role", interactive ? "group" : "img");
    const descriptions = [];
    [...root.children].forEach((el, i) => {
      const cell = cells[i], proposed = patch.find((p) => p.x === cell.x && p.y === cell.y);
      const color = colors[proposed?.color || cell.color];
      const description = `格 (${cell.x}, ${cell.y}) · ${color.label}${proposed ? " · 未发表" : cell.authorActorId ? ` · 居民 ${cell.authorActorId} · v${cell.stateVersion}` : " · 尚无人绘制"}`;
      el.style.backgroundColor = color.hex;
      el.dataset.x = cell.x; el.dataset.y = cell.y; el.dataset.color = color.id;
      el.dataset.draft = String(Boolean(proposed));
      el.title = description;
      if (interactive) {
        el.disabled = disabled;
        el.setAttribute("aria-label", description);
        el.setAttribute("aria-pressed", String(Boolean(proposed)));
        el.onclick = () => onCell?.(cell.x, cell.y);
        el.onkeydown = (event) => {
          const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -5, ArrowDown: 5 }[event.key];
          if (offset === undefined) return;
          event.preventDefault(); event.stopPropagation();
          const next = i + offset;
          if (next >= 0 && next < 25 && (Math.abs(offset) === 5 || Math.floor(next / 5) === Math.floor(i / 5))) root.children[next].focus();
        };
      }
      if (cell.color !== "blank" || proposed) descriptions.push(description);
    });
    root.setAttribute("aria-label", interactive ? "你的画布草稿，方向键在格子之间选择，空格或回车上色" : `5 × 5 共同画布。${descriptions.join("；") || "全部空白"}`);
  }
  window.MosaicUI = Object.freeze({ palette, colors, validPatch, canonical, equalPatch, validBoard, validEdit, emptyCells, renderBoard });
})();
