function installFeedbackMenu() {
  const anchor=document.querySelector('.nav-link[data-section="settings"]');
  const button=document.createElement('button');
  button.type='button';button.className='nav-link';button.dataset.section='feedback';
  button.textContent='✉ Tagasiside';anchor.before(button);
  const panel=document.createElement('section');
  panel.className='screen';panel.id='feedback';
  panel.innerHTML='<article class="panel"><h2>Tagasiside</h2><label>Leht <select></select></label> <label>Teema <select></select></label> <label>Järjestus <select><option>Uuemad enne</option><option>Vanemad enne</option></select></label> <button type="button">Värskenda</button><p role="status"></p><div></div></article>';
  document.querySelector('.screen').parentElement.append(panel);
  const [page,topic,order]=panel.querySelectorAll('select');
  const status=panel.querySelector('p'),list=panel.querySelector('article > div');
  let rows=[];
  function render(){
    list.replaceChildren();
    const matches=rows.filter(r=>(!page.value||r[1]===page.value)&&(!topic.value||r[2]===topic.value));
    matches.sort((a,b)=>(Date.parse(b[0])-Date.parse(a[0]))*(order.selectedIndex?-1:1));
    status.textContent=matches.length+' sõnumit';
    for(const [time,place,theme,message] of matches){
      const item=document.createElement('article'),title=document.createElement('strong'),body=document.createElement('p');
      title.textContent=[localTime(time,true),place,theme].join(' · ');
      body.textContent=message;body.style.whiteSpace='pre-wrap';body.style.overflowWrap='anywhere';
      item.append(title,body);list.append(item);
    }
  }
  async function refresh(){
    try{
      const data=await requestJSON('/api/feedback');
      if(!Array.isArray(data))throw Error();
      rows=data;
      for(const [select,idx] of [[page,1],[topic,2]]){
        const prev=select.value;
        select.replaceChildren(new Option('Kõik',''));
        for(const value of [...new Set(rows.map(row=>row[idx]))].sort())select.add(new Option(value,value));
        if([...select.options].some(o=>o.value===prev))select.value=prev;
      }
      render();
    }catch{status.textContent='Sõnumeid ei õnnestunud laadida. Kontrolli vastuvõtja seadistust.';}
  }
  for(const select of [page,topic,order])select.addEventListener('change',render);
  panel.querySelector('button').onclick=refresh;
  button.onclick=()=>{go('feedback');text('page-title','Tagasiside');refresh();};
}
