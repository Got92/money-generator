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
export function transactionsThrough(transactions,date){if(!validDate(date))throw Error('Date de valorisation invalide.');return transactions.filter(t=>t.date<=date)}
export function positions(transactions, portfolioId, quotes, includeClosed=false, rates=[], base='EUR') {
 const map = new Map(),identityByTicker=new Map();
 for(const t of transactions.filter(t=>t.portfolioId===portfolioId&&t.type==='opening'))if(transactions.some(x=>x.portfolioId===portfolioId&&x.id!==t.id&&x.ticker===t.ticker&&x.date<t.date))throw Error('La position initiale doit précéder tout historique connu du titre.');
 for(const t of transactions.filter(x=>x.portfolioId===portfolioId&&x.ticker&&x.instrumentId)){const known=identityByTicker.get(t.ticker);if(known&&known!==t.instrumentId)throw Error('Identifiants contradictoires pour '+t.ticker);identityByTicker.set(t.ticker,t.instrumentId)}
 for (const t of transactions.filter(x => x.portfolioId === portfolioId).sort((a,b)=>a.date.localeCompare(b.date))) {
  if (!['buy','sell','opening','split','adjustment'].includes(t.type)) continue;
  const identity=t.instrumentId||identityByTicker.get(t.ticker)||t.ticker;const p=map.get(identity)||{ticker:t.ticker,...(t.instrumentId||identityByTicker.get(t.ticker)?{instrumentId:identity}:{}),quantity:0,cost:0,realized:0};
  if(t.type==='split'||t.type==='adjustment'){const value=numeric(t.type==='split'?t.ratio:t.quantityDelta);const result=t.type==='split'?p.quantity*value:p.quantity+value;if(!t.ticker||!t.note?.trim()||p.quantity<=EPS||!Number.isFinite(value)||(t.type==='split'?value<=0:value===0)||!Number.isFinite(result)||result<=EPS)throw Error('Opération sur titres invalide : '+(t.ticker||''));p.quantity=result;map.set(identity,p);continue}
  if(t.type==='opening'){if(p.quantity>EPS||map.has(identity))throw Error('Une position initiale doit précéder les opérations sur ce titre.');const q=numeric(t.quantity),price=numeric(t.price),rate=fxRate(rates,t.currency||base,base,t.date);if(!(q>0)||!(price>0)||!Number.isFinite(q)||!Number.isFinite(price))throw Error('Position initiale invalide.');p.quantity=q;p.cost=rate===null?null:q*price*rate;p.incompleteHistory=true;map.set(identity,p);continue}
  const q=numeric(t.quantity), price=numeric(t.price), fee=numeric(t.fee||0),settled=Boolean(t.settlementCurrency),settlement=numeric(t.settlementAmount), rate=fxRate(rates,settled?t.settlementCurrency:(t.currency||base),base,t.date);
  if(!Number.isFinite(q)||!Number.isFinite(price)||!Number.isFinite(fee)||q<=0||price<=0||fee<0||(settled&&(!Number.isFinite(settlement)||settlement<=0||fee!==0))) throw Error(`Transaction invalide : ${t.ticker}`);
  if(t.type==='buy'){p.quantity+=q;p.cost=p.cost===null||rate===null?null:p.cost+(settled?settlement:q*price+fee)*rate} else {if(q>p.quantity+EPS) throw Error(`Vente supérieure à la position : ${t.ticker}`); const basis=p.cost===null?null:(p.quantity ? p.cost*q/p.quantity : 0); p.realized=p.realized===null||basis===null||rate===null?null:p.realized+(settled?settlement:q*price-fee)*rate-basis;p.quantity-=q;p.cost=basis===null?null:p.cost-basis;if(Math.abs(p.quantity)<EPS){p.quantity=0;p.cost=0}}
  map.set(identity,p);
 }
 return [...map.values()].filter(p=>includeClosed||p.quantity>EPS).map(p=>{const quote=quotes[p.ticker];const rate=quote?fxRate(rates,quote.currency||base,base,quote.priceDate||'9999-12-31'):null;const value=quote && Number.isFinite(quote.price)&&rate!==null ? p.quantity*quote.price*rate : null;return {...p,average:p.quantity&&p.cost!==null?p.cost/p.quantity:null,quote,value,unrealized:value===null||p.cost===null?null:value-p.cost}});
}
export function cashBalance(transactions, id, rates=[], base='EUR', maxAgeDays=Infinity){return transactions.filter(t=>t.portfolioId===id).reduce((a,t)=>{if(['opening','split','adjustment'].includes(t.type))return a;const settled=['buy','sell'].includes(t.type)&&Boolean(t.settlementCurrency),q=numeric(t.quantity||0),p=numeric(t.price||0),f=numeric(t.fee||0),v=numeric(t.amount||0),rate=fxRate(rates,settled?t.settlementCurrency:(t.currency||base),base,t.date,maxAgeDays);const movement=settled?(t.type==='buy'?-numeric(t.settlementAmount):numeric(t.settlementAmount)):({deposit:v,withdrawal:-v,dividend:v,buy:-q*p-f,sell:q*p-f}[t.type]||0);return a===null||rate===null?null:a+movement*rate},0)}
function validateTransactionFields(t){if(!validDate(t.date)||!t.portfolioId) throw Error('Date valide et portefeuille requis.');if(t.currency&&!/^[A-Z]{3}$/.test(t.currency))throw Error('Devise invalide (code ISO à trois lettres requis).');if(!['buy','sell','opening','deposit','withdrawal','dividend','exchange','split','adjustment'].includes(t.type)) throw Error('Type invalide.');if(!['buy','sell'].includes(t.type)&&(t.settlementCurrency||t.settlementAmount||t.settlementFee))throw Error('Le règlement réel concerne uniquement les achats et ventes.');if(t.type==='opening'&&(Number(t.fee||0)!==0))throw Error('Une position initiale ne comporte pas de frais.');if(['buy','sell','opening'].includes(t.type)){if(!t.ticker||!Number.isFinite(numeric(t.quantity))||!(numeric(t.quantity)>0)||!Number.isFinite(numeric(t.price))||!(numeric(t.price)>0)||!Number.isFinite(numeric(t.fee||0))||numeric(t.fee||0)<0) throw Error('Ticker, quantité, prix et frais valides requis.');if(t.settlementCurrency||t.settlementAmount||t.settlementFee){if(!/^[A-Z]{3}$/.test(t.settlementCurrency||'')||!Number.isFinite(numeric(t.settlementAmount))||numeric(t.settlementAmount)<=0||!Number.isFinite(numeric(t.settlementFee||0))||numeric(t.settlementFee||0)<0||(t.type==='buy'&&numeric(t.settlementFee||0)>numeric(t.settlementAmount))||numeric(t.fee||0)!==0)throw Error('Règlement réel : devise, montant positif et frais de règlement valides requis ; les frais du prix doivent être à zéro.')}}else if(['split','adjustment'].includes(t.type)){const v=numeric(t.type==='split'?t.ratio:t.quantityDelta);if(!t.ticker||!t.note?.trim()||!Number.isFinite(v)||(t.type==='split'?v<=0:v===0))throw Error('Ticker, motif et valeur valides requis pour l’opération sur titres.')}else if(t.type==='exchange'){if(!t.currency||!/^[A-Z]{3}$/.test(t.targetCurrency||'')||t.currency===t.targetCurrency||!Number.isFinite(numeric(t.amount))||numeric(t.amount)<=0||!Number.isFinite(numeric(t.targetAmount))||numeric(t.targetAmount)<=0)throw Error('Devises distinctes et montants positifs requis pour le change.')}else if(!Number.isFinite(numeric(t.amount))||!(numeric(t.amount)>0)) throw Error('Montant positif requis.');}
export function validateTransaction(t, transactions){validateTransactionFields(t);positions([...transactions,t],t.portfolioId,{});}
export function validateTransactions(transactions){for(const t of transactions)validateTransactionFields(t);for(const id of new Set(transactions.map(t=>t.portfolioId)))positions(transactions,id,{});}
// In multi-currency accounts each trade settles in its transaction currency.
export function cashBalances(transactions,id){const balances={};for(const t of transactions.filter(t=>t.portfolioId===id)){const settled=['buy','sell'].includes(t.type)&&Boolean(t.settlementCurrency),c=settled?t.settlementCurrency:(t.currency||'EUR'),q=Number(t.quantity||0),p=Number(t.price||0),f=Number(t.fee||0),a=Number(t.amount||0);const movement=settled?(t.type==='buy'?-Number(t.settlementAmount):Number(t.settlementAmount)):({deposit:a,withdrawal:-a,dividend:a,buy:-q*p-f,sell:q*p-f,exchange:-a}[t.type]||0);balances[c]=(balances[c]||0)+movement;if(t.type==='exchange')balances[t.targetCurrency]=(balances[t.targetCurrency]||0)+Number(t.targetAmount)}return balances}
export function cashValue(balances,rates,date){let total=0;for(const [currency,amount] of Object.entries(balances)){if(Math.abs(amount)<1e-9)continue;const r=fxRate(rates,currency,'EUR',date);if(r===null)return null;total+=amount*r}return total}

// Stable ordering matches positions(), including transactions on the same day.
export function transactionsBefore(transactions,transaction){
 const next=transactions.some(t=>t.id===transaction.id)?transactions.map(t=>t.id===transaction.id?transaction:t):[...transactions,transaction];
 const ordered=next.filter(t=>t.portfolioId===transaction.portfolioId).sort((a,b)=>a.date.localeCompare(b.date));
 return ordered.slice(0,ordered.findIndex(t=>t.id===transaction.id));
}

// Preview uses the same chronology, cost basis, settlement and FX rules as saved data.
export function previewTransaction(transactions, transaction, quotes={}, rates=[], cashMode='converted'){
 quotes=Object.fromEntries(Object.entries(quotes).filter(([,q])=>q.priceDate&&q.priceDate<=transaction.date));
 const original=transactions.find(t=>t.id===transaction.id);
 const next=original?transactions.map(t=>t.id===transaction.id?transaction:t):[...transactions,transaction];
 validateTransactions(next);
 const before=transactionsBefore(transactions,transaction);
 const after=[...before,transaction];
 const match=p=>transaction.instrumentId&&p.instrumentId?p.instrumentId===transaction.instrumentId:p.ticker===transaction.ticker;
 const oldPosition=positions(before,transaction.portfolioId,quotes,true,rates).find(match);
 const all=positions(after,transaction.portfolioId,quotes,true,rates),position=all.find(match);
 const balancesBefore=cashBalances(before,transaction.portfolioId),balancesAfter=cashBalances(after,transaction.portfolioId);
 const movement=cashBalances([transaction],transaction.portfolioId);
 const cashBeforeEUR=cashBalance(before,transaction.portfolioId,rates),cashAfterEUR=cashBalance(after,transaction.portfolioId,rates);
 const cash=cashMode==='multi'?cashValue(balancesAfter,rates,transaction.date):cashAfterEUR;
 const total=cash===null||all.some(p=>p.value===null)?null:cash+all.reduce((sum,p)=>sum+p.value,0);
 return {next,quantityBefore:oldPosition?.quantity||0,quantityAfter:position?.quantity||0,
  averageBefore:oldPosition?.average??null,averageAfter:position?.average??null,
  gross:['buy','sell'].includes(transaction.type)?Math.abs(cashBalances([{...transaction,fee:0,settlementCurrency:'',settlementAmount:''}],transaction.portfolioId)[transaction.currency||'EUR']):null,
  fee:Number(transaction.settlementCurrency?transaction.settlementFee||0:transaction.fee||0),
  balancesBefore,balancesAfter,movement,cashBeforeEUR,cashAfterEUR,weight:total>0&&position&&position.value!==null?position.value/total*100:null};
}
