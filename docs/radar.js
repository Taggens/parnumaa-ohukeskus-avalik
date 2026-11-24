(() => {
 const section=document.getElementById('radar');
 const panel=document.getElementById('radar-cards');
 const points={'Pärnu linn':[58.3859,24.4971],'Pärnu rand':[58.3765,24.4845],'Häädemeeste':[58.0825,24.495],'Tõstamaa':[58.3339,23.9921],'Sindi':[58.399,24.655]};
 const clock=s=>new Intl.DateTimeFormat('et-EE',{timeZone:'Europe/Tallinn',hour:'2-digit',minute:'2-digit'}).format(s*1000);
 let map,layer,data,lastImage,loading=false,lastFetch=0,mapLoading=false,selectedFrame=null;
 function history(){
  const rows=Array.isArray(data?.history)?data.history:[];
  const valid=rows.filter(x=>x&&Number.isFinite(x.frame)&&typeof x.image==='string'&&x.image.length>0);
  if(valid.length)return valid.slice().sort((a,b)=>a.frame-b.frame);
  return Number.isFinite(data?.frame)&&typeof data?.image==='string'?[{frame:data.frame,image:data.image}]:[];
 }
 function renderHistory(){
  const frames=history(),slider=document.getElementById('radar-history');
  if(!frames.length){
   slider.disabled=true;slider.max='0';slider.value='0';
   document.getElementById('radar-history-time').textContent='Kaadrid puuduvad';
   document.getElementById('radar-history-note').textContent='Radari ajalugu ei ole kättesaadav.';
   return;
  }
  let index=frames.findIndex(x=>x.frame===selectedFrame);
  if(index<0){index=frames.length-1;selectedFrame=frames[index].frame;}
  slider.max=String(frames.length-1);slider.value=String(index);slider.disabled=frames.length<2;
  document.getElementById('radar-history-start').textContent=clock(frames[0].frame);
  document.getElementById('radar-history-end').textContent=clock(frames[frames.length-1].frame);
  document.getElementById('radar-history-time').textContent=clock(selectedFrame)+(index===frames.length-1?' · viimane kaader':' · ajalugu');
  document.getElementById('radar-history-note').textContent=frames.length<2
   ?'Ajalugu koguneb automaatselt järgnevate radarikaadritega.'
   :'Sirvi tegelikke KAIA radarikaadreid. Valitud kaader ei ole prognoos'+(index===frames.length-1?'.':' ega praeguse hetke mõõtmine.');
 }
 function drawMap(){
  if(!window.L||!section.classList.contains('active'))return;
  if(!map){
   map=L.map('radar-map',{scrollWheelZoom:false}).setView([58.32,24.36],8);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
   for(const [name,pos] of Object.entries(points))L.circleMarker(pos,{radius:5,color:'#173957',fillColor:'#fff',fillOpacity:1}).bindTooltip(name).addTo(map);
  }
  map.invalidateSize();
  const frames=history(),selected=frames.find(x=>x.frame===selectedFrame)||frames[frames.length-1];
  if(lastImage===selected?.frame)return;
  if(layer){layer.remove();layer=null;}
  lastImage=selected?.frame;
  if(selected?.image&&data?.bounds?.length===4){
   const [w,s,e,n]=data.bounds;
   layer=L.imageOverlay('data:image/png;base64,'+selected.image,[[s,w],[n,e]],{opacity:.82}).addTo(map);
  }
 }
 function activateMap(){
  if(window.L){drawMap();return;}
  if(mapLoading)return;
  mapLoading=true;
  const css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.append(css);
  const js=document.createElement('script');js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';js.onload=drawMap;
  js.onerror=()=>{mapLoading=false;document.getElementById('radar-map').textContent='Aluskaardi laadimine ebaõnnestus.';};document.head.append(js);
 }
 function render(){
  const now=Date.now()/1000,f=data?.frame,age=Math.floor((now-f)/60);
  const fresh=Number.isFinite(f)&&now-f>=-120&&now-f<=900;
  document.getElementById('radar-time').textContent=f?'KAIA radarikaader '+clock(f)+' · '+Math.max(0,age)+' min tagasi'+(fresh?'':' · aegunud või kinnitamata'):'Värske radarikaader puudub.';
  renderHistory();
  panel.replaceChildren();
  for(const name of Object.keys(points)){
   const t=data?.targets?.find(x=>x.name===name);
   const here=fresh&&(t?.status==='radarikaja kohal'||data?.observations?.some(x=>x.name===name&&x.echo_detected===true));
   let value='',detail='';
   if(here){value='Kell '+clock(f)+' oli läheduses radarikaja';detail='Kaja tuvastati umbes 6 km raadiuses.';}
   else if(fresh&&data.motion&&t?.status==='võimalik saabumine'&&t.eta_window_start_utc>=f&&t.eta_window_start_utc<=t.eta_from_frame_utc&&t.eta_from_frame_utc<=t.eta_window_end_utc&&t.eta_window_end_utc<=f+5400&&now<=t.eta_window_end_utc){
    value=now>=t.eta_window_start_utc?'Võimalik saabumine kuni '+clock(t.eta_window_end_utc):clock(t.eta_window_start_utc)+'–'+clock(t.eta_window_end_utc);
    detail='Radarikaja hinnanguline saabumisvahemik.';
   }else if(name==='Pärnu linn'){
    value='Saabumisaega ei saa hinnata';
    detail=!fresh?'Vajalik on kuni 15 minuti vanune radarikaader.':!data.motion?data.reason||'Liikumissuund on kinnitamata.':t?.eta_window_end_utc<now?'Eelmise hinnangu aeg on möödunud.':'Sajuala jõudmine Pärnu lähedale 90 minuti jooksul on kinnitamata.';
   }else continue;
   const card=document.createElement('article');card.className='panel';
   for(const [tag,txt] of [['h3',name],['strong',value],['p',detail]]){const el=document.createElement(tag);el.textContent=txt;card.append(el);}
   panel.append(card);
  }
  drawMap();
 }
 async function refresh(){
  if(!section.classList.contains('active')||document.hidden)return;
  activateMap();render();
  if(loading||Date.now()-lastFetch<30000)return;
  loading=true;lastFetch=Date.now();
  try{const r=await fetch('./data/radar.json',{cache:'no-store'});if(r.ok){const j=await r.json();if(Number.isFinite(j.frame))data=j;}}catch{}finally{loading=false;render();}
 }
 document.getElementById('radar-history').addEventListener('input',event=>{
  const frames=history(),index=Number(event.target.value);
  if(!frames[index])return;
  selectedFrame=frames[index].frame;
  renderHistory();drawMap();
 });
 new MutationObserver(refresh).observe(section,{attributes:true,attributeFilter:['class']});
 document.addEventListener('visibilitychange',refresh);
 document.getElementById('refresh').addEventListener('click',()=>{lastFetch=0;refresh();});
 setInterval(refresh,30000);refresh();
})();
