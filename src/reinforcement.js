import {localToday} from './calendar.js';
import {positions,validateTransactions,cashBalances,cashValue,cashBalance,fxRate} from './finance.js';

// Amount is the total budget including fees; quantity is fractional when necessary.
export function simulateReinforcement({transactions,portfolioId,portfolio,quotes={},rates=[],ticker,amount,quantity,price,currency,fee=0,date,targets,scenarios,evaluateScenario}){
 const n=v=>Number(v), today=localToday();
 if(!portfolio||portfolio.id!==portfolioId||portfolio.currency!=='EUR')throw Error('Portefeuille EUR valide requis.');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date||'')||date>today)throw Error('Date de simulation présente ou passée requise.');
 if(!ticker||!/^[A-Z]{3}$/.test(currency||'')||!Number.isFinite(n(price))||n(price)<=0||!Number.isFinite(n(fee))||n(fee)<0)throw Error('Titre, prix, devise et frais valides requis.');
 const hasAmount=amount!==undefined&&amount!==null&&amount!=='';const hasQuantity=quantity!==undefined&&quantity!==null&&quantity!=='';
 if(hasAmount===hasQuantity)throw Error('Saisissez un budget ou une quantité, pas les deux.');
 const qty=hasAmount?(n(amount)-n(fee))/n(price):n(quantity);
 if(!Number.isFinite(qty)||qty<=0)throw Error('Le budget doit dépasser les frais et la quantité être positive.');
 const quote=quotes[ticker];if(quote?.currency&&quote.currency!==currency)throw Error('La devise du prix hypothétique doit être celle de la cotation.');
 const history=structuredClone(transactions.filter(t=>t.date<=date));validateTransactions(history);
 const usable=Object.fromEntries(Object.entries(quotes).filter(([,q])=>q&&q.currency&&q.priceDate&&q.priceDate<=date&&Number.isFinite(q.price)&&q.price>0));
 const buy={portfolioId,date,type:'buy',ticker,quantity:qty,price:n(price),fee:n(fee),currency};const next=[...history,buy];validateTransactions(next);
 const before=positions(history,portfolioId,usable,false,rates),after=positions(next,portfolioId,usable,false,rates);
 const old=before.find(p=>p.ticker===ticker),current=after.find(p=>p.ticker===ticker);
 const sum=ps=>ps.every(p=>p.value!==null)?ps.reduce((a,p)=>a+p.value,0):null;
 const pre=sum(before),post=sum(after);const hhi=(ps,total)=>total!==null&&total>0?ps.reduce((a,p)=>a+(p.value/total)**2,0):null;
 const oldHhi=hhi(before,pre),newHhi=hhi(after,post),weight=post!==null&&post>0&&current.value!==null?current.value/post:null;
 const nativeBalances=cashBalances(next,portfolioId);const cash=portfolio.cashMode==='multi'?cashValue(nativeBalances,rates,date):cashBalance(next,portfolioId,rates,'EUR');
 const balances=portfolio.cashMode==='multi'?nativeBalances:(cash===null?null:{EUR:cash});
 const target=date===today&&(!targets?.portfolioId||targets.portfolioId===portfolioId)?targets?.targets?.find(t=>t.dimension==='position'&&t.key===ticker):null;
 const targetDenominator=targets?.basis==='invested'?post:targets?.basis==='total'&&post!==null&&cash!==null?post+cash:null;
 const targetWeight=targetDenominator!==null&&targetDenominator>0&&current.value!==null?current.value/targetDenominator:null;
 const scenarioResults=Array.isArray(scenarios)&&typeof evaluateScenario==='function'?scenarios.map(s=>{if(date!==today)return {name:s.name,reason:'Disponibilité historique du scénario non vérifiée.'};if(s.currency!==currency)return {name:s.name,reason:'Devise du scénario différente ou inconnue.'};try{return {name:s.name,...evaluateScenario(s,n(price))}}catch(e){return {name:s.name,reason:e.message}}}):[];
 return {ticker,date,currency,quantity:qty,tradeCost:qty*n(price)+n(fee),fee:n(fee),oldQuantity:old?.quantity||0,newQuantity:current.quantity,oldAverageEur:old?old.average:null,newAverageEur:current.average,oldValueEur:old?.value??(old?null:0),newValueEur:current.value,marketQuote:usable[ticker]||null,tradeFx:fxRate(rates,currency,'EUR',date),weight,targetBasis:targets?.basis??null,targetWeight,target:target?.target??null,targetGap:targetWeight!==null&&target?.target!=null?targetWeight-target.target:null,oldHhi,newHhi,hhiChange:oldHhi!==null&&newHhi!==null?newHhi-oldHhi:null,cashBalances:balances,cashEur:cash,scenarios:scenarioResults};
}
