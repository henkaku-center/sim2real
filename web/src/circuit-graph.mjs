// Design-derived graph adapter shared by agents and the existing build scene.
// No DOM, tutorial, separate diagram or persistent duplicate connectivity.
export function createCircuitGraph(graph, parts, sceneSource) {
  if (graph.schema !== 'aps-circuit/1') throw Error('Unsupported circuit graph');
  if (!graph.cadBinding?.valid) throw Error('Circuit CAD binding is stale; regenerate the design snapshot');
  const native=graph.sources?.find(s=>s.path===sceneSource?.assembly);
  if(!native||native.sha256!==sceneSource?.assembly_sha256)throw Error('Circuit/native scene provenance differs; regenerate from the same design');
  const pins = new Map(graph.pins.map(p => [p.id, p]));
  const nets = new Map(graph.nets.map(n => [n.id, n]));
  const partIds = new Set(parts.map(p => p.id));
  const memberships = new Map();
  if (pins.size !== graph.pins.length || nets.size !== graph.nets.length) throw Error('Duplicate circuit IDs');
  for (const net of nets.values()) {
    if (net.layer !== 'external') throw Error(`Unsupported circuit layer: ${net.id}`);
    for (const id of net.pins) {
      if (!pins.has(id) || memberships.has(id)) throw Error(`Invalid net endpoint: ${id}`);
      memberships.set(id, net);
    }
    for (const id of net.partIds) if (!partIds.has(id)) throw Error(`Circuit CAD constraint: missing ${id} in ${net.id}`);
  }
  for (const pin of pins.values()) {
    if (!['connected', 'no_connect', 'unknown'].includes(pin.state)) throw Error(`Invalid pin state: ${pin.id}`);
    if ((pin.state === 'connected') !== memberships.has(pin.id)) throw Error(`Circuit pin-state constraint: ${pin.id}`);
  }
  const resolve = id => {
    if (pins.has(id)) return {pin:pins.get(id), nets:memberships.has(id)?[memberships.get(id)]:[]};
    if (nets.has(id)) return {pin:null, nets:[nets.get(id)]};
    throw Error(`Unknown circuit ID: ${id}`);
  };
  const query = id => {
    const result=resolve(id);
    return structuredClone({id, scope:graph.scope, pin:result.pin, nets:result.nets,
      firmware:graph.firmware.filter(f=>f.pin===id||f.role.toLowerCase()===id.split('.').at(-1).toLowerCase()),
      unknowns:graph.unknowns.filter(u=>u.pins.includes(id)), evidence:graph.evidence,
      sources:graph.sources??graph.sourceDigests});
  };
  const highlights = id => new Map((id==='all'?[...nets.values()]:resolve(id).nets)
    .flatMap(net=>net.partIds.map(part=>[part,net.colour])));
  return Object.freeze({query, highlights,
    ids:()=>({pins:[...pins.keys()],nets:[...nets.keys()]}),
    allParts:new Set([...nets.values()].flatMap(n=>n.partIds))});
}

export function circuitRevealStyle(id, highlighted, allConductors) {
  if (!highlighted.size) return {};
  // The renderer already uses edgeOnly for the cable-channel reveal. Reuse it
  // for structural obstructions instead of inventing a second transparency path.
  return {edgeOnly:!allConductors.has(id), colour:highlighted.get(id)??null};
}
