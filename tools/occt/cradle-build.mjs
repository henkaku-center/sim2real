// Process-isolated builder: releases all native WASM allocations on exit.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {buildCradle,exportsFor} from './cradle.mjs';

const started=performance.now();
try {
  const params=JSON.parse(readFileSync(0,'utf8')||'{}');
  const built=await buildCradle(params),files=await exportsFor(built.shape);
  built.report.build_ms=performance.now()-started;
  const result={params:built.params,report:built.report,step:files.step,stl_base64:Buffer.from(files.stl).toString('base64')};
  if (process.argv[2]) {
    const out=resolve(process.argv[2]);mkdirSync(out,{recursive:true});
    writeFileSync(resolve(out,'cradle.step'),files.step);
    writeFileSync(resolve(out,'cradle.stl'),files.stl);
    writeFileSync(resolve(out,'cradle.json'),JSON.stringify({params:built.params,report:built.report},null,2)+'\n');
  }
  process.stdout.write(JSON.stringify(result));
} catch (e) { process.stderr.write(String(e.message)+'\n');process.exitCode=1; }
