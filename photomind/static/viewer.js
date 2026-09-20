"use strict";
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const params=new URLSearchParams(location.search);
let L={},LF={},lang='ru';
let photoId=Number(params.get('photo'));
let tab=params.get('tab')||'info';
let contextType=params.get('ctx')||'single';
let contextIds=(params.get('ids')||'').split(',').map(Number).filter(Number.isFinite);
let imageToken=0,sideToken=0,toastTimer=null,viewerDiag={};
let lastDetections=[],pinnedDetection=null;

async function api(url,opt={}){const r=await fetch(url,opt);if(!r.ok){let m=`${r.status} ${r.statusText}`;try{const body=await r.json(),d=body.detail;if(d&&typeof d==='object'&&d.code)m=t(d.code)+(d.detail?`: ${d.detail}`:'');else if(typeof d==='string')m=d}catch{}throw new Error(m)}const ct=r.headers.get('content-type')||'';return ct.includes('json')?r.json():r}
function esc(s=''){return String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function t(k,v={}){let s=L[k]||LF[k];if(s==null){console.warn('Missing locale key',k);s='—'}for(const [a,b] of Object.entries(v))s=s.replaceAll(`{${a}}`,String(b));return s}
function fmtBytes(n){n=Number(n||0);for(const u of ['B','KB','MB','GB','TB']){if(n<1024||u==='TB')return `${n<10&&u!=='B'?n.toFixed(1):Math.round(n)} ${u}`;n/=1024}}
function currentLang(){const v=localStorage.getItem('eidolarch.language')||'auto';return v==='auto'?((navigator.language||'en').toLowerCase().startsWith('ru')?'ru':'en'):v}
function applyTheme(){const v=localStorage.getItem('eidolarch.theme')||'system',theme=v==='system'?(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'):v;document.documentElement.dataset.theme=theme}
function infoRow(k,v){return `<div class="photo-info-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`}
function toast(html,ms=5000){const e=$('#toast');clearTimeout(toastTimer);e.innerHTML=html;e.classList.remove('hidden');toastTimer=setTimeout(()=>e.classList.add('hidden'),ms)}
function setTooltip(el,text,rich=false){if(!el)return;el.removeAttribute('title');if(text){el.dataset.tooltip=String(text);if(rich)el.dataset.tooltipRich='1';else delete el.dataset.tooltipRich}}
let tooltipTimer=null,tooltipAnchor=null;
function hideUiTooltip(){clearTimeout(tooltipTimer);tooltipTimer=null;tooltipAnchor=null;$('#uiTooltip')?.classList.add('hidden')}
function showUiTooltip(el){const text=el?.dataset?.tooltip,tip=$('#uiTooltip');if(!text||!tip)return;tooltipAnchor=el;tip.textContent=text;tip.classList.toggle('rich',el.dataset.tooltipRich==='1');tip.classList.remove('hidden');requestAnimationFrame(()=>{if(tooltipAnchor!==el)return;const r=el.getBoundingClientRect(),tr=tip.getBoundingClientRect(),gap=8;tip.style.left=Math.min(innerWidth-tr.width-8,Math.max(8,r.left+(r.width-tr.width)/2))+'px';let top=r.bottom+gap;if(top+tr.height>innerHeight-8)top=Math.max(8,r.top-tr.height-gap);tip.style.top=top+'px'})}
function installTooltipSystem(){const promote=el=>{if(!(el instanceof Element))return;if(el.hasAttribute('title')){const v=el.getAttribute('title');el.removeAttribute('title');if(v&&!el.dataset.tooltip)el.dataset.tooltip=v}for(const n of el.querySelectorAll?.('[title]')||[]){const v=n.getAttribute('title');n.removeAttribute('title');if(v&&!n.dataset.tooltip)n.dataset.tooltip=v}};promote(document.documentElement);new MutationObserver(ms=>{for(const m of ms){if(m.type==='childList'){for(const n of m.addedNodes)if(n.nodeType===1)promote(n)}else if(m.type==='attributes')promote(m.target)}}).observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['title']});document.addEventListener('pointerover',e=>{const el=e.target.closest?.('[data-tooltip]');if(el){clearTimeout(tooltipTimer);tooltipTimer=setTimeout(()=>showUiTooltip(el),420)}});document.addEventListener('pointerout',e=>{const el=e.target.closest?.('[data-tooltip]');if(el&&!el.contains(e.relatedTarget))hideUiTooltip()});document.addEventListener('focusin',e=>{const el=e.target.closest?.('[data-tooltip]');if(el)showUiTooltip(el)});document.addEventListener('focusout',hideUiTooltip);addEventListener('scroll',hideUiTooltip,{passive:true});addEventListener('resize',hideUiTooltip)}

async function loadLocale(){
  lang=currentLang();
  try{LF=await api('/api/locales/en.json');L=lang==='en'?LF:await api(`/api/locales/${lang}.json`)}catch(e){console.warn('Locale load failed',e);L=LF||{}}
  document.documentElement.lang=lang;
  const map={info:'viewer.info',objects:'viewer.objects',similar:'viewer.similar',duplicates:'viewer.duplicates'};
  for(const b of $$('.viewer-tab'))b.textContent=t(map[b.dataset.tab]);
  setTooltip($('#zoomOut'),t('viewer.zoomOut'));setTooltip($('#zoomIn'),t('viewer.zoomIn'));$('#actualSize').textContent=t('viewer.actual');$('#fitImage').textContent=t('viewer.fit');setTooltip($('#fullscreenBtn'),t('viewer.fullscreen'));setTooltip($('#toggleSide'),t(sideHidden?'viewer.showPanel':'viewer.hidePanel'));setTooltip($('#stage'),t('viewer.zoomHint'),true);
  if($('#copyViewerDiagnostics'))$('#copyViewerDiagnostics').textContent=t('viewer.copyDiagnostics');
}

async function loadPhoto(id,which=tab){
  const token=++imageToken;
  photoId=Number(id);tab=which||'info';pinnedDetection=null;lastDetections=[];clearDetectionHighlight(true);updateViewerNav();
  const img=$('#photo'),status=$('#imageStatus');
  img.removeAttribute('src');img.style.width='';img.style.height='';img.style.transform='';status?.classList.add('hidden');
  $('#side').innerHTML=`<div class="viewer-side-loading">${esc(t('gallery.loading'))}</div>`;
  const originalUrl=`/api/photos/${photoId}/original?v=2.2.13&rid=${token}`;
  viewerDiag={photo_id:photoId,stage:'loading-image',started_at:new Date().toISOString(),url:originalUrl,http:null,naturalWidth:0,naturalHeight:0,error:null};
  const infoPromise=api(`/api/photos/${photoId}/info`);
  try{
    await new Promise((resolve,reject)=>{
      const onLoad=()=>{cleanup();resolve()};const onError=()=>{cleanup();reject(new Error('Browser could not decode/load the original image'))};
      const cleanup=()=>{img.removeEventListener('load',onLoad);img.removeEventListener('error',onError)};
      img.addEventListener('load',onLoad,{once:true});img.addEventListener('error',onError,{once:true});img.src=originalUrl;
    });
    if(token!==imageToken)return;
    viewerDiag.stage='loaded';viewerDiag.naturalWidth=img.naturalWidth;viewerDiag.naturalHeight=img.naturalHeight;
    resetView();
    requestAnimationFrame(()=>{if(token!==imageToken)return;const r=img.getBoundingClientRect();viewerDiag.stage='rendered';viewerDiag.rect={x:r.x,y:r.y,width:r.width,height:r.height};viewerDiag.scale=currentScale()});
    try{const info=await infoPromise;if(token!==imageToken)return;viewerDiag.path=info.path;viewerDiag.size=info.size;viewerDiag.modified_at=info.modified_at;$('#caption').textContent=info.name;document.title=`${info.name} — Eidolarch`}catch(e){viewerDiag.info_error=e.message;$('#caption').textContent=`#${photoId}`;document.title=`#${photoId} — Eidolarch`}
    if(token===imageToken)await setTab(tab);
  }catch(e){
    if(token!==imageToken)return;viewerDiag.error=e.message;viewerDiag.stage='image-error';
    try{const probe=await fetch(originalUrl,{headers:{Range:'bytes=0-0'},cache:'no-store'});viewerDiag.http={ok:probe.ok,status:probe.status,type:probe.headers.get('content-type'),length:probe.headers.get('content-length'),contentRange:probe.headers.get('content-range')};await probe.body?.cancel?.()}catch(pe){viewerDiag.http={ok:false,error:pe.message}}
    $('#imageStatusTitle').textContent=t('viewer.imageLoadFailed');$('#imageStatusText').textContent=`${e.message} · HTTP ${viewerDiag.http?.status||viewerDiag.http?.error||'?'}`;status?.classList.remove('hidden');$('#caption').textContent='';
  }
}

function renderInfo(d){
  const e=d.exif||{},exp=[e.fnumber?`ƒ/${(+e.fnumber).toFixed(1)}`:'',e.exposure_time?`${e.exposure_time<1?'1/'+Math.round(1/e.exposure_time):e.exposure_time+'s'}`:'',e.iso?`ISO ${e.iso}`:'',e.focal_length?`${(+e.focal_length).toFixed(1)} mm`:''].filter(Boolean).join(' · ');
  return `<div class="photo-info">${infoRow(t('info.date'),d.taken_at||e.datetime_original||'—')}${infoRow(t('info.dimensions'),d.width&&d.height?`${d.width} × ${d.height}`:'—')}${infoRow(t('info.size'),fmtBytes(d.size))}${infoRow(t('info.format'),d.suffix||'—')}${infoRow(t('info.camera'),[e.make,e.model].filter(Boolean).join(' ')||'—')}${infoRow(t('info.lens'),e.lens||'—')}${infoRow(t('info.exposure'),exp||'—')}${infoRow(t('info.gps'),e.latitude!=null?`${e.latitude.toFixed(6)}, ${e.longitude.toFixed(6)}${e.altitude!=null?' · '+Math.round(e.altitude)+' m':''}`:'—')}<div class="info-block"><span>${t('info.path')}</span><code>${esc(d.path)}</code><div class="inline-actions"><button onclick="openFolder()">📂 ${esc(t('viewer.openFolder'))}</button><button onclick="openExternal()">↗ ${esc(t('viewer.openExternal'))}</button><button onclick="printPhoto()">🖨 ${esc(t('viewer.print'))}</button></div></div><div class="info-block"><span>${t('info.tags')}</span><div class="tag-list">${(d.tags||[]).map(x=>`<span>#${esc(x.name)}</span>`).join('')}</div></div></div>`;
}

async function setTab(which){
  tab=which;if(which!=='objects'){pinnedDetection=null;clearDetectionHighlight(true)}const token=++sideToken;for(const b of $$('.viewer-tab'))b.classList.toggle('active',b.dataset.tab===which);const box=$('#side');box.innerHTML=`<div class="viewer-side-loading">${esc(t('gallery.loading'))}</div>`;
  try{
    if(which==='info'){
      const d=await api(`/api/photos/${photoId}/info`);if(token!==sideToken)return;box.innerHTML=renderInfo(d);return;
    }
    if(which==='objects'){
      const d=await api(`/api/photos/${photoId}/detections`);if(token!==sideToken)return;lastDetections=d.items||[];
      const scan=d.scan||null;let empty='';if(!d.items.length){if(!scan)empty=t('objects.notIndexed');else if(scan.status==='error')empty=t('objects.scanFailed',{error:scan.error||'—'});else empty=t('objects.noneFound')}
      const scanMeta=scan?`<div class="small muted object-scan-meta">${esc(d.scan_key||'')} · ${esc(scan.updated_at||'')}</div>`:'';
      const controls=`<div class="object-controls"><button onclick="redetectAndSave()">↻ ${esc(t('objects.redetectSave'))}</button><button onclick="runDetectionDiagnostics()">${esc(t('objects.runDiagnostics'))}</button></div><div id="objectDiag" class="small muted"></div>`;
      const cards=d.items.length?`<div class="detections">${d.items.map(x=>`<div class="detection" data-detection-id="${x.id}" onmouseenter="highlightDetection(${x.id},false)" onmouseleave="clearDetectionHighlight(false)" onclick="highlightDetection(${x.id},true)"><img src="${x.crop}"><div><b>${esc(x.entity_name||t(x.kind_label_key||'entity.kind.unknown'))}</b><small>${Math.round(x.score*100)}%</small><div class="namebox"><input id="name-${x.id}" value="${esc(x.entity_name||'')}" onclick="event.stopPropagation()"><button onclick="event.stopPropagation();nameDetection(${x.id})">✓</button></div></div></div>`).join('')}</div>`:`<div class="viewer-side-empty object-empty">${empty}</div>`;
      box.innerHTML=`<p class="side-help">${esc(t('objects.help'))}</p>${scanMeta}${controls}${cards}`;return;
    }
    const ep=which==='similar'?'similar':'duplicates';const d=await api(`/api/photos/${photoId}/${ep}`);if(token!==sideToken)return;const items=d.items||[],ids=items.map(x=>x.id);
    let header='';
    if(which==='similar')header=`<div class="side-section-title">${esc(t('viewer.referencePhoto'))}</div><div class="viewer-reference"><img src="/api/photos/${photoId}/thumbnail?v=2.2.13"><span>${esc($('#caption').textContent||'#'+photoId)}</span></div><div class="side-section-title">${esc(t('viewer.similarResults'))}</div>`;
    else if(d.current)header=`<div class="side-section-title">${esc(t('viewer.currentFile'))}</div><div class="viewer-reference"><img src="${d.current.thumbnail}"><code>${esc(d.current.path||'')}</code></div><div class="side-section-title">${esc(t('viewer.duplicateResults'))}</div>`;
    const results=items.length?`<div class="viewer-results standalone-results">${items.map(x=>`<article class="viewer-result-card"><button class="viewer-result" onclick="openChildViewer(${x.id},'${which}',[${ids.join(',')}])"><img src="${x.thumbnail}"><span>${x.score!=null?(+x.score).toFixed(3):esc(x.match_type||'⧉')}</span></button>${which==='duplicates'?`<code title="${esc(x.path||'')}">${esc(x.path||'')}</code><div class="dupe-actions"><button onclick="openFolder(${x.id})">📂</button><button class="danger" onclick="trashDuplicate(${x.id})">⌫ ${esc(t('viewer.trash'))}</button></div>`:''}</article>`).join('')}</div>`:`<div class="viewer-side-empty">${esc(which==='similar'?t('viewer.noSimilar'):t('viewer.noDuplicates'))}</div>`;
    box.innerHTML=header+results;
  }catch(e){if(token===sideToken)box.innerHTML=`<div class="errorbox">${esc(e.message)}</div>`}
}

window.nameDetection=async id=>{const input=$(`#name-${id}`),name=input?.value.trim();if(!name)return;await api(`/api/detections/${id}/name`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,propagate:false})});toast(esc(t('message.saved')));await setTab('objects')};
window.openFolder=async(id=photoId)=>api(`/api/photos/${id}/open-folder`,{method:'POST'});window.openExternal=async(id=photoId)=>api(`/api/photos/${id}/open-external`,{method:'POST'});window.printPhoto=()=>{const w=open(`/api/photos/${photoId}/original`,'_blank');w?.addEventListener('load',()=>w.print())};
window.trashDuplicate=async id=>{if(!confirm(t('confirm.delete')))return;await api('/api/files/trash',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_ids:[id]})});toast(`${esc(t('message.trashed'))} <button onclick="openRecycle()">${esc(t('message.openRecycleBin'))}</button>`);setTab('duplicates')};window.openRecycle=()=>api('/api/system/recycle-bin',{method:'POST'});
window.redetectAndSave=async()=>{const el=$('#objectDiag');if(el)el.textContent=t('objects.redetectRunning');try{await api(`/api/photos/${photoId}/redetect`,{method:'POST'});toast(esc(t('objects.redetectDone')));await setTab('objects')}catch(e){if(el)el.textContent=t('objects.diagnosticsError',{error:e.message})}};
window.runDetectionDiagnostics=async()=>{const el=$('#objectDiag');if(el)el.textContent=t('objects.diagnosticsRunning');try{const d=await api(`/api/photos/${photoId}/detection-diagnostics`),targets=d.live?.target_predictions||[],counts=d.live?.counts||{},all=counts.raw_predictions??0;if(el)el.textContent=t('objects.diagnosticsResult',{targets:targets.length,total:all,device:d.live?.device||'?'})+` · ${counts.after_threshold??'?'} → ${counts.after_nms??'?'} → ${counts.final??'?'}`+(targets.length?` · ${targets.slice(0,5).map(x=>x.label+' '+Math.round(x.score*100)+'%').join(', ')}`:'')}catch(e){if(el)el.textContent=t('objects.diagnosticsError',{error:e.message})}};
window.openChildViewer=async(id,which,ids)=>{const q=`tab=${encodeURIComponent(which)}&ctx=${encodeURIComponent(which)}&ids=${encodeURIComponent((ids||[]).join(','))}`;try{await api(`/api/window/viewer/${id}?${q}`,{method:'POST'})}catch{open(`/viewer?photo=${id}&${q}&v=2.2.13`,'_blank','popup,width=1500,height=950')}};

window.highlightDetection=(id,pin=false)=>{const d=lastDetections.find(x=>x.id===Number(id));if(!d)return;if(pin)pinnedDetection=pinnedDetection===d.id?null:d.id;if(pin&&!pinnedDetection){clearDetectionHighlight(true);return}const img=$('#photo'),stage=$('#stage'),layer=$('#bboxLayer');if(!img.naturalWidth||!layer)return;const ir=img.getBoundingClientRect(),sr=stage.getBoundingClientRect(),sx=ir.width/img.naturalWidth,sy=ir.height/img.naturalHeight;layer.style.left=(ir.left-sr.left+d.x1*sx)+'px';layer.style.top=(ir.top-sr.top+d.y1*sy)+'px';layer.style.width=Math.max(2,(d.x2-d.x1)*sx)+'px';layer.style.height=Math.max(2,(d.y2-d.y1)*sy)+'px';$('#bboxLabel').textContent=`${d.entity_name||t(d.kind_label_key||'entity.kind.unknown')} ${Math.round(d.score*100)}%`;layer.classList.remove('hidden')};
window.clearDetectionHighlight=(force=false)=>{if(pinnedDetection&&!force){highlightDetection(pinnedDetection,false);return}$('#bboxLayer')?.classList.add('hidden')};

function viewerStep(dir){if(!contextIds.length)return;const i=contextIds.indexOf(Number(photoId)),n=i+dir;if(i<0||n<0||n>=contextIds.length)return;const next=contextIds[n];history.replaceState(null,'',`/viewer?photo=${next}&tab=${encodeURIComponent(tab)}&ctx=${encodeURIComponent(contextType)}&ids=${encodeURIComponent(contextIds.join(','))}&v=2.2.13`);loadPhoto(next,tab)}
function updateViewerNav(){const i=contextIds.indexOf(Number(photoId));$('#viewerPrevStandalone').disabled=!(i>0);$('#viewerNextStandalone').disabled=!(i>=0&&i<contextIds.length-1)}

let zoom=0,panX=0,panY=0,dragging=false,dragStart=null,sideHidden=matchMedia('(orientation: portrait)').matches;if(sideHidden)document.body.classList.add('viewer-side-hidden');
function naturalFitScale(){const img=$('#photo');if(!img.naturalWidth||!img.naturalHeight)return 1;const side=sideHidden?0:document.querySelector('.standalone-side').getBoundingClientRect().width,w=Math.max(1,innerWidth-side-24),h=Math.max(1,innerHeight-24);return Math.min(w/img.naturalWidth,h/img.naturalHeight,1)}
function currentScale(){return zoom===0?naturalFitScale():zoom}
function applyTransform(){const img=$('#photo');if(!img.naturalWidth||!img.naturalHeight)return;const z=currentScale();img.style.maxWidth='none';img.style.maxHeight='none';img.style.width=img.naturalWidth+'px';img.style.height=img.naturalHeight+'px';img.style.transform=`translate(${panX}px,${panY}px) scale(${z})`;$('#zoomValue').textContent=zoom===0?t('viewer.fit'):`${Math.round(z*100)}%`;$('#stage').classList.toggle('pannable',z>naturalFitScale()+.001);if(pinnedDetection)requestAnimationFrame(()=>highlightDetection(pinnedDetection,false))}
function resetView(){zoom=0;panX=0;panY=0;requestAnimationFrame(applyTransform)}
function setZoom(next,cx=innerWidth/2,cy=innerHeight/2){const old=currentScale(),n=Math.max(.1,Math.min(8,next));if(Math.abs(n-old)<1e-4)return;zoom=n;const rect=$('#stage').getBoundingClientRect(),x=cx-(rect.left+rect.width/2)-panX,y=cy-(rect.top+rect.height/2)-panY;panX-=x*(n/old-1);panY-=y*(n/old-1);applyTransform()}

$('#stage').addEventListener('wheel',e=>{e.preventDefault();setZoom(currentScale()*(e.deltaY<0?1.12:1/1.12),e.clientX,e.clientY)},{passive:false});
$('#stage').addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('.viewer-toolbar,.standalone-nav'))return;if(currentScale()<=naturalFitScale()+.001)return;dragging=true;dragStart={x:e.clientX,y:e.clientY,px:panX,py:panY};$('#stage').setPointerCapture(e.pointerId);$('#stage').classList.add('dragging')});
$('#stage').addEventListener('pointermove',e=>{if(!dragging)return;panX=dragStart.px+e.clientX-dragStart.x;panY=dragStart.py+e.clientY-dragStart.y;applyTransform()});
$('#stage').addEventListener('pointerup',e=>{dragging=false;$('#stage').classList.remove('dragging');try{$('#stage').releasePointerCapture(e.pointerId)}catch{}});
$('#zoomIn').onclick=()=>setZoom(currentScale()*1.25);$('#zoomOut').onclick=()=>setZoom(currentScale()/1.25);$('#actualSize').onclick=()=>{zoom=1;panX=panY=0;applyTransform()};$('#fitImage').onclick=resetView;
$('#toggleSide').onclick=()=>{sideHidden=!sideHidden;document.body.classList.toggle('viewer-side-hidden',sideHidden);setTooltip($('#toggleSide'),t(sideHidden?'viewer.showPanel':'viewer.hidePanel'));resetView()};$('#fullscreenBtn').onclick=async()=>{if(!document.fullscreenElement)await document.documentElement.requestFullscreen?.();else await document.exitFullscreen?.()};
$('#viewerPrevStandalone').onclick=()=>viewerStep(-1);$('#viewerNextStandalone').onclick=()=>viewerStep(1);addEventListener('resize',()=>{if(zoom===0)applyTransform()});
window.copyViewerDiagnostics=async()=>{const payload={...viewerDiag,context:{type:contextType,ids:contextIds,current:photoId},viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},sideHidden,zoom,panX,panY,userAgent:navigator.userAgent};try{await navigator.clipboard.writeText(JSON.stringify(payload,null,2));toast(esc(t('viewer.diagnosticsCopied')))}catch{console.log('Viewer diagnostics',payload)}};$('#copyViewerDiagnostics').onclick=window.copyViewerDiagnostics;
$$('.viewer-tab').forEach(b=>b.onclick=()=>{if(sideHidden&&matchMedia('(orientation: portrait)').matches){sideHidden=false;document.body.classList.remove('viewer-side-hidden');resetView()}setTab(b.dataset.tab)});
addEventListener('keydown',e=>{if(e.target.matches?.('input,textarea'))return;if(e.key==='0'){e.preventDefault();zoom=1;panX=panY=0;applyTransform()}else if(e.key.toLowerCase()==='f'){e.preventDefault();resetView()}else if(e.key==='Enter'){e.preventDefault();$('#fullscreenBtn').click()}else if(e.key==='ArrowLeft'){e.preventDefault();viewerStep(-1)}else if(e.key==='ArrowRight'){e.preventDefault();viewerStep(1)}else if(e.key==='Escape'){if(document.fullscreenElement)document.exitFullscreen?.();else close()}});

addEventListener('storage',async e=>{if(e.key==='eidolarch.language'){await loadLocale();await setTab(tab)}else if(e.key==='eidolarch.theme'){applyTheme()}});
(async()=>{installTooltipSystem();applyTheme();await loadLocale();await loadPhoto(photoId,tab);updateViewerNav()})();
