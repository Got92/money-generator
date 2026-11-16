// Small document cache above the durable SQLite cache exposed by the server.
const histories=new Map(),fx=new Map(),pending=new Map();
const DAY=86400000,RETRY=300000;

async function load(cache,key,url,refresh){
 const old=cache.get(key);
 if(!refresh&&old&&old.expires>Date.now())return old.rows;
 const requestKey=url+(refresh?'&refresh=1':'');
 if(pending.has(requestKey))return pending.get(requestKey);
 const request=(async()=>{
  try{
   const response=await fetch(requestKey,{cache:'no-store'}),body=await response.json();
   if(!response.ok)throw Error(body.error||'Données indisponibles.');
   const info=body.cache||{},expires=info.status==='stale'?Date.now()+RETRY:Date.parse(info.expiresAt)||Date.now()+DAY;
   cache.set(key,{rows:body.data,info,expires});
   return body.data;
  }catch(error){
   if(!old)throw error;
   // A server/network failure must not erase the last usable observations.
   cache.set(key,{...old,expires:Date.now()+RETRY,info:{...old.info,status:'stale',warning:error.message}});
   return old.rows;
  }
 })();
 pending.set(requestKey,request);
 try{return await request}finally{pending.delete(requestKey)}
}

export async function loadHistory(symbol,refresh=false){symbol=symbol.toUpperCase();return load(histories,symbol,'/api/market/history?symbol='+encodeURIComponent(symbol),refresh)}
export async function loadFx(currency,refresh=false){if(currency==='EUR')return [];return load(fx,currency,'/api/market/fx?from='+encodeURIComponent(currency)+'&to=EUR',refresh)}
export function sessionRates(){return [...fx.values()].flatMap(entry=>entry.rows)}

export function cacheSummary(symbols=[],currencies=[]){
 return [...symbols.map(s=>[s,histories.get(s.toUpperCase())]),...currencies.filter(c=>c!=='EUR').map(c=>[c+'/EUR',fx.get(c)])].map(([name,entry])=>{
  if(!entry)return name+' : historique indisponible.';
  const c=entry.info,coverage=c.firstDate?`${c.firstDate} → ${c.lastDate} (${c.observations} observations)`:'couverture non communiquée';
  return `${name} : ${(c.sources||[]).join(', ')||'source non communiquée'} · ${coverage} · récupéré le ${c.lastSuccessAt||'date inconnue'}${c.status==='stale'?' · fraîcheur non confirmée':''}${c.warning?' · '+c.warning:''}${c.missingWeekdaysCount?' · '+c.missingWeekdaysCount+' jours ouvrés sans observation (jours fériés possibles)':''}.`;
 }).join(' ');
}
