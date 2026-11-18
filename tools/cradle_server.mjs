#!/usr/bin/env node
// Local, bounded CAD service. Mount through Tailscale Serve; never expose the
// repository, invoke a shell or accept an output path from a network request.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
import {spawn} from 'node:child_process';
import {parameters,PRESETS} from './occt/cradle.mjs';

const root=dirname(fileURLToPath(import.meta.url));
const routes=new Map([
  ['', ['cradle_web/index.html','text/html; charset=utf-8']],
  ['index.html',['cradle_web/index.html','text/html; charset=utf-8']],
  ['app.js',['cradle_web/app.js','text/javascript']],
  ['style.css',['cradle_web/style.css','text/css']],
  ...['three.module.js','three.core.js','OrbitControls.js'].map(n=>['vendor/'+n,['cad_workbench_web/vendor/'+n,'text/javascript']]),
  ['vendor/LICENSE',['cad_workbench_web/vendor/LICENSE','text/plain']],
]);

export function createServer() {
  let active=null;
  const send=(res,status,obj)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(obj));};
  const server=http.createServer(async(req,res)=>{
    try {
      const host=new URL('http://'+(req.headers.host||'')).hostname;
      if(!['localhost','127.0.0.1','[::1]'].includes(host) && !host.endsWith('.ts.net'))
        return send(res,403,{error:'Unrecognised host'});
      const u=new URL(req.url,'http://localhost');
      // Works directly and behind /battery-cradle/, with the proxy retaining or
      // stripping the prefix. No other paths are served.
      const path=u.pathname.replace(/^\/battery-cradle(?=\/)/,'').replace(/^\//,'');
      if (req.method==='GET' && path==='api/presets') return send(res,200,PRESETS);
      if (req.method==='GET' && path==='api/health') return send(res,200,{service:'sesame-battery-cradle',revision:process.env.SOURCE_REVISION||'working-tree'});
      if (req.method==='POST' && path==='api/build') {
        if (req.headers['sec-fetch-site']==='cross-site') return send(res,403,{error:'Cross-site builds are not allowed'});
        if (!String(req.headers['content-type']||'').startsWith('application/json')) return send(res,415,{error:'Send application/json'});
        if (active) return send(res,503,{error:'Another build is running. Try again shortly.'});
        let body='';
        for await (const chunk of req) { body+=chunk; if(Buffer.byteLength(body)>4096) return send(res,413,{error:'Request is too large'}); }
        let p;
        try {p=parameters(JSON.parse(body));} catch(e) {return send(res,400,{error:e.message});}
        // Reserve only after parsing, but re-check because another request could
        // have acquired the build slot while this request was being streamed.
        if (active) return send(res,503,{error:'Another build is running. Try again shortly.'});
        const child=spawn(process.execPath,[join(root,'occt/cradle-build.mjs')],{stdio:['pipe','pipe','pipe']});
        active=child;let output='',errors='',finished=false;
        const timer=setTimeout(()=>child.kill('SIGKILL'),30000);
        const finish=(code)=>{
          if(finished)return;finished=true;clearTimeout(timer);active=null;
          if(res.destroyed)return;
          if(code!==0)return send(res,500,{error:'CAD build failed; the previous model has not changed.'});
          try {send(res,200,JSON.parse(output));} catch {send(res,500,{error:'Invalid build result'});}
        };
        child.stdout.on('data',b=>{output+=b;if(output.length>4_000_000)child.kill('SIGKILL');});
        child.stderr.on('data',b=>{if(errors.length<2048)errors+=b;});
        child.on('error',()=>finish(1));child.on('close',finish);
        res.on('close',()=>{if(!finished)child.kill('SIGKILL');});
        child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(p));
        return;
      }
      if(req.method!=='GET')return send(res,405,{error:'Method not allowed'});
      const file=routes.get(path);if(!file)return send(res,404,{error:'Not found'});
      const bytes=await readFile(join(root,file[0]));
      res.writeHead(200,{'Content-Type':file[1],'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'self'"});
      res.end(bytes);
    } catch {if(!res.headersSent)send(res,500,{error:'Request failed'});else res.end();}
  });
  server.requestTimeout=35000;
  server.on('close',()=>active?.kill('SIGKILL'));
  return server;
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const port=Number(process.env.PORT||8862);
  const server=createServer();
  server.listen(port,'127.0.0.1',()=>console.log(`Battery cradle: http://127.0.0.1:${port}/`));
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close(()=>process.exit(0)));
}
