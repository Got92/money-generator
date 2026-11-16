const EPS=1e-9;
function numeric(value){const n=Number(value);return Number.isFinite(n)?n:NaN}
function validDate(s){if(!/^\d{4}-\d{2}-\d{2}$/.test(s||''))return false;const d=new Date(s+'T00:00:00Z');return !Number.isNaN(d.valueOf())&&d.toISOString().slice(0,10)===s}
// Rates are units of portfolio currency per unit of transaction currency, dated on or before the flow.
export function fxObservation(rates, currency='EUR', base='EUR', date='9999-12-31', maxAgeDays=Infinity){
 if(currency===base)return null;
 const matches=(rates||[]).filter(r=>r.from===currency&&r.to===base&&r.date<=date&&Number.isFinite(Number(r.rate))&&Number(r.rate)>0).sort((a,b)=>b.date.localeCompare(a.date));
 return matches.length&&(Date.parse(date)-Date.parse(matches[0].date))/86400000<=maxAgeDays?matches[0]:null;
}
export function fxRate(rates, currency='EUR', base='EUR', date='9999-12-31', maxAgeDays=Infinity){
 if(currency===base)return 1;
 const observation=fxObservation(rates,currency,base,date,maxAgeDays);
 return observation?Number(observation.rate):null;
}
export function positions(transactions, portfolioId, quotes, includeClosed=false, rates=[], base='EUR') {
 const map = new Map();
 for (const t of transactions.filter(x => x.portfolioId === portfolioId).sort((a,b)=>a.date.localeCompare(b.date))) {
  if (!['buy','sell'].includes(t.type)) continue;
  const p=map.get(t.ticker)||{ticker:t.ticker, quantity:0, cost:0, realized:0};
  const q=numeric(t.quantity), price=numeric(t.price), fee=numeric(t.fee||0), rate=fxRate(rates,t.currency||base,base,t.date);
  if(!Number.isFinite(q)||!Number.isFinite(price)||!Number.isFinite(fee)||q<=0||price<=0||fee<0) throw Error(`Transaction invalide : ${t.ticker}`);
  if(t.type==='buy'){p.quantity+=q;p.cost=p.cost===null||rate===null?null:p.cost+(q*price+fee)*rate} else {if(q>p.quantity+EPS) throw Error(`Vente supérieure à la position : ${t.ticker}`); const basis=p.cost===null?null:(p.quantity ? p.cost*q/p.quantity : 0); p.realized=p.realized===null||basis===null||rate===null?null:p.realized+(q*price-fee)*rate-basis;p.quantity-=q;p.cost=basis===null?null:p.cost-basis;if(Math.abs(p.quantity)<EPS){p.quantity=0;p.cost=0}}
  map.set(t.ticker,p);
 }
 return [...map.values()].filter(p=>includeClosed||p.quantity>EPS).map(p=>{const quote=quotes[p.ticker];const rate=quote?fxRate(rates,quote.currency||base,base,quote.priceDate||'9999-12-31'):null;const value=quote && Number.isFinite(quote.price)&&rate!==null ? p.quantity*quote.price*rate : null;return {...p,average:p.quantity&&p.cost!==null?p.cost/p.quantity:null,quote,value,unrealized:value===null||p.cost===null?null:value-p.cost}});
}
export function cashBalance(transactions, id, rates=[], base='EUR', maxAgeDays=Infinity){return transactions.filter(t=>t.portfolioId===id).reduce((a,t)=>{let q=numeric(t.quantity||0),p=numeric(t.price||0),f=numeric(t.fee||0),v=numeric(t.amount||0),rate=fxRate(rates,t.currency||base,base,t.date,maxAgeDays);return a===null||rate===null?null:a+({deposit:v,withdrawal:-v,dividend:v,buy:-q*p-f,sell:q*p-f}[t.type]||0)*rate},0)}
function validateTransactionFields(t){if(!validDate(t.date)||!t.portfolioId) throw Error('Date valide et portefeuille requis.');if(t.currency&&!/^[A-Z]{3}$/.test(t.currency))throw Error('Devise invalide (code ISO à trois lettres requis).');if(!['buy','sell','deposit','withdrawal','dividend','exchange'].includes(t.type)) throw Error('Type invalide.');if(['buy','sell'].includes(t.type)){if(!t.ticker||!Number.isFinite(numeric(t.quantity))||!(numeric(t.quantity)>0)||!Number.isFinite(numeric(t.price))||!(numeric(t.price)>0)||!Number.isFinite(numeric(t.fee||0))||numeric(t.fee||0)<0) throw Error('Ticker, quantité, prix et frais valides requis.');}else if(t.type==='exchange'){if(!t.currency||!/^[A-Z]{3}$/.test(t.targetCurrency||'')||t.currency===t.targetCurrency||!Number.isFinite(numeric(t.amount))||numeric(t.amount)<=0||!Number.isFinite(numeric(t.targetAmount))||numeric(t.targetAmount)<=0)throw Error('Devises distinctes et montants positifs requis pour le change.')}else if(!Number.isFinite(numeric(t.amount))||!(numeric(t.amount)>0)) throw Error('Montant positif requis.');}
export function validateTransaction(t, transactions){validateTransactionFields(t);positions([...transactions,t],t.portfolioId,{});}
export function validateTransactions(transactions){for(const t of transactions)validateTransactionFields(t);for(const id of new Set(transactions.map(t=>t.portfolioId)))positions(transactions,id,{});}
// In multi-currency accounts each trade settles in its transaction currency.
export function cashBalances(transactions,id){const balances={};for(const t of transactions.filter(t=>t.portfolioId===id)){const c=t.currency||'EUR',q=Number(t.quantity||0),p=Number(t.price||0),f=Number(t.fee||0),a=Number(t.amount||0);balances[c]=(balances[c]||0)+({deposit:a,withdrawal:-a,dividend:a,buy:-q*p-f,sell:q*p-f,exchange:-a}[t.type]||0);if(t.type==='exchange')balances[t.targetCurrency]=(balances[t.targetCurrency]||0)+Number(t.targetAmount)}return balances}
export function cashValue(balances,rates,date){let total=0;for(const [currency,amount] of Object.entries(balances)){if(Math.abs(amount)<1e-9)continue;const r=fxRate(rates,currency,'EUR',date);if(r===null)return null;total+=amount*r}return total}
