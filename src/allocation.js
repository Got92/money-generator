// Values are in EUR. Unknown values invalidate the chosen denominator; they are never zero-filled.
// Cash entries carry their own currency and signed value, including overdrafts.
export function calculateAllocation(positions, cashEntries, field, basis='invested') {
 if (!['invested','total'].includes(basis)) throw new Error('Invalid allocation basis');
 const entries=positions.map(p=>({value:p.value, category:p.quote?.[field]}));
 if(basis==='total') entries.push(...cashEntries.map(c=>({value:c.value, category:field==='currency'?c.currency:'Liquidités', cash:field!=='currency'})));
 if(entries.some(e=>!Number.isFinite(e.value))) return {status:'missing', denominator:null, groups:[]};
 const denominator=entries.reduce((sum,e)=>sum+e.value,0);
 if(!Number.isFinite(denominator)||denominator<=0) return {status:'nonpositive', denominator, groups:[]};
 const groups=new Map();
 for(const e of entries){
  const category=typeof e.category==='string'&&e.category.trim()?e.category.trim():null;
  const key=e.cash?'cash':category===null?'unknown':'category:'+category;
  const old=groups.get(key)||{category, cash:!!e.cash, value:0};
  old.value+=e.value; groups.set(key,old);
 }
 return {status:'ok',denominator,groups:[...groups.values()].map(g=>({...g,weight:g.value/denominator})).sort((a,b)=>b.value-a.value)};
}
