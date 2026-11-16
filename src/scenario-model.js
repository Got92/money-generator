import {dcf} from './valuation.js';
// Simulations only: all financial inputs are supplied by the user, in consistent units.
export function projectScenario(s){
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 if(!s||!['FCFF','FCFE'].includes(s.method)||!['growth','margin','manual'].includes(s.projectionMode)||!Array.isArray(s.years)||s.years.length!==5)throw Error('Cinq années et une méthode valides sont requises.');
 for(const k of ['discount','terminalGrowth','postYear5Growth','netDebt','shares','marginOfSafety'])if(!finite(s[k]))throw Error('Hypothèse numérique manquante : '+k);
 if(s.discount<=s.terminalGrowth||s.discount<=-1||s.terminalGrowth<=-1||s.postYear5Growth<=-1||s.shares<=0||s.marginOfSafety<0||s.marginOfSafety>=1||(s.method==='FCFE'&&s.netDebt!==0))throw Error('Taux, actions, marge de sécurité ou dette nette invalides. FCFE ne déduit pas la dette.');
 if(!/^[A-Z]{3}$/.test(s.currency||'')||typeof s.unit!=='string'||!s.unit.trim())throw Error('Devise et unité requises.');
 if(s.annualDividend!=null&&(!finite(s.annualDividend)||s.annualDividend<0))throw Error('Dividende invalide.');
 let f=s.initialFcf, revenue=s.initialRevenue;
 if(s.projectionMode==='growth'&&(!finite(f)||f<=0))throw Error('Flux initial positif requis.');
 if(s.projectionMode==='margin'&&(!finite(revenue)||revenue<=0))throw Error('Chiffre d’affaires initial positif requis.');
 const projections=s.years.map((y,i)=>{
  if(s.projectionMode==='manual'){if(!finite(y.flow))throw Error('Flux annuel manquant.');f=y.flow}
  else {if(!finite(y.growth)||y.growth<=-1)throw Error('Croissance annuelle invalide.');if(s.projectionMode==='growth')f*=1+y.growth;else{if(!finite(y.margin))throw Error('Marge de flux manquante.');revenue*=1+y.growth;f=revenue*y.margin}}
  return {year:i+1,flow:f,...(s.projectionMode==='margin'?{revenue,margin:y.margin}:{})};
 });
 if(projections[4].flow<=0)throw Error('Le flux de la cinquième année doit être positif.');
 return projections;
}
export function evaluateScenario(s,currentPrice=null){
 const projections=projectScenario(s), flows=projections.map(p=>p.flow), r=s.discount,g=s.terminalGrowth;
 // At each future date, explicitly discount the following five flows and a terminal value.
 const flowAt=year=>year<=5?flows[year-1]:flows[4]*(1+s.postYear5Growth)**(year-5);
 const valueAt=t=>{const future=Array.from({length:5},(_,i)=>flowAt(t+i+1));const terminal=future[4]*(1+g)/(r-g);return {value:dcf({method:s.method,projections:future,discount:r,terminal:g,netDebt:s.netDebt,shares:s.shares}),terminal}};
 const now=valueAt(0),one=valueAt(1),five=valueAt(5);
 if(![now.value,one.value,five.value,now.terminal].every(Number.isFinite))throw Error('Résultat non calculable.');
 const usable=typeof currentPrice==='number'&&Number.isFinite(currentPrice)&&currentPrice>0;
 const upside=usable?now.value/currentPrice-1:null;
 const annualizedReturn=usable&&five.value>0?(five.value/currentPrice)**(1/5)-1:null;
 const totalInvestorReturn=usable&&s.annualDividend!=null?(five.value+5*s.annualDividend)/currentPrice-1:null;
 return {fairValue:now.value,oneYearValue:one.value,fiveYearValue:five.value,upside,annualizedReturn,totalInvestorReturn,entryValue:now.value*(1-s.marginOfSafety),assumptions:{...s},projections,terminalValue:now.terminal};
}
