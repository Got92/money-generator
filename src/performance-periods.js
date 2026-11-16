export const PERIODS=['1D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX'];
const DAY=86400000,stamp=day=>Date.parse(day+'T00:00:00Z');
function shiftMonths(day,count){
 const date=new Date(stamp(day)),dayOfMonth=date.getUTCDate();
 date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()-count);
 const last=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
 date.setUTCDate(Math.min(dayOfMonth,last));
 return date.toISOString().slice(0,10);
}
export function periodStart(end,period){
 if(!PERIODS.includes(period))throw Error('Période de performance invalide.');
 if(period==='MAX')return null;
 if(period==='YTD')return (Number(end.slice(0,4))-1)+'-12-31';
 if(period==='1D'||period==='1W')return new Date(stamp(end)-(period==='1D'?1:7)*DAY).toISOString().slice(0,10);
 return shiftMonths(end,({'1M':1,'3M':3,'6M':6,'1Y':12,'3Y':36,'5Y':60})[period]);
}
export function selectPeriod(points,period){
 if(!points.length)return [];
 const start=periodStart(points.at(-1).date,period);
 return start===null?points.slice():points.filter(p=>p.date>=start);
}
// Chain daily factors inside the selected window. Never rebase a global index
// that has crossed a gap or lost 100% of its value.
export function periodPerformance(allPoints,period){
 const selected=selectPeriod(allPoints,period),points=[];
 let linked=true,factor=1,capital=false,reason=null;
 for(let i=0;i<selected.length;i++){
  const point=selected[i];
  if(point.value===null){linked=false;reason??=point.reason||'Une valorisation est manquante dans la période.'}
  if(i===0&&!point.inception){
   capital=point.value>0;
  }else{
   if(point.returnFactor===null||!Number.isFinite(point.returnFactor)){linked=false;reason??=point.reason||'Un rendement quotidien est indisponible.'}
   else if(linked)factor*=point.returnFactor;
   capital ||= point.value>0||point.externalFlow>0;
  }
  points.push({...point,portfolio:linked&&capital&&Number.isFinite(factor)?(factor-1)*100:null});
 }
 if(!capital)reason??='Aucun capital positif n’est observé dans cette période.';
 if(selected.length<2)reason??='Au moins deux dates sont nécessaires pour comparer la période.';
 const twr=linked&&capital&&selected.length>=2&&Number.isFinite(factor)?factor-1:null;
 return {points,twr,reason:twr===null?reason:null,startDate:selected[0]?.date??null,endDate:selected.at(-1)?.date??null,
  carriedDays:selected.filter(p=>p.carried).length};
}
