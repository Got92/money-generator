import {fxObservation} from './finance.js';

// The observations follow exactly the dates used by finance.js for the EUR valuations.
export function cashEntriesForAllocation({balances,cash,rates,transactions,portfolioId,today}) {
 if(balances) return Object.entries(balances).map(([currency,amount])=>{
  const observation=currency==='EUR'||Math.abs(amount)<1e-9?null:fxObservation(rates,currency,'EUR',today);
  return {currency,value:Math.abs(amount)<1e-9?0:currency==='EUR'?amount:observation?amount*Number(observation.rate):null,observations:observation?[observation]:[]};
 });
 const observations=transactions.filter(t=>t.portfolioId===portfolioId && t.currency && t.currency!=='EUR').map(t=>({currency:t.currency,date:t.date,observation:fxObservation(rates,t.currency,'EUR',t.date)}));
 return [{currency:'EUR',value:cash,converted:true,observations}];
}
