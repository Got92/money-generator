import {validateTransactions} from './finance.js';
export const IMPORT_FIELDS=['date','type','ticker','quantity','price','fee','amount','currency','targetCurrency','targetAmount','ratio','quantityDelta','note','brokerRef','sourceIsin','settlementCurrency','settlementAmount','settlementFee'];
const TYPES={buy:'buy',achat:'buy',sell:'sell',vente:'sell',deposit:'deposit',depot:'deposit',withdrawal:'withdrawal',retrait:'withdrawal',dividend:'dividend',dividende:'dividend',exchange:'exchange',change:'exchange',split:'split',adjustment:'adjustment',correction:'adjustment'};
const normal=s=>String(s||'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[\s_\-]/g,'');
function validIsin(value){if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(value))return false;const digits=[...value].map(c=>/[A-Z]/.test(c)?String(c.charCodeAt(0)-55):c).join('');return [...digits].reverse().reduce((sum,c,i)=>{const n=Number(c)*(i%2?2:1);return sum+Math.floor(n/10)+n%10},0)%10===0}
export function guessColumns(headers){return Object.fromEntries(IMPORT_FIELDS.map(key=>[key,headers.findIndex(h=>normal(h)===normal(key))]));}
export function prepareImport({rows,mapping,portfolioId,existing=[],symbols={},cashMode='converted',idFactory=()=>crypto.randomUUID()}){
 if(!Array.isArray(rows)||!rows.length)throw Error('Aucune ligne à importer.');
 for(const key of ['date','type'])if(!Number.isInteger(mapping[key])||mapping[key]<0)throw Error('Associez les colonnes date et type.');
 const chosen=Object.values(mapping).filter(i=>Number.isInteger(i)&&i>=0);if(new Set(chosen).size!==chosen.length)throw Error('Une colonne ne peut pas être associée à plusieurs champs.');
 const pending=[],originalSymbols=new Set();
 const get=(row,key)=>mapping[key]>=0?String(row[mapping[key]]??'').trim():'';
 for(let i=0;i<rows.length;i++){
  const row=rows[i];if(row.every(x=>!String(x).trim()))continue;
  try{
   const t={id:idFactory(),portfolioId};for(const key of IMPORT_FIELDS)t[key]=get(row,key);
   t.type=TYPES[normal(t.type)]||t.type.toLowerCase();t.ticker=t.ticker.toUpperCase();const original=t.ticker;if(original)t.sourceTicker=original;if(original)originalSymbols.add(original);if(original&&Object.hasOwn(symbols,original)){if(!symbols[original]?.trim())throw Error('Symbole Atlas requis pour '+original+'.');t.ticker=symbols[original].trim().toUpperCase()}
   t.currency=(t.currency||'EUR').toUpperCase();t.targetCurrency=t.targetCurrency.toUpperCase();t.settlementCurrency=t.settlementCurrency.toUpperCase();t.sourceIsin=t.sourceIsin.toUpperCase();if(t.sourceIsin&&(!t.ticker||!validIsin(t.sourceIsin)))throw Error('ISIN courtier invalide ou symbole manquant.');if(t.brokerRef&&[...existing,...pending].some(x=>x.portfolioId===portfolioId&&x.brokerRef===t.brokerRef))throw Error('Identifiant courtier déjà importé : '+t.brokerRef+'.');if(t.type==='exchange'&&cashMode!=='multi')throw Error('Le change exige des soldes par devise.');
   for(const key of ['quantity','price','fee','amount','targetAmount','ratio','quantityDelta','settlementAmount','settlementFee'])if(t[key]){const raw=t[key].replace(',','.');if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw)||!Number.isFinite(Number(raw)))throw Error('Nombre invalide pour '+key+'.');t[key]=Number(raw)}
   const keys=['portfolioId','date','type','ticker','quantity','price','fee','amount','currency','targetCurrency','targetAmount','ratio','quantityDelta','note','settlementCurrency','settlementAmount','settlementFee'];
   const normalized=(v,key)=>key==='currency'?String(v||'EUR').toUpperCase():['quantity','price','fee','amount','targetAmount','ratio','quantityDelta','settlementAmount','settlementFee'].includes(key)?Number(v||0):String(v||'');
   if([...existing,...pending].some(x=>!(x.brokerRef&&t.brokerRef&&x.brokerRef!==t.brokerRef)&&keys.every(k=>normalized(x[k],k)===normalized(t[k],k))))throw Error('Doublon probable : vérifiez les opérations identiques.');
   pending.push(t);
  }catch(e){throw Error('Ligne '+(i+2)+' : '+e.message)}
 }
 if(!pending.length)throw Error('Aucune ligne à importer.');
 validateTransactions([...existing,...pending]);return {transactions:pending,symbols:[...originalSymbols].sort()};
}

// Only reuse a previously confirmed broker mapping with the same source identity.
// A shared ISIN alone does not establish a listing (exchange/currency may differ).
export function reusableImportSymbols({rows,mapping,existing=[],registry=[],portfolioId}){
 const get=(row,key)=>mapping[key]>=0?String(row[mapping[key]]||'').trim().toUpperCase():'';
 const result={};
 for(const source of new Set(rows.map(r=>get(r,'ticker')).filter(Boolean))){
  const group=rows.filter(r=>get(r,'ticker')===source);
  const isins=new Set(group.map(r=>get(r,'sourceIsin'))),currencies=new Set(group.map(r=>get(r,'currency')));
  if(isins.size!==1||currencies.size!==1||!group.every(r=>get(r,'brokerRef').startsWith('TRADING212:')))continue;
  const matches=existing.filter(t=>t.portfolioId===portfolioId&&t.brokerRef?.startsWith('trading212:')&&t.sourceTicker===source&&String(t.sourceIsin||'')===[...isins][0]&&t.currency===[...currencies][0]);
  const targets=new Set(matches.map(t=>t.ticker));if(targets.size!==1)continue;
  const target=[...targets][0],item=registry.find(x=>x.ticker===target);
  if(!item||matches.some(t=>t.instrumentId!==item.id)||(item.isin&&[...isins][0]&&item.isin!==[...isins][0])||(item.currency&&item.currency!==[...currencies][0]))continue;
  result[source]=target;
 }
 return result;
}
