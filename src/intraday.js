import {positions,cashBalance,cashBalances} from './finance.js';
// Values are aligned by timestamp; no later quote is used for an earlier instant.
export function intradayPortfolio(transactions,id,series,rates,cashMode,sessionDate){
 const all=transactions.filter(t=>t.portfolioId===id);
 if(all.some(t=>t.date===sessionDate))throw Error('Une transaction a eu lieu pendant cette séance : son heure est nécessaire pour calculer la performance 1D.');
 const tx=all.filter(t=>t.date<sessionDate),held=positions(tx,id,{},false,rates);
 const balances=cashMode==='multi'?cashBalances(tx,id):null;
 const cash=balances?null:cashBalance(tx,id,rates);
 if(!balances&&cash===null)throw Error('Taux historique manquant pour calculer les liquidités.');
 const instruments=held.map(p=>series[p.ticker]);
 if(instruments.some(s=>!s||s.sessionDate!==sessionDate))throw Error('Les séances intrajournalières des positions ne sont pas disponibles pour la même date.');
 const currencies=new Set([...instruments.map(s=>s.currency),...Object.keys(balances||{})].filter(c=>c!=='EUR'));
 const get=(symbol,t)=>{const rows=series[symbol]?.points||[];let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(Date.parse(rows[m].timestamp)<=t)lo=m+1;else hi=m}const row=rows[lo-1];return row&&t-Date.parse(row.timestamp)<=30*60000?row.price:null};
 const convert=(currency,t)=>currency==='EUR'?1:get(currency+'EUR=X',t);
 const timestamps=[...new Set(instruments.flatMap(s=>s.points.map(p=>p.timestamp)))].sort();
 if(!timestamps.length)for(const c of currencies)for(const p of series[c+'EUR=X']?.points||[])timestamps.push(p.timestamp);
 const result=[...new Set(timestamps)].sort().map(timestamp=>{const t=Date.parse(timestamp);let value=cash??0;
  for(const p of held){const price=get(p.ticker,t),fx=convert(series[p.ticker].currency,t);if(price===null||fx===null)return {timestamp,value:null};value+=p.quantity*price*fx}
  for(const [currency,amount] of Object.entries(balances||{})){if(Math.abs(amount)<1e-9)continue;const fx=convert(currency,t);if(fx===null)return {timestamp,value:null};value+=amount*fx}
  return {timestamp,value};
 });
 return result;
}
export function intradayBenchmark(points,series,symbol){
 const q=series[symbol];if(!q)return points.map(()=>null);
 function at(s,t){const rows=series[s]?.points||[];let result=null;for(const row of rows){const ts=Date.parse(row.timestamp);if(ts>t)break;if(t-ts<=30*60000)result=row.price}return result}
 return points.map(p=>{const t=Date.parse(p.timestamp),price=at(symbol,t),fx=q.currency==='EUR'?1:at(q.currency+'EUR=X',t);return price===null||fx===null?null:price*fx});
}
