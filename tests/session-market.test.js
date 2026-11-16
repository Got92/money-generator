import {test} from 'node:test';import assert from 'node:assert/strict';
test('le cache mémoire reste propre à chaque document et relit le serveur SQLite au nouvel onglet',async()=>{
 const original=globalThis.fetch;let calls=0;globalThis.fetch=async url=>({ok:true,json:async()=>({data:url.includes('/fx?')?[{from:'USD',to:'EUR',date:'2024-01-01',rate:.9}]:[{ticker:'IBM',date:'2024-01-01',price:100,currency:'USD'}]})});
 try {const a=await import('../src/session-market.js?tab=a'),b=await import('../src/session-market.js?tab=b');await a.loadHistory('IBM');await a.loadFx('USD');assert.equal(a.sessionRates().length,1);assert.equal(b.sessionRates().length,0);const saved=globalThis.fetch;globalThis.fetch=async(...args)=>{calls++;return saved(...args)};await a.loadHistory('IBM');assert.equal(calls,0);await b.loadHistory('IBM');assert.equal(calls,1)} finally {globalThis.fetch=original}
});

test('déduplique les demandes simultanées et transmet une actualisation explicite',async()=>{
 const original=globalThis.fetch;let calls=[];
 globalThis.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>({data:[{ticker:'IBM',date:'2024-01-01',price:100,currency:'USD'}]})}};
 try{
  const cache=await import('../src/session-market.js?dedup');
  await Promise.all([cache.loadHistory('ibm'),cache.loadHistory('IBM')]);
  assert.equal(calls.length,1);
  await cache.loadHistory('IBM',true);
  assert.match(calls[1],/refresh=1/);
 }finally{globalThis.fetch=original}
});

test('conserve les derniers taux et signale un échec réseau sans effacer les valeurs',async()=>{
 const original=globalThis.fetch;
 const rates=[{from:'USD',to:'EUR',date:'2024-01-01',rate:.9}];
 globalThis.fetch=async()=>({ok:true,json:async()=>({data:rates,cache:{sources:['Test hors ligne'],firstDate:'2024-01-01',lastDate:'2024-01-01',observations:1,lastSuccessAt:'2024-01-02'}})});
 try{
  const cache=await import('../src/session-market.js?fallback');
  await cache.loadFx('USD');
  globalThis.fetch=async()=>{throw Error('Réseau indisponible')};
  assert.deepEqual(await cache.loadFx('USD',true),rates);
  assert.deepEqual(cache.sessionRates(),rates);
  assert.match(cache.cacheSummary([],['USD']),/fraîcheur non confirmée.*Réseau indisponible/);
  assert.match(cache.cacheSummary([],['USD']),/Test hors ligne.*2024-01-01.*2024-01-02/);
 }finally{globalThis.fetch=original}
});

test('respecte l’expiration du serveur et relance la récupération après 24 heures',async()=>{
 const original=globalThis.fetch,clock=Date.now;let now=Date.parse('2024-01-02T12:00:00Z'),calls=0;
 Date.now=()=>now;
 globalThis.fetch=async()=>{calls++;return {ok:true,json:async()=>({data:[],cache:{status:'fresh',expiresAt:new Date(now+86400000).toISOString()}})}};
 try{
  const cache=await import('../src/session-market.js?expiry');
  await cache.loadHistory('IBM');await cache.loadHistory('IBM');assert.equal(calls,1);
  now+=86400001;await cache.loadHistory('IBM');assert.equal(calls,2);
 }finally{globalThis.fetch=original;Date.now=clock}
});

test('affiche la couverture et les lacunes signalées par le serveur, sans inventer de cours',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>({ok:true,json:async()=>({data:[],cache:{status:'stale',warning:'Quota atteint',sources:['Source test'],firstDate:'2024-01-01',lastDate:'2024-01-05',observations:3,missingWeekdaysCount:2}})});
 try{
  const cache=await import('../src/session-market.js?metadata');
  assert.deepEqual(await cache.loadHistory('IBM'),[]);
  const text=cache.cacheSummary(['IBM']);
  assert.match(text,/3 observations/);assert.match(text,/Quota atteint/);
  assert.match(text,/2 jours ouvrés sans observation \(jours fériés possibles\)/);
  assert.match(cache.cacheSummary(['OTHER']),/historique indisponible/);
 }finally{globalThis.fetch=original}
});

test('sans cache, une réponse indisponible reste une erreur',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>({ok:false,json:async()=>({error:'Indisponible'})});
 try{const cache=await import('../src/session-market.js?empty');await assert.rejects(cache.loadHistory('IBM'),/Indisponible/)}finally{globalThis.fetch=original}
});
