export function positions(transactions, portfolioId, quotes) {
 const map = new Map();
 for (const t of transactions.filter(x => x.portfolioId === portfolioId).sort((a,b)=>a.date.localeCompare(b.date))) {
  if (!['buy','sell'].includes(t.type)) continue;
  const p=map.get(t.ticker)||{ticker:t.ticker, quantity:0, cost:0, realized:0};
  const q=Number(t.quantity), price=Number(t.price), fee=Number(t.fee||0);
  if(t.type==='buy'){p.quantity+=q;p.cost+=q*price+fee} else {if(q>p.quantity+1e-9) throw Error(`Vente supérieure à la position : ${t.ticker}`); const basis=p.quantity ? p.cost*q/p.quantity : 0; p.realized+=q*price-fee-basis;p.quantity-=q;p.cost-=basis}
  map.set(t.ticker,p);
 }
 return [...map.values()].filter(p=>p.quantity>1e-9).map(p=>{const quote=quotes[p.ticker];const value=quote ? p.quantity*quote.price : null;return {...p,average:p.cost/p.quantity,quote,value,unrealized:value===null?null:value-p.cost}});
}
export function cashBalance(transactions, id){return transactions.filter(t=>t.portfolioId===id).reduce((a,t)=>{let q=Number(t.quantity||0),p=Number(t.price||0),f=Number(t.fee||0),v=Number(t.amount||0);return a+({deposit:v,withdrawal:-v,dividend:v,buy:-q*p-f,sell:q*p-f}[t.type]||0)},0)}
export function validateTransaction(t, transactions){if(!t.date||!t.portfolioId) throw Error('Date et portefeuille requis.');if(!['buy','sell','deposit','withdrawal','dividend'].includes(t.type)) throw Error('Type invalide.');if(['buy','sell'].includes(t.type)){if(!t.ticker||!(Number(t.quantity)>0)||!(Number(t.price)>0)||Number(t.fee||0)<0) throw Error('Ticker, quantité et prix valides requis.');positions([...transactions,t],t.portfolioId,{});}else if(!(Number(t.amount)>0)) throw Error('Montant positif requis.');}
