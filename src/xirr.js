// ACT/365 XIRR. Root isolation uses the critical points of exponential sums.
const DAY=86400000;
function dateValue(day){
 if(typeof day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(day))return NaN;
 const value=Date.parse(day+'T00:00:00Z');
 return Number.isFinite(value)&&new Date(value).toISOString().slice(0,10)===day?value:NaN;
}
function evaluate(terms,x){
 const logs=terms.map(([t,c])=>Math.log(Math.abs(c))-t*x),largest=Math.max(...logs);
 let value=0,size=0;
 terms.forEach(([,c],i)=>{const weight=Math.exp(logs[i]-largest);value+=Math.sign(c)*weight;size+=weight});
 return {value,nearZero:Math.abs(value)<=1e-11*size};
}
function bounds(terms){
 const [first,last]=[terms[0],terms.at(-1)],safety=Math.log(2*terms.length);
 let lo=-1,hi=1;
 for(const [t,c] of terms){
  if(t<last[0])lo=Math.min(lo,(-safety-Math.log(Math.abs(c))+Math.log(Math.abs(last[1])))/(last[0]-t));
  if(t>first[0])hi=Math.max(hi,(safety+Math.log(Math.abs(c))-Math.log(Math.abs(first[1])))/(t-first[0]));
 }
 return [lo,hi];
}
function bisect(terms,lo,hi){
 let left=evaluate(terms,lo).value;
 for(let i=0;i<200&&hi-lo>1e-13*Math.max(1,Math.abs(lo),Math.abs(hi));i++){
  const mid=lo+(hi-lo)/2,value=evaluate(terms,mid).value;
  if(value===0)return mid;
  if(Math.sign(left)!==Math.sign(value))hi=mid;else{lo=mid;left=value}
 }
 return lo+(hi-lo)/2;
}
function isolate(terms,depth=0){
 const changes=terms.slice(1).reduce((n,term,i)=>n+(Math.sign(term[1])!==Math.sign(terms[i][1])),0);
 if(!changes)return {roots:[],uncertain:false};
 if(depth>128)return {roots:[],uncertain:true};
 const [lo,hi]=bounds(terms);
 if(!Number.isFinite(lo)||!Number.isFinite(hi))return {roots:[],uncertain:true};
 if(changes===1)return {roots:[bisect(terms,lo,hi)],uncertain:false};
 // Divide by the first exponential, then differentiate. Its critical points
 // partition the original sum into monotone intervals, including tangencies.
 const derivative=terms.slice(1).map(([t,c])=>[t-terms[1][0],-(t-terms[0][0])*c]);
 const scale=Math.max(...derivative.map(([,c])=>Math.abs(c)));
 if(!Number.isFinite(scale)||!scale||derivative.some(([,c])=>!c||!Number.isFinite(c/scale)||c/scale===0))return {roots:[],uncertain:true};
 const critical=isolate(derivative.map(([t,c])=>[t,c/scale]),depth+1);
 const cuts=[lo,...critical.roots.filter(x=>x>lo&&x<hi),hi].sort((a,b)=>a-b);
 const values=cuts.map(x=>evaluate(terms,x)),roots=[];
 let uncertain=critical.uncertain;
 for(let i=1;i<cuts.length-1;i++)if(values[i].nearZero)uncertain=true;
 for(let i=1;i<cuts.length;i++){
  if(values[i-1].nearZero||values[i].nearZero)continue;
  if(Math.sign(values[i-1].value)!==Math.sign(values[i].value))roots.push(bisect(terms,cuts[i-1],cuts[i]));
 }
 return {roots,uncertain};
}
export function xirrResult(flows){
 const unavailable=reason=>({value:null,reason});
 if(!Array.isArray(flows)||flows.length<2)return unavailable('Au moins deux flux datés sont nécessaires.');
 const grouped=new Map();
 for(const flow of flows){
  const time=dateValue(flow?.date),amount=flow?.amount;
  if(!Number.isFinite(time)||typeof amount!=='number'||!Number.isFinite(amount))return unavailable('Un flux ou sa conversion en EUR est indisponible.');
  grouped.set(time,(grouped.get(time)||0)+amount);
 }
 const rows=[...grouped].filter(([,amount])=>amount!==0).sort((a,b)=>a[0]-b[0]);
 if(rows.length<2||!rows.some(([,v])=>v<0)||!rows.some(([,v])=>v>0))return unavailable('Les flux nets doivent avoir des dates distinctes et des signes opposés.');
 const scale=Math.max(...rows.map(([,v])=>Math.abs(v)));
 const terms=rows.map(([time,value])=>[(time-rows[0][0])/DAY/365,value/scale]);
 if(terms.some(([,c])=>!c||!Number.isFinite(c)))return unavailable('Échelle des flux non calculable.');
 const result=isolate(terms);
 if(result.uncertain||result.roots.length!==1)return unavailable('Aucune racine unique ne peut être certifiée (racines multiples, tangence ou calcul instable).');
 const value=Math.expm1(result.roots[0]);
 if(!Number.isFinite(value)||value<=-1||!evaluate(terms,result.roots[0]).nearZero)return unavailable('Le rendement annualisé est hors de la précision numérique disponible.');
 return {value,reason:null};
}
export function xirr(flows){return xirrResult(flows).value}
