import test from 'node:test';
import assert from 'node:assert/strict';
import {createCircuitGraph,circuitRevealStyle} from '../web/src/circuit-graph.mjs';
const fixture=()=>({schema:'aps-circuit/1',scope:'test',cadBinding:{valid:true},
  sources:[{path:'native.FCStd',sha256:'current'}],
  pins:[{id:'a',state:'connected'},{id:'b',state:'connected'},{id:'oe',state:'no_connect'}],
  nets:[{id:'n',layer:'external',pins:['a','b'],partIds:['wire'],colour:'#123456'}],
  firmware:[],unknowns:[],evidence:{}});
const source={assembly:'native.FCStd',assembly_sha256:'current'};
test('same connectivity drives agent query and 3D highlights',()=>{
  const c=createCircuitGraph(fixture(),[{id:'wire'},{id:'shell'}],source);
  assert.equal(c.query('a').nets[0].id,'n');
  assert.equal(c.highlights('a').get('wire'),'#123456');
  assert.equal(c.highlights('oe').size,0);
  assert.equal(circuitRevealStyle('shell',c.highlights('a'),c.allParts).edgeOnly,true);
  assert.equal(circuitRevealStyle('wire',c.highlights('a'),c.allParts).edgeOnly,false);
  assert.deepEqual(circuitRevealStyle('shell',new Map(),c.allParts),{});
});
test('design/scene and no-connect divergence fails instead of stale display',()=>{
  assert.throws(()=>createCircuitGraph(fixture(),[],source),/missing wire/);
  assert.throws(()=>createCircuitGraph(fixture(),[{id:'wire'}],{...source,assembly_sha256:'old'}),/provenance differs/);
  const g=fixture();g.nets[0].pins.push('oe');
  assert.throws(()=>createCircuitGraph(g,[{id:'wire'}],source),/pin-state/);
});
test('no course-specific pin assumption; unknown IDs fail explicitly',()=>{
  const c=createCircuitGraph(fixture(),[{id:'wire'}],source);
  assert.throws(()=>c.query('hub.OE'),/Unknown/);
  const r=c.query('a');r.nets[0].pins.push('oe');
  assert.equal(c.query('a').nets[0].pins.length,2);
});
