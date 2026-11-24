(() => {
 const section=document.getElementById('radar');
 const panel=document.getElementById('radar-cards');
 const points={'Pärnu linn':[58.3859,24.4971],'Pärnu rand':[58.3765,24.4845],'Häädemeeste':[58.0825,24.495],'Tõstamaa':[58.3339,23.9921],'Sindi':[58.399,24.655]};
 const clock=s=>new Intl.DateTimeFormat('et-EE',{timeZone:'Europe/Tallinn',hour:'2-digit',minute:'2-digit'}).format(s*1000);
 let map,layer,data,lastImage,loading=false,lastFetch=0,mapLoading=false;
 function drawMap(){
  if(!window.L||!section.classList.contains('active'))return;
  if(!map){
   map=L.map('radar-map',{scrollWheelZoom:false}).setView([58.32,24.36],8);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
   for(const [name,pos] of Object.entries(points))L.circleMarker(pos,{radius:5,color:'#173957',fillColor:'#fff',fillOpacity:1}).bindTooltip(name).addTo(map);
  }
  map.invalidateSize();
  if(lastImage===data?.frame)return;
  if(layer){layer.remove();layer=null;}
  lastImage=data?.frame;
  if(data?.image&&data.bounds?.length===4){
   const [w,s,e,n]=data.bounds;
   layer=L.imageOverlay('data:image/png;base64,'+data.image,[[s,w],[n,e]],{opacity:.82}).addTo(map);
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
  document.getElementById('radar-move').textContent=fresh&&data.motion?'Sajuala liikumine '+data.direction+' · umbes '+data.speed+' km/h':'';
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
 new MutationObserver(refresh).observe(section,{attributes:true,attributeFilter:['class']});
 document.addEventListener('visibilitychange',refresh);
 document.getElementById('refresh').addEventListener('click',()=>{lastFetch=0;refresh();});
 setInterval(refresh,30000);refresh();
})();
