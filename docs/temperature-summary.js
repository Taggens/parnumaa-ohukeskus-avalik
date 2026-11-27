function temperatureSummary(model,now=Date.now()/1000){
 const first=Math.floor(now/3600)*3600+3600;
 const hours=new Map();
 for(const h of model?.hours||[]){
  if(h && numeric(h.temp) && Number.isInteger(h.t) && h.t%3600===0 && h.t>=first && h.t<first+24*3600)hours.set(h.t,h);
 }
 const rows=[...hours.values()].sort((a,b)=>a.t-b.t);
 if(!rows.length)return 'Järgmise 24 tunni temperatuuriprognoos puudub.';
 const low=rows.reduce((a,b)=>a.temp<=b.temp?a:b), high=rows.reduce((a,b)=>a.temp>=b.temp?a:b);
 const period=rows.length===24?'Järgmised 24 tundi':'Osaline prognoos · '+rows.length+'/24 tundi · '+local(rows[0].t)+' – '+local(rows.at(-1).t);
 return period+' · '+modelNames[model.id]+' · madalaim '+temp(low.temp)+' ('+local(low.t)+'), kõrgeim '+temp(high.temp)+' ('+local(high.t)+').';
}
