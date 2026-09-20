"use strict";
const $=s=>document.querySelector(s);
let L={},LF={};
async function api(url){const r=await fetch(url);if(!r.ok)throw new Error(r.status+" "+r.statusText);return r.json()}
function currentLang(){const v=localStorage.getItem('eidolarch.language')||'auto';return v==='auto'?((navigator.language||'en').toLowerCase().startsWith('ru')?'ru':'en'):v}
function t(k){return L[k]||LF[k]||k}
function applyTheme(){const v=localStorage.getItem('eidolarch.theme')||'system',theme=v==='system'?(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'):v;document.documentElement.dataset.theme=theme}
async function loadLocale(){const lang=currentLang();LF=await api('/api/locales/en.json');L=lang==='en'?LF:await api('/api/locales/'+lang+'.json');document.documentElement.lang=lang;$('#graphTitle').textContent=t('graph.title');$('#graphHint').textContent=t('graph.hint')}
function draw(data){
 const box=$('#graphCanvas');box.innerHTML='';if(!data.nodes?.length){box.textContent='—';return}
 const w=Math.max(900,box.clientWidth||1200),h=Math.max(620,box.clientHeight||760),cx=w/2,cy=h/2;
 const nodes=data.nodes.map((n,i)=>({...n,x:cx+Math.cos(i*2.399)*Math.sqrt(i+1)*46,y:cy+Math.sin(i*2.399)*Math.sqrt(i+1)*36,vx:0,vy:0})),by=new Map(nodes.map(n=>[n.id,n]));
 for(let step=0;step<140;step++){
   for(const e of data.edges){const a=by.get(e.a),b=by.get(e.b);if(!a||!b)continue;let dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(20,Math.hypot(dx,dy)),target=72+125/(1+e.weight*.12),f=(dist-target)*.0008;dx/=dist;dy/=dist;a.vx+=dx*f;b.vx-=dx*f;a.vy+=dy*f;b.vy-=dy*f}
   for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j],dx=b.x-a.x,dy=b.y-a.y,d2=Math.max(350,dx*dx+dy*dy),f=16/d2;a.vx-=dx*f;b.vx+=dx*f;a.vy-=dy*f;b.vy+=dy*f}
   for(const n of nodes){n.vx+=(cx-n.x)*.00045;n.vy+=(cy-n.y)*.00045;n.vx*=.86;n.vy*=.86;n.x+=n.vx;n.y+=n.vy;n.x=Math.max(50,Math.min(w-50,n.x));n.y=Math.max(38,Math.min(h-38,n.y))}
 }
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('class','graph-svg');
 const edgeEls=[];
 for(const e of data.edges){const a=by.get(e.a),b=by.get(e.b);if(!a||!b)continue;const l=document.createElementNS(ns,'line');l.dataset.a=e.a;l.dataset.b=e.b;l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);l.setAttribute('stroke-width',Math.min(2.1,.45+.42*Math.log1p(e.weight)));l.setAttribute('class','graph-edge');svg.appendChild(l);edgeEls.push(l)}
 const max=Math.max(...nodes.map(n=>n.count)),nodeEls=[];
 const clear=()=>{for(const l of edgeEls)l.classList.remove('active','dim');for(const g of nodeEls)g.classList.remove('active','dim')};
 for(const n of nodes){const g=document.createElementNS(ns,'g');g.dataset.id=n.id;g.setAttribute('class','graph-node');g.setAttribute('transform',`translate(${n.x},${n.y})`);const c=document.createElementNS(ns,'circle');c.setAttribute('r',8+18*Math.sqrt(n.count/max));const tx=document.createElementNS(ns,'text');tx.setAttribute('y',-14);tx.setAttribute('text-anchor','middle');tx.textContent='#'+n.name;g.append(c,tx);
   g.addEventListener('mouseenter',()=>{for(const l of edgeEls){const hit=Number(l.dataset.a)===Number(n.id)||Number(l.dataset.b)===Number(n.id);l.classList.toggle('active',hit);l.classList.toggle('dim',!hit)}for(const other of nodeEls){const oid=Number(other.dataset.id),connected=oid===Number(n.id)||data.edges.some(e=>(e.a===n.id&&e.b===oid)||(e.b===n.id&&e.a===oid));other.classList.toggle('active',oid===Number(n.id));other.classList.toggle('dim',!connected)}});
   g.addEventListener('mouseleave',clear);
   g.addEventListener('click',()=>{localStorage.setItem('eidolarch.graphTag',JSON.stringify({id:n.id,name:n.name,ts:Date.now()}))});
   svg.appendChild(g);nodeEls.push(g)
 }
 box.appendChild(svg)
}
async function run(){applyTheme();await loadLocale();draw(await api('/api/graph'))}
addEventListener('storage',async e=>{if(e.key==='eidolarch.language'){await loadLocale()}else if(e.key==='eidolarch.theme'){applyTheme()}});
addEventListener('resize',()=>run().catch(()=>{}));
run().catch(e=>{$('#graphCanvas').textContent=e.message});
