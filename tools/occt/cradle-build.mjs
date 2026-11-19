// Process-isolated builder: releases all native WASM allocations on exit.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {buildCradle,exportsFor} from './cradle.mjs';

const started=performance.now();
try {
  const args=process.argv.slice(2),receiptOnly=args.at(-1)==='--receipt';
  if(receiptOnly)args.pop();
  if(args.length>1 || (receiptOnly && !args[0])) throw Error('Usage: cradle-build.mjs [OUTPUT_DIRECTORY [--receipt]]');
  const params=JSON.parse(readFileSync(0,'utf8')||'{}');
  const built=await buildCradle(params),files=await exportsFor(built.shape);
  built.report.build_ms=performance.now()-started;
  const receipt={params:built.params,report:built.report},paths={};
  if (args[0]) {
    const out=resolve(args[0]);mkdirSync(out,{recursive:true});
    paths.step=resolve(out,'cradle.step');paths.stl=resolve(out,'cradle.stl');paths.report=resolve(out,'cradle.json');
    writeFileSync(paths.step,files.step);
    writeFileSync(paths.stl,files.stl);
    writeFileSync(paths.report,JSON.stringify(receipt,null,2)+'\n');
  }
  process.stdout.write(JSON.stringify(receiptOnly ? {...receipt,files:paths}
    : {...receipt,step:files.step,stl_base64:Buffer.from(files.stl).toString('base64')}));
} catch (e) { process.stderr.write(String(e.message)+'\n');process.exitCode=1; }
