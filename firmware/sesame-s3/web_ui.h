// SPDX-License-Identifier: Apache-2.0
#pragma once
// Phone console. Macros: one command per line (or ';'). "?cmd" tolerates ERR,
// "wait MS" pauses, {J} is the selected joint, and motion/rest/sweep wait until
// the robot reports completion. Heartbeats run only while the page is visible;
// hiding it lets the firmware freeze and hold (it never sends off by itself).
constexpr char WEB_UI[] = R"HTML(<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sesame S3</title>
<style>
body{font:15px system-ui,sans-serif;margin:0 0 40px;background:#f4f4f4}
header{position:sticky;top:0;background:#222;color:#fff;padding:6px 8px;z-index:1}
#st{font:12px ui-monospace,monospace;white-space:pre-wrap;min-height:2.4em}
section{background:#fff;margin:8px;padding:8px;border-radius:8px}
h2{font-size:13px;margin:0 0 6px;color:#555;text-transform:uppercase}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:6px}
button{font:inherit;padding:10px 4px;border:0;border-radius:6px;background:#dde3ee}
button:active{background:#aab}.off{background:#d22;color:#fff;font-weight:bold}.fr{background:#e90}
.top{display:grid;grid-template-columns:2fr 1fr;gap:6px;margin-top:6px}
input,select,textarea{font:inherit;box-sizing:border-box}textarea{width:100%;height:7em}
.row{display:flex;gap:6px;margin-bottom:6px}.row>*{flex:1}
pre{font:12px ui-monospace,monospace;white-space:pre-wrap;margin:0;max-height:40vh;overflow:auto}
</style>
<header><div id="st">connecting…</div>
<div class="top"><button class="off" onclick="stopAll('off')">OUTPUTS OFF</button>
<button class="fr" onclick="stopAll('stop')">Freeze</button></div></header>
<section><h2>Motions (auto arm run)</h2><div class="g" id="motions"></div></section>
<section><h2>Calibration</h2><div class="row"><select id="joint"></select>
<button onclick="macro('off;arm joint {J}')">Arm joint</button></div><div class="g">
<button onclick="macro('angle 90')">Angle 90</button><button onclick="macro('sweep 75 105')">Sweep 75–105</button>
<button onclick="macro('jog -5')">Jog −5</button><button onclick="macro('jog -1')">Jog −1</button>
<button onclick="macro('jog 1')">Jog +1</button><button onclick="macro('jog 5')">Jog +5</button>
<button onclick="macro('off;verify {J}')">Verify joint</button><button onclick="macro('off;save')">Save</button>
<button onclick="macro('show')">Show</button><button onclick="macro('status;wifi')">Status</button>
</div></section>
<section><h2>My macros</h2><div class="g" id="mine"></div>
<details><summary>Edit</summary><input id="mname" placeholder="name" style="width:100%;margin:6px 0">
<textarea id="mbody" autocapitalize="off" autocorrect="off" spellcheck="false"
placeholder="?arm run&#10;motion stand&#10;wait 1000&#10;motion wave"></textarea>
<div class="row"><button onclick="saveMacro()">Save</button><button onclick="delMacro()">Delete</button></div></details></section>
<section><h2>Command</h2><form class="row" onsubmit="event.preventDefault();macro(cmd.value)">
<input id="cmd" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="a;b;c" value="help">
<button style="flex:0 0 5em">Run</button></form><pre id="log"></pre></section>
<script>
const $=s=>document.querySelector(s), log=$('#log'), cmd=$('#cmd');
const MODES=['OFF','Channel','Bench','Joint','Assembly','Run','Reference','ClockMeasure'];
const JOINTS=['L1','L2','L3','L4','R1','R2','R3','R4'];
const MOTIONS='stand rest wave dance swim point pushup bow cute freaky worm shake shrug dead crab walk walk_backward turn_left turn_right'.split(' ');
const DEFAULTS={'Hello':'?arm run\nmotion stand\nmotion wave\nmotion rest','Party':'?arm run\nmotion stand\nmotion dance\nmotion shake\nmotion rest'};
let lock=Promise.resolve(), inflight=0, run=0, last={}, up=0, link=[];
for(const j of JOINTS)$('#joint').add(new Option(j));
$('#joint').value=localStorage.joint||'L1';$('#joint').onchange=e=>localStorage.joint=e.target.value;
for(const m of MOTIONS)add('#motions',m,'?arm run\nmotion '+m);
function add(where,label,body,edit){const b=document.createElement('button');b.textContent=label;
b.onclick=()=>{if(edit){$('#mname').value=label;$('#mbody').value=body}macro(body)};$(where).append(b)}
function mine(){return JSON.parse(localStorage.macros||JSON.stringify(DEFAULTS))}
function drawMine(){$('#mine').textContent='';for(const[k,v]of Object.entries(mine()))add('#mine',k,v,1)}
function saveMacro(){const m=mine(),k=$('#mname').value.trim();if(!k)return;m[k]=$('#mbody').value;localStorage.macros=JSON.stringify(m);drawMine()}
function delMacro(){const m=mine();delete m[$('#mname').value.trim()];localStorage.macros=JSON.stringify(m);drawMine()}
drawMine();
function say(t){if(t)log.textContent=(t+'\n'+log.textContent).slice(0,6000)}
// One request at a time: the firmware serves a single client.
// Last 30 request round trips (ms; -1 = failed) for the link line.
function note(ms){link.push(ms);if(link.length>30)link.shift()}
function req(path,ms=3000){const p=lock.then(async()=>{inflight++;const t0=performance.now();
try{const r=await fetch(path,{signal:AbortSignal.timeout(ms)});const t=await r.text();note(performance.now()-t0);return [r.ok,t]}
catch(e){note(-1);throw e}finally{inflight--}});lock=p.catch(()=>{});return p}
function linkText(){const ok=link.filter(x=>x>=0);
return `link: fail ${link.length-ok.length}/${link.length}`+(ok.length?` rtt avg ${Math.round(ok.reduce((a,b)=>a+b,0)/ok.length)} max ${Math.round(Math.max(...ok))} ms`:'')}
const send=c=>req('/cmd?c='+encodeURIComponent(c));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function status(){const[,t]=await req('/status');const g=k=>(t.match(new RegExp(' '+k+'=(\\S+)'))||[])[1];
last={mode:MODES[+(t.match(/^mode=(\d)/)||[])[1]]||'?',out:g('outputs'),motion:g('motion'),sweep:g('sweep'),hold:g('hold'),owner:g('owner'),
sta:(t.match(/STA.* ip=(\S+)/)||[])[1]};
last.rssi=g('ap_rssi');last.drops=g('http_drops');const u=+g('up_s');if(u<up)say(`ROBOT RESTARTED (reset=${g('reset')}); outputs are OFF`);up=u;
$('#st').textContent=`${last.hold==='1'?'HOLD ':''}${last.mode} outputs=${last.out} motion=${last.motion}${last.sweep==='1'?' sweeping':''}`+
(last.sta&&last.sta!=='0.0.0.0'?`\nLAN http://${last.sta}  (${location.host})`:`\n${location.host}`)+
`\n${linkText()} | phone rssi ${last.rssi} dBm | drops ${last.drops}`;return last}
// Safety commands bypass the request queue.
async function stopAll(c){run++;say('> '+c);try{say(await (await fetch('/cmd?c='+c,{signal:AbortSignal.timeout(3000)})).text())}
catch(e){say('ERR no reply: '+e.name+'; check phone is still on Sesame Wi-Fi. BOOT button stops the robot')}}
async function macro(text){const id=++run, joint=$('#joint').value;
const lines=text.replace(/\{J\}/g,joint).split(/[;\n]/).map(s=>s.trim()).filter(Boolean);
for(let line of lines){if(id!==run)return say('(macro cancelled)');
const ok_err=line[0]==='?';if(ok_err)line=line.slice(1).trim();
const w=line.match(/^wait\s+(\d+)$/);if(w){await sleep(+w[1]);continue}
say('> '+line);let ok,t;try{[ok,t]=await send(line)}catch(e){return say('ERR no reply ('+e.name+'); phone left Sesame Wi-Fi? robot holds pose after 500 ms')}
say(t);if(!ok&&!ok_err)return say('(macro stopped)');
if(ok&&/^(motion|run|rest|sweep)\b/.test(line))for(let n=0;n<300&&id===run;n++){await sleep(250);
const s=await status().catch(()=>({}));if(s.motion==='none'&&s.sweep==='0')break}}}
// Heartbeat only while visible; hidden pages stop, the robot freezes and holds.
setInterval(()=>{if(!document.hidden&&!inflight)send('heartbeat').catch(()=>{})},200);
setInterval(()=>{if(!document.hidden)status().catch(()=>{$('#st').textContent='no connection: is the phone still on this robot\'s Wi-Fi?\n'+linkText()})},1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)status().catch(()=>{})});
</script>)HTML";
