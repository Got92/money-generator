import {validateTransactions} from './finance.js';
export const IMPORT_FIELDS=['date','type','ticker','quantity','price','fee','amount','currency','targetCurrency','targetAmount','ratio','quantityDelta','note'];
const TYPES={buy:'buy',achat:'buy',sell:'sell',vente:'sell',deposit:'deposit',depot:'deposit',withdrawal:'withdrawal',retrait:'withdrawal',dividend:'dividend',dividende:'dividend',exchange:'exchange',change:'exchange',split:'split',adjustment:'adjustment',correction:'adjustment'};
const normal=s=>String(s||'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[\s_\-]/g,'');
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
   t.type=TYPES[normal(t.type)]||t.type.toLowerCase();t.ticker=t.ticker.toUpperCase();const original=t.ticker;if(original)originalSymbols.add(original);if(original&&Object.hasOwn(symbols,original)){if(!symbols[original]?.trim())throw Error('Symbole Atlas requis pour '+original+'.');t.ticker=symbols[original].trim().toUpperCase()}
   t.currency=(t.currency||'EUR').toUpperCase();t.targetCurrency=t.targetCurrency.toUpperCase();if(t.type==='exchange'&&cashMode!=='multi')throw Error('Le change exige des soldes par devise.');
   for(const key of ['quantity','price','fee','amount','targetAmount','ratio','quantityDelta'])if(t[key]){const raw=t[key].replace(',','.');if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw)||!Number.isFinite(Number(raw)))throw Error('Nombre invalide pour '+key+'.');t[key]=Number(raw)}
   const keys=['portfolioId','date','type','ticker','quantity','price','fee','amount','currency','targetCurrency','targetAmount','ratio','quantityDelta','note'];
   const normalized=(v,key)=>key==='currency'?String(v||'EUR').toUpperCase():['quantity','price','fee','amount','targetAmount','ratio','quantityDelta'].includes(key)?Number(v||0):String(v||'');
   if([...existing,...pending].some(x=>keys.every(k=>normalized(x[k],k)===normalized(t[k],k))))throw Error('Doublon probable : vérifiez les opérations identiques.');
   pending.push(t);
  }catch(e){throw Error('Ligne '+(i+2)+' : '+e.message)}
 }
 if(!pending.length)throw Error('Aucune ligne à importer.');
 validateTransactions([...existing,...pending]);return {transactions:pending,symbols:[...originalSymbols].sort()};
}
