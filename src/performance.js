const DAY=86400000;
const time=d=>Date.parse(d+'T00:00:00Z');
function indexBy(rows,key){const map=new Map();for(const row of rows){const k=key(row);if(!map.has(k))map.set(k,[]);map.get(k).push(row)}for(const values of map.values())values.sort((a,b)=>a.date.localeCompare(b.date));return map}
function asOf(rows,date,maxAge=7){if(!rows)return null;let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m].date<=date)lo=m+1;else hi=m}const r=rows[lo-1];return r&&time(date)-time(r.date)<=maxAge*DAY?r:null}
export function xirr(flows){
 if(flows.length<2||!flows.some(f=>f.amount<0)||!flows.some(f=>f.amount>0))return null;
 const start=time(flows[0].date);if(flows.every(f=>time(f.date)===start))return null;
 const npv=x=>flows.reduce((s,f)=>s+f.amount*Math.exp(-x*(time(f.date)-start)/DAY/365),0);
 // Search log(1+r), and refuse ambiguous multiple roots.
 const roots=[];let a=-13.8,fa=npv(a);for(let b=a+.1;b<=14;b+=.1){const fb=npv(b);if(Number.isFinite(fa)&&Number.isFinite(fb)&&fa*fb<0){let l=a,h=b,fl=fa;for(let i=0;i<80;i++){const m=(l+h)/2,fm=npv(m);if(fl*fm<=0)h=m;else{l=m;fl=fm}}roots.push(Math.exp((l+h)/2)-1)}a=b;fa=fb}return roots.length===1&&Number.isFinite(roots[0])?roots[0]:null;
}
// Daily closing values; deposits/withdrawals are assumed to occur at the end of the day.
export function performanceSeries(transactions,portfolioId,prices,rates,endDate=new Date().toISOString().slice(0,10),cashMode='converted'){
 const tx=transactions.filter(t=>t.portfolioId===portfolioId&&t.date<=endDate).slice().sort((a,b)=>a.date.localeCompare(b.date));
 if(!tx.length)return {points:[],xirr:null};
 const indexed=indexBy(prices,r=>r.ticker), fx=indexBy(rates,r=>r.from+'/'+r.to), holdings=new Map(), flows=[];let cash=0, next=0, previous=null, index=100, broken=false;
 const rate=(currency,date)=>currency==='EUR'?1:Number(asOf(fx.get(currency+'/EUR'),date)?.rate)||null;
 const points=[], balances={};
 for(let ms=time(tx[0].date);ms<=time(endDate);ms+=DAY){const date=new Date(ms).toISOString().slice(0,10);let external=0,missing=false;
  while(next<tx.length&&tx[next].date===date){const t=tx[next++],r=rate(t.currency||'EUR',date);if(r===null){missing=true;broken=true;continue}const currency=t.currency||'EUR';const amount=Number(t.amount||0),q=Number(t.quantity||0),price=Number(t.price||0),fee=Number(t.fee||0);
   if(t.type==='deposit'||t.type==='withdrawal'){const sign=t.type==='deposit'?1:-1;const v=amount*r*sign;if(cashMode==='multi')balances[currency]=(balances[currency]||0)+amount*sign;else cash+=v;external+=v;flows.push({date,amount:-v})}
   else if(t.type==='dividend'){if(cashMode==='multi')balances[currency]=(balances[currency]||0)+amount;else cash+=amount*r;}
   else if(t.type==='buy'||t.type==='sell'){const sign=t.type==='buy'?1:-1;holdings.set(t.ticker,(holdings.get(t.ticker)||0)+sign*q);if(cashMode==='multi')balances[currency]=(balances[currency]||0)-sign*q*price-fee;else cash+=(-sign*q*price-fee)*r}
   else if(t.type==='exchange'&&cashMode==='multi'){balances[currency]=(balances[currency]||0)-amount;balances[t.targetCurrency]=(balances[t.targetCurrency]||0)+Number(t.targetAmount)}
  }
  let value=cash;if(cashMode==='multi')for(const [currency,amount] of Object.entries(balances)){if(Math.abs(amount)<1e-9)continue;const r=rate(currency,date);if(r===null){missing=true;break}value+=amount*r}for(const [ticker,q] of holdings){if(Math.abs(q)<1e-9)continue;const quote=asOf(indexed.get(ticker),date),r=quote&&rate(quote.currency,date);if(!quote||r===null){missing=true;break}value+=q*quote.price*r}
  if(missing||broken){points.push({date,value:null,index:null});previous=null;index=100;continue}
  if(previous===null){if(external>0){index=100*(value/external)}else if(value>0){index=100}else index=null}
  else if(previous>0&&index!==null)index*= (value-external)/previous;
  else index=null;
  points.push({date,value,index:Number.isFinite(index)?index:null});previous=value;
 }
 const last=points.at(-1);return {points,xirr:last?.value!==null&&!broken?xirr([...flows,{date:last.date,amount:last.value}]):null};
}
export function benchmarkSeries(points,prices,rates,symbol){const p=indexBy(prices,r=>r.ticker),fx=indexBy(rates,r=>r.from+'/'+r.to);return points.map(point=>{const q=asOf(p.get(symbol),point.date),r=q&&(q.currency==='EUR'?1:Number(asOf(fx.get(q.currency+'/EUR'),point.date)?.rate)||null);return {date:point.date,value:q&&r!==null?q.price*r:null}})}
export function selectPeriod(points,period){if(!points.length)return [];const end=time(points.at(-1).date);let start=period==='1D'?end-DAY:period==='1W'?end-7*DAY:period==='1M'?end-30*DAY:period==='YTD'?time(points.at(-1).date.slice(0,4)+'-01-01'):-Infinity;return points.filter(p=>time(p.date)>=start)}
