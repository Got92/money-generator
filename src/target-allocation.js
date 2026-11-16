import {calculateAllocation} from './allocation.js';

// Position identifiers are tickers; category values come only from supplied quotes.
export function compareTargets(positions, cashEntries, config) {
 const results={};
 for (const dimension of ['position','sector','industry']) {
  const field=dimension==='position'?'targetTicker':dimension;
  const mapped=positions.map(p=>({...p,quote:{...p.quote,targetTicker:p.ticker}}));
  const allocation=calculateAllocation(mapped,cashEntries,field,config.basis);
  results[dimension]={...allocation,targets:config.targets.filter(t=>t.dimension===dimension).map(t=>{
   const group=allocation.groups.find(g=>!g.cash&&g.category===t.key);
   const unknown=dimension!=='position' && allocation.groups.some(g=>!g.cash&&g.category===null&&g.value!==0);
   const actual=allocation.status==='ok'&&!unknown?(group?.weight??0):null;
   return {...t,actual,deviation:actual===null?null:actual-t.target,flag:actual===null?'unavailable':actual<t.min?'below':actual>t.max?'above':'within'};
  })};
 }
 return results;
}
