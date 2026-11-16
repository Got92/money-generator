import {positions,cashBalances,cashBalance,fxRate} from './finance.js';

// A broker snapshot is explicit about its date, coverage, currencies and units.
export function reconcile({data,portfolioId,quotes={},rates=[],statement,tolerances={quantity:0.000001,money:0.02}}){
 const date=statement?.asOf, start=statement?.from;
 const validDate=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
 if(!validDate(date)||!validDate(start)||start>date)throw Error('Dates du relevé invalides : from et asOf sont requis.');
 if(!Array.isArray(statement.positions)||!Array.isArray(statement.cash))throw Error('Le relevé doit contenir les listes positions et cash.');
 if(typeof statement.positionsComplete!=='boolean'||typeof statement.cashComplete!=='boolean')throw Error('Précisez positionsComplete et cashComplete.');
 const number=(v,label)=>{if(typeof v!=='number'||!Number.isFinite(v))throw Error(label+' doit être un nombre fini.');return v};
 const portfolio=data.portfolios.find(p=>p.id===portfolioId);if(!portfolio)throw Error('Portefeuille introuvable.');
 const seen=new Set();for(const p of statement.positions){if(!p||typeof p.ticker!=='string'||!p.ticker.trim()||p.ticker!==p.ticker.trim().toUpperCase()||seen.has(p.ticker))throw Error('Ticker de relevé invalide ou en double.');seen.add(p.ticker);number(p.quantity,'Quantité');if(p.isin!=null&&!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(p.isin))throw Error('Format ISIN invalide.');if(p.exchange!=null&&(typeof p.exchange!=='string'||!p.exchange.trim()))throw Error('Place invalide.');if(p.quantity<0)throw Error('Quantité négative non prise en charge.');for(const k of ['averageEUR','valueEUR'])if(p[k]!=null)number(p[k],k)}
 const currencies=new Set();for(const c of statement.cash){if(!c||!/^\w{3}$/.test(c.currency||'')||! /^[A-Z]{3}$/.test(c.currency)||currencies.has(c.currency))throw Error('Devise de relevé invalide ou en double.');currencies.add(c.currency);number(c.amount,'Liquidités')}
 for(const k of ['quantity','money'])if(!Number.isFinite(tolerances[k])||tolerances[k]<0)throw Error('Tolérance invalide.');
 const tx=data.transactions.filter(t=>t.portfolioId===portfolioId&&t.date<=date), period=tx.filter(t=>t.date>=start), rows=[];
 const add=(category,key,atlas,broker,tolerance,cause)=>{const ok=atlas!==null&&broker!==null&&Number.isFinite(atlas)&&Number.isFinite(broker);const delta=ok?atlas-broker:null;rows.push({category,key,atlas,broker,delta,status:!ok?'unavailable':Math.abs(delta)<=tolerance?'ok':'difference',cause:!ok?cause||'Donnée absente ou couverture non confirmée.':Math.abs(delta)>tolerance?cause:null})};
 // Never use a quote from after the statement date or an undated/stale FX rate.
 const eligible={};for(const [ticker,q] of Object.entries(quotes)){if(q?.priceDate&&q.priceDate<=date&&Date.parse(date)-Date.parse(q.priceDate)<=7*86400000&&Number.isFinite(q.price)&&q.currency)eligible[ticker]=q}
 const local=positions(tx,portfolioId,eligible,true,rates), byTicker=new Map(local.map(p=>[p.ticker,p])), broker=new Map(statement.positions.map(p=>[p.ticker,p]));
 for(const ticker of new Set([...byTicker.keys(),...broker.keys()])){
  const p=byTicker.get(ticker),b=broker.get(ticker),held=p?.quantity||0, brokerQty=b?.quantity??(statement.positionsComplete?0:null);
  add('Quantité',ticker,held,brokerQty,tolerances.quantity,'Transaction manquante, opération sur titres ou correspondance de ticker à vérifier.');
  if(held>1e-9||brokerQty>1e-9){
   const basisKnown=tx.filter(t=>t.ticker===ticker&&['buy','sell'].includes(t.type)).every(t=>fxRate(rates,t.currency||'EUR','EUR',t.date,7)!==null);
   add('PRU EUR',ticker,basisKnown?(p?.average??null):null,b?.averageEUR??null,tolerances.money,'Devise, frais inclus, taux historique ou méthode de PRU à vérifier.');
   const q=eligible[ticker],fx=q?fxRate(rates,q.currency,'EUR',q.priceDate,7):null;
   const value=p&&q&&fx!==null?p.quantity*q.price*fx:null;
   add('Valeur EUR',ticker,value,b?.valueEUR??null,tolerances.money,'Cours, date de valorisation, devise ou taux de change absent ou différent.');
  }
  if(Math.abs(p?.realized||0)>1e-9||b?.realizedEUR!=null||(b&&b.quantity===0)){if(b?.realizedEUR!=null)number(b.realizedEUR,'Plus-value réalisée');const basisKnown=tx.filter(t=>t.ticker===ticker&&['buy','sell'].includes(t.type)).every(t=>fxRate(rates,t.currency||'EUR','EUR',t.date,7)!==null);add('Gain réalisé EUR',ticker,basisKnown?(p?.realized??0):null,b?.realizedEUR??null,tolerances.money,'Ventes, frais, taux historiques et méthode de PRU à vérifier.')}
  {
   const q=quotes[ticker];const supplied=Boolean(b?.isin||b?.exchange),complete=Boolean(supplied&&q&&(!b.isin||q.isin)&&(!b.exchange||q.exchange));
   const matches=complete&&(!b.isin||q.isin===b.isin)&&(!b.exchange||q.exchange===b.exchange);
   rows.push({category:'Identité',key:ticker,atlas:[q?.isin,q?.exchange].filter(Boolean).join(' / ')||null,broker:[b?.isin,b?.exchange].filter(Boolean).join(' / ')||null,delta:null,status:!complete?'unavailable':matches?'ok':'difference',cause:matches?null:'Vérifiez la place, l’ISIN et la correspondance du symbole avec le courtier.'});
  }
 }
 const balances=portfolio.cashMode==='multi'?cashBalances(tx,portfolioId):{'EUR':cashBalance(tx,portfolioId,rates,'EUR',7)};
 for(const c of new Set([...Object.keys(balances),...currencies])){
  const b=statement.cash.find(x=>x.currency===c),localValue=portfolio.cashMode!=='multi'&&c!=='EUR'?null:(balances[c]??0),brokerValue=b?.amount??(statement.cashComplete?0:null);
  add('Liquidités '+c,c,localValue,brokerValue,tolerances.money,'Mode de trésorerie, change, dépôt, frais ou dividende à vérifier.');
 }
 for(const [field,label] of [['fees','Frais'],['dividends','Dividendes']]){
  const provided=statement[field];if(provided!=null&&!Array.isArray(provided))throw Error(label+' : liste attendue.');
  if(!provided){add(label,'Période',null,null,tolerances.money,'Total par devise non fourni par le relevé.');continue}
  const seenCurr=new Set();for(const x of provided){if(!x||!/^[A-Z]{3}$/.test(x.currency||'')||seenCurr.has(x.currency))throw Error(label+' : devise invalide ou en double.');seenCurr.add(x.currency);number(x.amount,label)}
  const localTotals={};for(const t of period){const c=t.currency||'EUR',v=field==='fees'&&['buy','sell'].includes(t.type)?Number(t.fee||0):field==='dividends'&&t.type==='dividend'?Number(t.amount):0;if(v)localTotals[c]=(localTotals[c]||0)+v}
  for(const c of new Set([...Object.keys(localTotals),...seenCurr])){const b=provided.find(x=>x.currency===c);add(label,c,localTotals[c]||0,b?.amount??null,tolerances.money,'Période, devise, frais ou dividendes manquants à vérifier.')}
  if(!provided.length&&!Object.keys(localTotals).length)add(label,'Période',0,0,tolerances.money);
 }
 return {asOf:date,from:start,rows,counts:{ok:rows.filter(x=>x.status==='ok').length,difference:rows.filter(x=>x.status==='difference').length,unavailable:rows.filter(x=>x.status==='unavailable').length}};
}
