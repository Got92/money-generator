import {parseCSV} from './csv.js';
// Normalised format, not a Trading 212 export parser; values must already be mapped by the user.
export function parseBrokerCSV(text){
 const rows=parseCSV(text.replace(/^\uFEFF/,'')), headers=rows.shift()?.map(x=>x.trim());
 if(!headers||new Set(headers).size!==headers.length||!headers.includes('type'))throw Error('En-tête CSV invalide.');
 const values=rows.filter(r=>r.some(x=>x.trim())).map((r,i)=>{if(r.length!==headers.length)throw Error(`Nombre de colonnes invalide à la ligne ${i+2}.`);return Object.fromEntries(headers.map((h,j)=>[h,r[j].trim()]))});
 const meta=values.filter(r=>r.type==='meta');if(meta.length!==1)throw Error('Une seule ligne meta est requise.');
 const bool=(x)=>x==='true'?true:x==='false'?false:(()=>{throw Error('Les indicateurs de couverture doivent valoir true ou false.')})();
 const num=(s,field,required=false)=>{if(!s){if(required)throw Error(field+' requis.');return undefined}const n=Number(s);if(!Number.isFinite(n))throw Error(field+' invalide.');return n};
 const result={from:meta[0].from,asOf:meta[0].asOf,positionsComplete:bool(meta[0].positionsComplete),cashComplete:bool(meta[0].cashComplete),positions:[],cash:[]};
 const total=num(meta[0].totalEUR,'totalEUR');if(total!==undefined)result.totalEUR=total;
 for(const r of values){if(r.type==='meta')continue;if(r.type==='position'){const p={ticker:r.ticker,quantity:num(r.quantity,'quantity',true)};for(const k of ['averageEUR','valueEUR','realizedEUR']){const v=num(r[k],k);if(v!==undefined)p[k]=v}for(const k of ['isin','exchange'])if(r[k])p[k]=r[k];result.positions.push(p)}else if(['cash','fee','dividend'].includes(r.type)){const target={cash:'cash',fee:'fees',dividend:'dividends'}[r.type];(result[target]??=[]).push({currency:r.currency,amount:num(r.amount,'amount',true)})}else if(r.type==='fees_none'||r.type==='dividends_none'){const k=r.type==='fees_none'?'fees':'dividends';result[k]??=[]}else throw Error('Type de ligne inconnu : '+r.type)}
 return result;
}
