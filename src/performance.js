import {localToday} from './calendar.js';
import {cashBalances,validateTransactions} from './finance.js';
import {xirrResult} from './xirr.js';
export {xirr} from './xirr.js';
export {selectPeriod,periodPerformance} from './performance-periods.js';
const DAY=86400000,EPS=1e-9;
const time=d=>Date.parse(d+'T00:00:00Z');
function validDate(day){return typeof day==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(day)&&Number.isFinite(time(day))&&new Date(time(day)).toISOString().slice(0,10)===day}
function indexBy(rows,key,field,allowZero=false){
 const map=new Map();
 for(const row of rows){
  if(!validDate(row.date)||typeof row[field]!=='number'||!Number.isFinite(row[field])||(allowZero?row[field]<0:row[field]<=0))continue;
  const k=key(row);if(!map.has(k))map.set(k,[]);map.get(k).push(row);
 }
 for(const values of map.values())values.sort((a,b)=>a.date.localeCompare(b.date));
 return map;
}
function asOf(rows,date){
 if(!rows)return null;
 let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m].date<=date)lo=m+1;else hi=m}
 const row=rows[lo-1];return row&&time(date)-time(row.date)<=7*DAY?row:null;
}
function dailyFactor(previous,value,external){
 if(value===null)return {factor:null,reason:'Cours ou taux de change manquant pour valoriser cette date.'};
 if(external===null)return {factor:null,reason:'Conversion en EUR d’un apport ou retrait indisponible.'};
 if(previous===null)return {factor:null,reason:'Valorisation de la veille indisponible.'};
 if(previous<-EPS||value<-EPS)return {factor:null,reason:'Valeur nette négative : rendement non calculable par cette méthode.'};
 if(previous>EPS){
  const numerator=value-external;
  return numerator>=-EPS?{factor:Math.max(0,numerator)/previous,reason:null}:{factor:null,reason:'Capital avant flux externe négatif.'};
 }
 if(external>EPS)return {factor:Math.max(0,value)/external,reason:null};
 if(Math.abs(value)<=EPS&&Math.abs(external)<=EPS)return {factor:1,reason:null};
 return {factor:null,reason:'Absence de capital initial positif ou de financement identifiable.'};
}
// Daily closing values. Net deposits/withdrawals are assumed at end of day;
// initial/restarted funding includes that day's costs and price variation.
export function performanceSeries(transactions,portfolioId,prices,rates,endDate=localToday(),cashMode='converted'){
 if(!validDate(endDate)||!['converted','multi'].includes(cashMode))throw Error('Date ou mode de trésorerie invalide.');
 const portfolioTx=transactions.filter(t=>t.portfolioId===portfolioId);
 validateTransactions(portfolioTx);
 if(cashMode!=='multi'&&portfolioTx.some(t=>t.type==='exchange'))throw Error('Un change nécessite des soldes par devise.');
 const tx=portfolioTx.filter(t=>t.date<=endDate).slice().sort((a,b)=>a.date.localeCompare(b.date));
 if(!tx.length)return {points:[],xirr:null,xirrReason:'Aucune transaction dans la période.'};
 const indexed=indexBy(prices,r=>r.ticker,'price',true),fx=indexBy(rates,r=>r.from+'/'+r.to,'rate');
 const holdings=new Map(),flows=[],points=[],balances={};
 let cash=0,next=0,previous=0,index=100,chainKnown=true,funded=false,cashReason=null;
 for(let ms=time(tx[0].date);ms<=time(endDate);ms+=DAY){
  const date=new Date(ms).toISOString().slice(0,10),priceDates={},fxDates={};
  const rate=currency=>{
   if(currency==='EUR')return 1;
   const row=asOf(fx.get(currency+'/EUR'),date);
   if(row)fxDates[currency]=row.date;
   return row?.rate??null;
  };
  let external=0;
  while(next<tx.length&&tx[next].date===date){
   const t=tx[next++],currency=t.currency||'EUR';
   // Share cash settlement rules (including trade fees) with the transaction engine.
   for(const [c,movement] of Object.entries(cashBalances([t],portfolioId))){
    if(cashMode==='multi')balances[c]=(balances[c]||0)+movement;
    else if(Math.abs(movement)>EPS){
     const r=rate(c);
     if(r===null){cash=null;cashReason='Taux historique manquant pour une transaction en '+c+'.'}
     else if(cash!==null)cash+=movement*r;
    }
   }
   if(t.type==='buy'||t.type==='sell')holdings.set(t.ticker,(holdings.get(t.ticker)||0)+(t.type==='buy'?1:-1)*Number(t.quantity));
   if(t.type==='split')holdings.set(t.ticker,(holdings.get(t.ticker)||0)*Number(t.ratio));
   if(t.type==='adjustment')holdings.set(t.ticker,(holdings.get(t.ticker)||0)+Number(t.quantityDelta));
   if(t.type==='deposit'||t.type==='withdrawal'){
    const r=rate(currency),amount=r===null?null:Number(t.amount)*r*(t.type==='deposit'?1:-1);
    external=external===null||amount===null?null:external+amount;
    flows.push({date,amount:amount===null?null:-amount});
   }
  }
  let value=cashMode==='multi'?0:cash,valuationReason=cashMode==='multi'?null:cashReason;
  if(cashMode==='multi')for(const [currency,amount] of Object.entries(balances)){
   if(Math.abs(amount)<=EPS)continue;
   const r=rate(currency);
   if(r===null){value=null;valuationReason='Taux de change '+currency+'/EUR indisponible.';break}
   value+=amount*r;
  }
  if(value!==null)for(const [ticker,quantity] of holdings){
   if(Math.abs(quantity)<=EPS)continue;
   const quote=asOf(indexed.get(ticker),date);
   if(!quote||!quote.currency){value=null;valuationReason='Cours daté ou devise indisponible pour '+ticker+'.';break}
   priceDates[ticker]=quote.date;
   const r=rate(quote.currency);
   if(r===null){value=null;valuationReason='Taux de change '+quote.currency+'/EUR indisponible.';break}
   value+=quantity*quote.price*r;
  }
  if(value!==null&&!Number.isFinite(value)){value=null;valuationReason='Valorisation hors de la précision numérique disponible.'}
  const inception=!funded&&external>EPS;
  const daily=dailyFactor(previous,value,external);
  funded ||= external>EPS;
  if(funded){
   if(daily.factor===null)chainKnown=false;
   else if(chainKnown)index*=daily.factor;
  }else if(value!==0)chainKnown=false;
  points.push({date,value,externalFlow:external,returnFactor:daily.factor,inception,
   index:funded&&chainKnown&&Number.isFinite(index)?index:null,reason:valuationReason||daily.reason,
   priceDates,fxDates,carried:[...Object.values(priceDates),...Object.values(fxDates)].some(d=>d<date)});
  previous=value;
 }
 const final=points.at(-1),irr=final.value===null?{value:null,reason:'La valorisation finale est indisponible.'}:xirrResult([...flows,{date:final.date,amount:final.value}]);
 return {points,xirr:irr.value,xirrReason:irr.reason};
}
export function benchmarkSeries(points,prices,rates,symbol){
 const indexed=indexBy(prices,r=>r.ticker,'price',true),fx=indexBy(rates,r=>r.from+'/'+r.to,'rate');
 return points.map(point=>{
  const quote=asOf(indexed.get(symbol),point.date);
  const currency=typeof quote?.currency==='string'&&/^[A-Z]{3}$/.test(quote.currency)?quote.currency:null;
  const conversion=currency&&asOf(fx.get(currency+'/EUR'),point.date);
  const rate=currency==='EUR'?1:conversion?.rate??null;
  return {date:point.date,value:quote&&quote.price>0&&rate!==null?quote.price*rate:null};
 });
}
