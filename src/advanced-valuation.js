import {dcf} from './valuation.js';

// A bracket is required: a root outside it is not silently extrapolated.
export function reverseDCF(model, price, {min=-0.95,max=2,steps=400,tolerance=1e-8}={}){
 if(!Number.isFinite(price)||price<=0||!Number.isFinite(min)||!Number.isFinite(max)||min<=-1||max<=min||!Number.isInteger(steps)||steps<2||!Number.isFinite(tolerance)||tolerance<=0) throw Error('Prix et intervalle de recherche valides requis.');
 const value=g=>dcf({...model,projections:undefined,growth:g})-price;
 const roots=[];let prevG=min,prev=value(min);
 for(let i=1;i<=steps;i++){
  const g=min+(max-min)*i/steps, y=value(g);
  if(Math.abs(prev)<=tolerance) roots.push(prevG);
  if(prev*y<0){let lo=prevG,hi=g,fl=prev;for(let j=0;j<100&&hi-lo>tolerance;j++){const mid=(lo+hi)/2,fm=value(mid);if(fl*fm<=0)hi=mid;else{lo=mid;fl=fm}}roots.push((lo+hi)/2)}
  prevG=g;prev=y;
 }
 if(Math.abs(prev)<=tolerance)roots.push(max);
 const unique=roots.filter((v,i)=>i===0||v-roots[i-1]>tolerance*2);
 return unique.length===1?{status:'ok',growth:unique[0],bracket:[min,max]}:{status:unique.length?'ambiguous':'no_root',growth:null,bracket:[min,max],roots:unique};
}
export function historicalCAGR(start,end,years){
 if(!Number.isFinite(start)||!Number.isFinite(end)||!Number.isFinite(years)||start<=0||end<=0||years<=0) return null;
 return (end/start)**(1/years)-1;
}
export function sensitivity(rows,columns,calculate){return {rows,columns,cells:rows.map(row=>columns.map(column=>{try{const v=calculate(row,column);return Number.isFinite(v)?{value:v}:{value:null,reason:'Résultat indisponible'} }catch(e){return {value:null,reason:e.message}}}))};}
export function discountTerminalMatrix(model,discounts,terminals){return sensitivity(discounts,terminals,(discount,terminal)=>dcf({...model,discount,terminal}));}
// Revenue and the FCF/operating-profit conversion are independent explicit assumptions.
export function growthMarginMatrix(model,growths,margins,{revenue,conversion}){
 return sensitivity(growths,margins,(growth,margin)=>{
  if(!Number.isFinite(revenue)||revenue<=0||!Number.isFinite(conversion)||conversion<0||!Number.isFinite(margin)||margin<=0||growth<=-1)throw Error('Chiffre d’affaires, marge et conversion FCF explicites requis.');
  const projections=Array.from({length:5},(_,i)=>revenue*(1+growth)**(i+1)*margin*conversion);
  return dcf({...model,projections});
 });
}
export function growthMultipleMatrix(model,growths,multiples){return sensitivity(growths,multiples,(growth,multiple)=>{
 const {fcf,discount,shares,netDebt=0,method='FCFF'}=model;
 if(!['FCFF','FCFE'].includes(method)||!Number.isFinite(fcf)||fcf<=0||!Number.isFinite(growth)||growth<=-1||!Number.isFinite(multiple)||multiple<0||!Number.isFinite(discount)||discount<=-1||!Number.isFinite(shares)||shares<=0||!Number.isFinite(netDebt)||(method==='FCFE'&&netDebt!==0))throw Error('Hypothèses de multiple terminal invalides.');
 const flows=Array.from({length:5},(_,i)=>fcf*(1+growth)**(i+1));
 return (flows.reduce((sum,f,i)=>sum+f/(1+discount)**(i+1),0)+flows[4]*multiple/(1+discount)**5-(method==='FCFF'?netDebt:0))/shares;
});}
export function fairValueSummary(entries,{currency,unit='per_share',basis='equity',price=null,marginOfSafety=0}={}){
 if(!currency||unit!=='per_share'||basis!=='equity'||!Number.isFinite(marginOfSafety)||marginOfSafety<0||marginOfSafety>=1)throw Error('Devise, base par action et marge de sécurité valide requises.');
 const included=[],excluded=[];
 for(const e of entries){let reason='';if(!['dcf','historical','relative'].includes(e.method))reason='Méthode non reconnue';else if(!Number.isFinite(e.value)||e.value<=0)reason='Valeur positive indisponible';else if(!Number.isFinite(e.weight)||e.weight<0)reason='Poids invalide';else if(!e.relevant)reason='Méthode non pertinente';else if(e.currency!==currency||e.unit!==unit||e.basis!==basis)reason='Devise, unité ou base non comparable';else if(!e.source?.trim())reason='Source ou hypothèse manquante';else if(e.weight===0)reason='Poids nul';(reason?excluded:included).push(reason?{...e,reason}:e)}
 const weight=included.reduce((s,e)=>s+e.weight,0),fairValue=weight?included.reduce((s,e)=>s+e.value*e.weight,0)/weight:null;
 return {included,excluded,fairValue,range:weight?[Math.min(...included.map(e=>e.value)),Math.max(...included.map(e=>e.value))]:null,entryPrice:fairValue===null?null:fairValue*(1-marginOfSafety),upside:fairValue!==null&&Number.isFinite(price)&&price>0?fairValue/price-1:null};
}
// Adapter accepts a genuine PR10 evaluation, never invents a scenario or its valuation.
export function scenarioSummaryEntry(scenario,evaluation,weight=1){return {method:'dcf',value:evaluation?.fairValue,weight,currency:scenario?.currency,unit:'per_share',basis:'equity',source:`Scénario DCF ${scenario?.name||''}`.trim(),relevant:true};}
