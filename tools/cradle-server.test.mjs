import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createServer} from './cradle_server.mjs';

test('bounded local API: presets, validation, export and path isolation',async()=>{
  const server=createServer();server.listen(0,'127.0.0.1');await once(server,'listening');
  const base=`http://127.0.0.1:${server.address().port}/`;
  const post=(data,headers={})=>fetch(base+'api/build',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(data)});
  try {
    const presets=await(await fetch(base+'api/presets')).json();assert.equal(presets.length,3);
    assert.equal((await fetch(base+'AGENTS.md')).status,404);
    assert.equal((await fetch(base+'api/build',{method:'POST',body:'{}'})).status,415);
    assert.equal((await post({}, {'Sec-Fetch-Site':'cross-site'})).status,403);
    assert.equal((await post({base:1})).status,400);
    assert.equal((await post({unknown:2})).status,400);
    const response=await post({});assert.equal(response.status,200);
    const data=await response.json();assert.equal(data.report.solid_count,1);
    assert.match(data.step,/ISO-10303-21/);assert.ok(Buffer.from(data.stl_base64,'base64').length>1000);
    assert.equal((await fetch(base+'battery-cradle/api/presets')).status,200);
  } finally {await new Promise(resolve=>server.close(resolve));}
});
