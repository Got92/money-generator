import {positions,cashBalance,cashBalances} from './finance.js';
// Values are aligned by timestamp; no later quote is used for an earlier instant.
export function intradayPortfolio(transactions,id,series,rates,cashMode,sessionDate){
 const all=transactions.filter(t=>t.portfolioId===id);
 if(all.some(t=>t.date===sessionDate))throw Error('Une transaction a eu lieu pendant cette séance : son heure est nécessaire pour calculer la performance 1D.');
 const tx=all.filter(t=>t.date<sessionDate),held=positions(tx,id,{},false,rates);
 const balances=cashMode==='multi'?cashBalances(tx,id):null;
 const cash=balances?null:cashBalance(tx,id,rates,'EUR',7);
 if(!balances&&cash===null)throw Error('Taux historique manquant pour calculer les liquidités.');
 const instruments=held.map(p=>series[p.ticker]);
 if(instruments.some(s=>!s||s.sessionDate!==sessionDate))throw Error('Les séances intrajournalières des positions ne sont pas disponibles pour la même date.');
 const currencies=new Set([...instruments.map(s=>s.currency),...Object.entries(balances||{}).filter(([,v])=>Math.abs(v)>1e-9).map(([c])=>c)].filter(c=>c!=='EUR'));
 const rowsBySymbol=new Map(Object.entries(series).map(([symbol,s])=>[symbol,validPoints(s.points)]));
 const get=(symbol,t)=>asOf(rowsBySymbol.get(symbol)||[],t);
 const convert=(currency,t)=>{if(currency==='EUR')return 1;const value=get(currency+'EUR=X',t);return value>0?value:null};
 const timestamps=[...new Set(held.flatMap(p=>(rowsBySymbol.get(p.ticker)||[]).map(p=>p.timestamp)))].sort();
 if(!timestamps.length)for(const c of currencies)for(const p of rowsBySymbol.get(c+'EUR=X')||[])timestamps.push(p.timestamp);
 const result=[...new Set(timestamps)].sort().map(timestamp=>{const t=Date.parse(timestamp);let value=cash??0;
  for(const p of held){const price=get(p.ticker,t),fx=convert(series[p.ticker].currency,t);if(price===null||fx===null)return {timestamp,value:null};value+=p.quantity*price*fx}
  for(const [currency,amount] of Object.entries(balances||{})){if(Math.abs(amount)<1e-9)continue;const fx=convert(currency,t);if(fx===null)return {timestamp,value:null};value+=amount*fx}
  return {timestamp,value};
 });
 return result;
}
export function intradayBenchmark(points,series,symbol){
 const q=series[symbol];if(!q)return points.map(()=>null);
 const rows=new Map([symbol,q.currency+'EUR=X'].map(s=>[s,validPoints(series[s]?.points||[])]));
 const at=(s,t)=>asOf(rows.get(s)||[],t);
 return points.map(p=>{const t=Date.parse(p.timestamp),price=at(symbol,t),fx=q.currency==='EUR'?1:at(q.currency+'EUR=X',t);return price===null||!(fx>0)?null:price*fx});
}
function validPoints(rows){return (rows||[]).filter(p=>Number.isFinite(Date.parse(p.timestamp))&&typeof p.price==='number'&&Number.isFinite(p.price)&&p.price>=0).slice().sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp))}
function asOf(rows,t){let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(Date.parse(rows[m].timestamp)<=t)lo=m+1;else hi=m}const row=rows[lo-1];return row&&t-Date.parse(row.timestamp)<=30*60000?row.price:null}
