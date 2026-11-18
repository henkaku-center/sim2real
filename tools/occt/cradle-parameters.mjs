// Shared by the browser, API and CAD builder. Nominal dimensions, not measured fit.
export const DEFAULTS = Object.freeze({length:51,width:28,height:14,clearance:0.5,wall:2,base:2.4,railHeight:6,strapWidth:10});
const RANGES = {length:[40,130],width:[20,80],height:[8,50],clearance:[0.2,1.5],wall:[1.6,4],base:[2.2,5],railHeight:[3,12],strapWidth:[6,16]};
export const PRESETS = [
  {id:'reference',label:'Current pack · 51 × 28 × 14',params:{...DEFAULTS},source:'https://www.amazon.co.jp/dp/B0F3JB59B6',note:'Listing dimensions; not measured. Leads and connector excluded.'},
  {id:'anker',label:'Anker A1638 · 82 × 51 × 36',params:{...DEFAULTS,length:82,width:51,height:36},source:'https://www.ankerjapan.com/products/a1638',note:'Manufacturer nominal envelope, not a purchase decision. Port/button clearance and rounded casing fit unverified.'},
  {id:'gforce',label:'G-FORCE GFG019 · 96 × 47 × 19',params:{...DEFAULTS,length:96,width:47,height:19},source:'https://www.gforce-hobby.jp/products/GFG019.html',note:'Manufacturer nominal body envelope. Terminals, charge leads and insulation are not modelled.'},
];

export function parameters(input={}) {
  if (!input || typeof input!=='object' || Array.isArray(input)) throw Error('Parameters must be an object');
  for (const key of Object.keys(input)) if (!Object.hasOwn(RANGES,key)) throw Error(`Unknown parameter: ${key}`);
  const p={...DEFAULTS,...input};
  for (const [name,[lo,hi]] of Object.entries(RANGES))
    if (typeof p[name]!=='number' || !Number.isFinite(p[name]) || p[name]<lo || p[name]>hi)
      throw Error(`${name} must be a number between ${lo} and ${hi} mm`);
  if (p.railHeight>p.height) throw Error('Rails must not rise above the battery envelope');
  return p;
}
