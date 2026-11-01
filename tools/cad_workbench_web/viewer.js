import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const $=s=>document.querySelector(s),canvas=$('canvas'),viewport=$('#viewport');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setClearColor('#edf2f7');
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(38,1,.05,10000);camera.up.set(0,0,1);
const controls=new OrbitControls(camera,canvas);controls.enableDamping=true;
scene.add(new THREE.HemisphereLight(0xffffff,0x63768c,2.5));
for(const [x,y,z,power] of [[100,-100,180,3],[-100,80,60,1.2]]){const l=new THREE.DirectionalLight(0xffffff,power);l.position.set(x,y,z);scene.add(l);}
let status=null,part='head',mode='current',loadedKey='',request=0,current=null,previous=null,renderedPart=null;
const views=new Map();
const readView=()=>({position:camera.position.toArray(),target:controls.target.toArray()});
function saveView(){if(renderedPart)views.set(renderedPart,readView());}
function restoreView(view){camera.position.fromArray(view.position);controls.target.fromArray(view.target);controls.update();}
function fit(){if(!current)return;const box=new THREE.Box3().setFromObject(current),center=box.getCenter(new THREE.Vector3()),radius=box.getSize(new THREE.Vector3()).length()/2;
  const distance=radius/Math.sin(THREE.MathUtils.degToRad(camera.fov/2))*Math.max(1,1/camera.aspect)*1.13;
  controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(1,-1.3,.9).normalize().multiplyScalar(distance));controls.update();saveView();}
controls.addEventListener('change',saveView);
function resize(){const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(viewport);resize();
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});

async function geometry(url){
  const response=await fetch('./'+url);if(!response.ok)throw Error(`Mesh request failed: ${response.status}`);
  const raw=await response.arrayBuffer(),data=new DataView(raw);if(raw.byteLength<84)throw Error('Incomplete STL');
  const count=data.getUint32(80,true);if(raw.byteLength!==84+50*count)throw Error('Invalid STL length');
  const positions=new Float32Array(count*9),normals=new Float32Array(count*9);
  for(let i=0;i<count;i++)for(let vertex=0;vertex<3;vertex++)for(let axis=0;axis<3;axis++){
    positions[i*9+vertex*3+axis]=data.getFloat32(84+i*50+12+vertex*12+axis*4,true);
    normals[i*9+vertex*3+axis]=data.getFloat32(84+i*50+axis*4,true);
  }
  const result=new THREE.BufferGeometry();result.setAttribute('position',new THREE.BufferAttribute(positions,3));result.setAttribute('normal',new THREE.BufferAttribute(normals,3));return result;
}
function object(mesh,old){
  const group=new THREE.Group();group.add(new THREE.Mesh(mesh,new THREE.MeshStandardMaterial({color:old?0xbd597e:0x8ab1cb,roughness:.65,metalness:.05,side:THREE.DoubleSide,polygonOffset:old,polygonOffsetFactor:old?-1:0,polygonOffsetUnits:old?-1:0})));
  group.add(new THREE.LineSegments(new THREE.EdgesGeometry(mesh,25),new THREE.LineBasicMaterial({color:old?0x963958:0x30495c,transparent:true,opacity:old ? 0.55 : 0.6})));return group;
}
function dispose(group){if(!group)return;scene.remove(group);group.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});}
function applyMode(){
  if(current)current.visible=mode!=='previous';if(previous){previous.visible=mode!=='current';const material=previous.children[0].material;
    material.transparent=mode==='overlay';material.opacity=mode==='overlay' ? 0.22 : 1;material.depthWrite=mode!=='overlay';material.needsUpdate=true;}
  document.querySelectorAll('[data-mode]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.mode===mode));b.disabled=b.dataset.mode!=='current'&&!previous;});
  $('.after').hidden=mode==='previous';$('.before').hidden=mode==='current'||!previous;
  const record=status?.parts?.[part],selected=mode==='previous'?record?.previous:record?.current;
  if(selected){$('#version').textContent=`${mode==='previous'?'Previous':'Current'} · ${new Date(selected.built_at*1000).toLocaleTimeString()} · ${selected.seconds.toFixed(2)}s build`;
    const p=selected.parameters,size=selected.bounds_mm[0].map((v,i)=>(selected.bounds_mm[1][i]-v).toFixed(2)).join(' × ');
    const dimensions=part==='head'?`Notch ${p.head_cover.cable_notch_width_mm} mm · lift ${p.head_cover.raise_mm} mm`:part==='frame'?`Pilot Ø${p.pcb_pilot_diameter_mm} mm · depth ${p.pcb_pilot_depth_mm} mm`:`Height ${p.pcb_standoff_height_mm} mm · bore Ø${p.pcb_spacer_bore_mm} mm`;
    $('#summary').textContent=`${dimensions} · ${size} mm. Drag to orbit; pinch to zoom.`;
    $('#download').hidden=false;$('#download').href='./'+selected.step;$('#download').download=part+'.step';}
}
async function sync(){
  const record=status?.parts?.[part];if(!record?.current){if(current)current.visible=false;if(previous)previous.visible=false;$('#download').hidden=true;$('#empty').hidden=false;$('#empty').textContent=`Waiting for ${part} preview…`;return;}
  const key=part+record.current.mesh+(record.previous?.mesh||'');if(key===loadedKey){applyMode();return;}
  const sequence=++request,kind=part;
  try{
    const [a,b]=await Promise.all([geometry(record.current.mesh),record.previous?geometry(record.previous.mesh):null]);
    if(sequence!==request||part!==kind){a.dispose();b?.dispose();return;}
    saveView();dispose(current);dispose(previous);current=object(a,false);previous=b?object(b,true):null;scene.add(current);if(previous)scene.add(previous);
    const changedPart=renderedPart!==kind;renderedPart=kind;loadedKey=key;
    if(changedPart){if(views.has(kind))restoreView(views.get(kind));else fit();}
    if(!previous)mode='current';$('#empty').hidden=true;applyMode();
  }catch(error){$('#error').hidden=false;$('#error').textContent='Preview loading failed: '+error.message;}
}
$('#part').addEventListener('change',()=>{saveView();part=$('#part').value;++request;sync();});
document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;applyMode();}));
$('#fit').addEventListener('click',fit);
async function poll(){try{const response=await fetch('./status.json',{cache:'no-store'});if(!response.ok)throw Error('status '+response.status);status=await response.json();
  $('#buildState').textContent=status.message;$('#error').hidden=!status.error;$('#error').textContent=status.error||'';await sync();
}catch(error){$('#buildState').textContent='Connection unavailable — showing last loaded geometry';}finally{setTimeout(poll,800);}}
poll();
window.__cadWorkbench={snapshot:()=>({part,mode,view:readView(),loadedKey,currentVisible:current?.visible,previousVisible:previous?.visible,status})};
