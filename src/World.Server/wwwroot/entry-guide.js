(() => {
  "use strict";
  const cell = p => Array.isArray(p) && p.length === 2 && p.every(n => Number.isInteger(n) && n >= 0 && n < 8);
  const same = (a, b) => cell(a) && cell(b) && a[0] === b[0] && a[1] === b[1];
  const coord = p => `(${p[0]}, ${p[1]})`;
  function valid(g, o) {
    if (!g || g.version !== 1 || g.stateVersion !== o.stateVersion || g.actorId !== o.self.actorId || !same(g.position, o.self.position)
      || g.materials?.publicWood !== o.depot.wood || g.materials?.ownWood !== o.self.inventory.wood || !same(g.materials?.depotPosition, o.depot.position)
      || !g.participation || g.participation.walkWoodCost !== 0
      || !['visitSupported','postcardSupported','mosaicSupported','foreignMosaicNeedsConsent'].every(k => typeof g.participation[k] === 'boolean')
      || !Array.isArray(g.sharedBridges) || !Array.isArray(g.places)) return false;
    const bridges = o.entities.filter(e => e.definitionId === 'bridge');
    if (bridges.length !== g.sharedBridges.length || g.sharedBridges.some(b => !bridges.some(e => e.entityId === b.entityId && e.ownerActorId === b.ownerActorId && same(e.position,b.position)))) return false;
    const places = o.activities.length ? o.activities : [{id:'goal',label:'目标地',position:o.world.goal}];
    if (g.places.length !== places.length || new Set(g.places.map(p=>p.id)).size !== places.length) return false;
    return g.places.every(p => {
      if (!places.some(a => a.id === p.id && a.label === p.label && same(a.position,p.position)) || typeof p.reachable !== 'boolean'
        || !Array.isArray(p.route) || p.route.length > 63 || !Array.isArray(p.bridgeEntityIds)
        || p.activityId !== (o.activities.length ? p.id : null)) return false;
      if (!p.reachable) return p.walkingSteps === null && p.route.length === 0 && p.bridgeEntityIds.length === 0;
      if (p.walkingSteps !== p.route.length) return false;
      let previous = g.position;
      for (const step of p.route) {
        if (!cell(step) || Math.abs(step[0]-previous[0])+Math.abs(step[1]-previous[1]) !== 1 || o.world.blocked.some(b=>same(b,step))) return false;
        previous = step;
      }
      const used = [...new Set(p.route.flatMap(step => bridges.filter(b=>same(b.position,step)).map(b=>b.entityId)))];
      return same(previous,p.position) && JSON.stringify(used) === JSON.stringify(p.bridgeEntityIds);
    });
  }
  function create(panel, choose) {
    const elements = Object.fromEntries(['state','materials','bridges','participation','places'].map(k=>[k,document.getElementById(`entry-${k}`)]));
    const cards = new Map();
    const make = (tag,text) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
    return (observation, fresh) => {
      const g = observation?.entryGuide;
      panel.hidden = !observation || g === undefined;
      if (panel.hidden) {for(const el of Object.values(elements))el.replaceChildren();cards.clear();return;}
      if (!valid(g,observation)) {
        elements.state.textContent='这次导览尚未确认，请等待世界重新同步。';
        for(const key of ['materials','bridges','participation','places'])elements[key].replaceChildren();cards.clear();return;
      }
      panel.dataset.version=String(g.stateVersion);panel.dataset.actor=g.actorId;
      elements.state.textContent=`居民 ${g.actorId} · 位置 ${coord(g.position)} · 世界版本 ${g.stateVersion}${fresh?' · 当前观察':' · 上次观察，等待同步'}`;
      elements.materials.textContent=`公共木材 ${g.materials.publicWood} · 自己库存 ${g.materials.ownWood}。${g.materials.publicWood===0?'公共储备已空；木材不足时建造会受限。':'领取须到储备点或相邻格；显示余量不代表已为你预留。'}`;
      elements.bridges.textContent=g.sharedBridges.length ? `已有 ${g.sharedBridges.length} 段公共桥：${g.sharedBridges.map(b=>`居民 ${b.ownerActorId} 建于 ${coord(b.position)}`).join('；')}。通行不按建造者限制，也不要求你重建。` : '这里还没有已建桥段。能否到达各地点，以实际通路为准。';
      const p=g.participation;
      elements.participation.textContent='步行不消耗木材。'+(p.visitSupported?'到地点后可以记录到访。':'')+(p.postcardSupported?'本人到访后可写公开手记，不需木材。':'')+(p.mosaicSupported?`花园画布也不需木材，仍须本人到访${p.foreignMosaicNeedsConsent?'；修改他人格子需要对方同意':''}。`:'');
      const present = new Set(g.places.map(p=>p.id));
      for (const [id,c] of cards)if(!present.has(id)){c.article.remove();cards.delete(id);}
      for (const place of g.places) {
        let c=cards.get(place.id);
        if(!c){
          const article=make('article');article.className='entry-place';article.dataset.place=place.id;
          const title=make('h3'),state=make('p'),details=make('details'),summary=make('summary','查看步行路线'),route=make('p'),button=make('button','在地图上选择');
          button.type='button';button.className='button quiet';button.dataset.entrySelect=place.id;route.className='entry-route';details.append(summary,route);article.append(title,state,details,button);elements.places.append(article);
          button.addEventListener('click',()=>choose(place.id));c={article,title,state,details,route,button};cards.set(place.id,c);
        }
        c.title.textContent=`${place.label} ${coord(place.position)}`;c.article.dataset.reachable=String(place.reachable);
        c.state.textContent=place.reachable ? `${place.walkingSteps===0?'你已在这里':`可步行到达 · ${place.walkingSteps} 步`} · 0 木材${place.bridgeEntityIds.length?` · 复用 ${place.bridgeEntityIds.length} 段桥`:''}` : '当前通路尚未连通，不能直接步行到达。';
        c.route.textContent=place.reachable ? [g.position,...place.route].map(coord).join(' → ') : '未铺桥水面或墙阻断了当前路线。可以先参加其他可达地点的活动。';
        c.button.disabled=!fresh;c.button.textContent=place.activityId?'选作活动地点':'在地图上选择';
      }
    };
  }
  window.EntryGuideUI=Object.freeze({create});
})();
