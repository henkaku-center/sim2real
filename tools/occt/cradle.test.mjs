import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import * as k from './kernel.mjs';
import {buildCradle,exportsFor,parameters,PRESETS} from './cradle.mjs';

function meshFacts(raw) {
  const text=Buffer.from(raw).toString();
  const vertices=[...text.matchAll(/vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/g)].map(m=>m.slice(1).map(Number));
  assert.ok(vertices.length>0 && vertices.length%3===0);
  const edges=new Map();let volume=0;
  const key=v=>v.map(x=>x.toFixed(6)).join(',');
  for(let i=0;i<vertices.length;i+=3) {
    const [a,b,c]=vertices.slice(i,i+3);
    volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6;
    for(const [u,v] of [[a,b],[b,c],[c,a]]) {
      const x=key(u),y=key(v),id=[x,y].sort().join('|');
      const e=edges.get(id)||[0,0];e[0]++;e[1]+=x<y?1:-1;edges.set(id,e);
    }
  }
  assert.ok([...edges.values()].every(([count,winding])=>count===2 && winding===0),'STL must be a closed consistently wound two-manifold');
  return {volume:Math.abs(volume),bounds:[0,1,2].map(i=>Math.max(...vertices.map(v=>v[i]))-Math.min(...vertices.map(v=>v[i])))};
}

for(const preset of PRESETS) test(`${preset.id}: exact solid, openings and STEP/STL roundtrip`,async()=>{
  const b=await buildCradle(preset.params),p=b.params,r=b.report;
  assert.equal(r.valid,true);assert.equal(r.solid_count,1);assert.equal(r.battery_overlap_mm3,0);
  const L=p.length+2*p.clearance,W=p.width+2*p.clearance+2*p.wall,S=p.strapWidth+0.6;
  const analytic=L*W*p.base+2*L*p.wall*p.railHeight+4*12*8*p.base-4*Math.PI*1.7**2*p.base-2*S*W-4*S*2*(p.base-1);
  assert.ok(Math.abs(r.volume_mm3-analytic)<0.001,'Boolean result must conserve expected material');
  const f=await exportsFor(b.shape),mesh=meshFacts(f.stl);
  assert.ok(Math.abs(mesh.volume-r.volume_mm3)/r.volume_mm3<0.002);
  r.outer_mm.forEach((v,i)=>assert.ok(Math.abs(mesh.bounds[i]-v)<0.001));
  const dir=mkdtempSync(join(tmpdir(),'cradle-roundtrip-'));
  try {
    const name=join(dir,'cradle.step');writeFileSync(name,f.step);
    const reread=k.readStep(name);
    assert.ok(k.isValid(reread));assert.equal(k.explore(reread,'SOLID').length,1);
    assert.ok(Math.abs(k.volume(reread)-r.volume_mm3)<0.001);
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('edits change the physical opening; reverting restores geometry',async()=>{
  const a=await buildCradle(),b=await buildCradle({width:33}),c=await buildCradle();
  assert.equal(b.report.outer_mm[1]-a.report.outer_mm[1],5);
  assert.deepEqual(c.report.outer_mm,a.report.outer_mm);
  assert.ok(Math.abs(c.report.volume_mm3-a.report.volume_mm3)<1e-7);
});

test('invalid input is rejected before loading geometry',()=>{
  for(const input of [{length:-1},{width:Infinity},{base:1},{railHeight:12,height:8},{wall:'2'},{path:'/etc/passwd'},[],null])
    assert.throws(()=>parameters(input));
});

test('boundary dimensions retain one valid solid and zero battery intersection',async()=>{
  for(const params of [{length:40,width:20,height:8,clearance:.2,wall:1.6,base:2.2,strapWidth:16},
    {length:130,width:80,height:50,clearance:1.5,wall:4,base:5,railHeight:12,strapWidth:6}]) {
    const b=await buildCradle(params);assert.equal(b.report.solid_count,1);assert.equal(b.report.battery_overlap_mm3,0);
  }
});
