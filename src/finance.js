const EPS=1e-9;
function numeric(value){const n=Number(value);return Number.isFinite(n)?n:NaN}
function validDate(s){if(!/^\d{4}-\d{2}-\d{2}$/.test(s||''))return false;const d=new Date(s+'T00:00:00Z');return !Number.isNaN(d.valueOf())&&d.toISOString().slice(0,10)===s}
export function positions(transactions, portfolioId, quotes, includeClosed=false) {
 const map = new Map();
 for (const t of transactions.filter(x => x.portfolioId === portfolioId).sort((a,b)=>a.date.localeCompare(b.date))) {
  if (!['buy','sell'].includes(t.type)) continue;
  const p=map.get(t.ticker)||{ticker:t.ticker, quantity:0, cost:0, realized:0};
  const q=numeric(t.quantity), price=numeric(t.price), fee=numeric(t.fee||0);
  if(!Number.isFinite(q)||!Number.isFinite(price)||!Number.isFinite(fee)||q<=0||price<=0||fee<0) throw Error(`Transaction invalide : ${t.ticker}`);
  if(t.type==='buy'){p.quantity+=q;p.cost+=q*price+fee} else {if(q>p.quantity+EPS) throw Error(`Vente supérieure à la position : ${t.ticker}`); const basis=p.quantity ? p.cost*q/p.quantity : 0; p.realized+=q*price-fee-basis;p.quantity-=q;p.cost-=basis;if(Math.abs(p.quantity)<EPS){p.quantity=0;p.cost=0}}
  map.set(t.ticker,p);
 }
 return [...map.values()].filter(p=>includeClosed||p.quantity>EPS).map(p=>{const quote=quotes[p.ticker];const value=quote && Number.isFinite(quote.price) ? p.quantity*quote.price : null;return {...p,average:p.quantity?p.cost/p.quantity:null,quote,value,unrealized:value===null?null:value-p.cost}});
}
export function cashBalance(transactions, id){return transactions.filter(t=>t.portfolioId===id).reduce((a,t)=>{let q=numeric(t.quantity||0),p=numeric(t.price||0),f=numeric(t.fee||0),v=numeric(t.amount||0);return a+({deposit:v,withdrawal:-v,dividend:v,buy:-q*p-f,sell:q*p-f}[t.type]||0)},0)}
export function validateTransaction(t, transactions){if(!validDate(t.date)||!t.portfolioId) throw Error('Date valide et portefeuille requis.');if(!['buy','sell','deposit','withdrawal','dividend'].includes(t.type)) throw Error('Type invalide.');if(['buy','sell'].includes(t.type)){if(!t.ticker||!Number.isFinite(numeric(t.quantity))||!(numeric(t.quantity)>0)||!Number.isFinite(numeric(t.price))||!(numeric(t.price)>0)||!Number.isFinite(numeric(t.fee||0))||numeric(t.fee||0)<0) throw Error('Ticker, quantité, prix et frais valides requis.');positions([...transactions,t],t.portfolioId,{});}else if(!Number.isFinite(numeric(t.amount))||!(numeric(t.amount)>0)) throw Error('Montant positif requis.');}
