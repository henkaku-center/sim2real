// SPDX-License-Identifier: Apache-2.0
#pragma once
constexpr char WEB_UI[] = R"HTML(<!doctype html><meta name="viewport" content="width=device-width"><title>Sesame S3</title>
<h1>Sesame S3</h1><p>Support robot. BOOT aborts. Arm alone leaves outputs off.</p>
<input id="cmd" value="help"><button onclick="send()">Send</button>
<button onclick="send('off')">OUTPUTS OFF</button><button onclick="send('stop')">Freeze</button>
<p><label><input type="checkbox" id="lease">Keep heartbeat (500 ms watchdog)</label></p>
<button onclick="send('arm run')">Arm calibrated robot</button>
<button onclick="send('motion rest')">Rest</button><button onclick="send('motion stand')">Stand</button>
<button onclick="send('motion wave')">Wave</button><button onclick="send('motion dance')">Dance</button>
<button onclick="send('show')">Calibration</button><button onclick="send('status')">Status</button>
<pre id="log"></pre><script>
let busy=false; const log=document.querySelector('#log'), lease=document.querySelector('#lease');
async function request(c){let r=await fetch('/cmd?c='+encodeURIComponent(c),{signal:AbortSignal.timeout(350)});return await r.text()}
async function send(c){c=c||document.querySelector('#cmd').value;
if(c==='off')lease.checked=false;
try{log.textContent=(await request(c))+'\n'+log.textContent.slice(0,3000)}catch(e){lease.checked=false;log.textContent='Disconnected: watchdog releases outputs\n'+log.textContent}}
setInterval(async()=>{if(!lease.checked||busy||document.hidden)return;busy=true;try{await request('heartbeat')}catch(e){lease.checked=false}finally{busy=false}},100);
document.addEventListener('visibilitychange',()=>{if(document.hidden){lease.checked=false;send('off')}});
</script>)HTML";
