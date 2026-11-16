import {benchmarkSeries} from './performance.js';
import {periodPerformance} from './performance-periods.js';

// Yahoo closes are cached by symbol. TR is only offered where the provider
// identifies the series as such; an ETF's unadjusted close is never called TR.
export const BENCHMARKS = [
 {id:'sp500',name:'S&P 500',variants:[{symbol:'^GSPC',kind:'PR',label:'S&P 500 — Price Return'}, {symbol:'^SP500TR',kind:'TR',label:'S&P 500 — Total Return'}]},
 {id:'world',name:'MSCI World',variants:[{symbol:'URTH',kind:'PR',label:'MSCI World — proxy ETF URTH, prix',proxy:true}]},
 {id:'nasdaq100',name:'Nasdaq 100',variants:[{symbol:'^NDX',kind:'PR',label:'Nasdaq 100 — Price Return'}, {symbol:'^XNDX',kind:'TR',label:'Nasdaq 100 — Total Return (disponibilité incertaine)'}]},
 {id:'cac40',name:'CAC 40',variants:[{symbol:'^FCHI',kind:'PR',label:'CAC 40 — Price Return'}]},
 {id:'stoxx600',name:'STOXX Europe 600',variants:[{symbol:'^STOXX',kind:'PR',label:'STOXX Europe 600 — Price Return'}]},
 {id:'eurostoxx50',name:'Euro STOXX 50',variants:[{symbol:'^STOXX50E',kind:'PR',label:'Euro STOXX 50 — Price Return'}]}
];
export const benchmarkVariants=BENCHMARKS.flatMap(b=>b.variants.map(v=>({...v,index:b.name})));
export const benchmarkVariant=symbol=>benchmarkVariants.find(v=>v.symbol===symbol);

// Restrict both returns to the same endpoint dates; gaps inside the window
// invalidate comparison, rather than inventing a return over missing data.
export function compareBenchmark(points,prices,rates,symbol){
 const values=benchmarkSeries(points,prices,rates,symbol);
 const valid=(p,i)=>p.value!==null&&Number.isFinite(p.value)&&values[i]?.value>0;
 const start=points.findIndex(valid),end=points.findLastIndex(valid);
 if(start<0||end<=start)return {available:false,reason:'Moins de deux dates communes avec cours et change disponibles.',lines:[]};
 const window=points.slice(start,end+1),quotes=values.slice(start,end+1);
 if(quotes.some(q=>q.value===null))return {available:false,reason:'Cours ou change du benchmark manquant dans la période commune.',lines:[]};
 const portfolio=periodPerformance(window.map((p,i)=>i===0?{...p,inception:false}:p),'MAX');
 if(portfolio.twr===null)return {available:false,reason:'Comparaison impossible : '+portfolio.reason,lines:[]};
 const first=quotes[0].value,lines=portfolio.points.map((p,i)=>({date:p.date,portfolio:p.portfolio,benchmark:(quotes[i].value/first-1)*100}));
 return {available:true,startDate:window[0].date,endDate:window.at(-1).date,portfolioReturn:portfolio.twr,benchmarkReturn:quotes.at(-1).value/first-1,lines};
}
