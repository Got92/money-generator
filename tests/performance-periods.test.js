import {test} from 'node:test';
import assert from 'node:assert/strict';
import {PERIODS,periodStart,selectPeriod,periodPerformance} from '../src/performance-periods.js';
import {performanceSeries} from '../src/performance.js';

test('toutes les périodes demandées ont des bornes calendaires explicites',()=>{
 assert.deepEqual(PERIODS,['1D','1W','1M','3M','6M','YTD','1Y','3Y','5Y','MAX']);
 const expected=['2024-03-30','2024-03-24','2024-02-29','2023-12-31','2023-09-30','2023-12-31','2023-03-31','2021-03-31','2019-03-31',null];
 PERIODS.forEach((period,i)=>assert.equal(periodStart('2024-03-31',period),expected[i]));
});
test('les années bissextiles sont ramenées à une date réelle, sans débordement de mois',()=>{
 for(const period of ['1Y','3Y','5Y'])assert.match(periodStart('2024-02-29',period),/-02-28$/);
 assert.equal(periodStart('2023-03-31','1M'),'2023-02-28');
});
test('YTD inclut le rendement du premier janvier à partir du 31 décembre',()=>{
 const tx=[{portfolioId:'p',date:'2023-12-31',type:'deposit',amount:100},{portfolioId:'p',date:'2024-01-01',type:'dividend',amount:10}];
 const result=performanceSeries(tx,'p',[],[],'2024-01-02');
 const view=periodPerformance(result.points,'YTD');
 assert.equal(view.startDate,'2023-12-31');assert.ok(Math.abs(view.twr-.1)<1e-12);
});
test('une période plus longue que la couverture conserve ses dates réelles et les frais initiaux',()=>{
 const tx=[{portfolioId:'p',date:'2024-01-01',type:'deposit',amount:100},{portfolioId:'p',date:'2024-01-01',type:'buy',ticker:'A',quantity:1,price:99,fee:1}];
 const quotes=[{ticker:'A',date:'2024-01-01',price:99,currency:'EUR'}];
 const result=performanceSeries(tx,'p',quotes,[],'2024-01-02');
 const view=periodPerformance(result.points,'5Y');
 assert.equal(view.startDate,'2024-01-01');assert.ok(Math.abs(view.twr+.01)<1e-12);
});
test('un bord de période manquant ne doit jamais être tronqué silencieusement',()=>{
 const base=[{date:'2024-01-01',value:100,returnFactor:1,inception:true,externalFlow:100},
  {date:'2024-01-02',value:110,returnFactor:1.1,externalFlow:0},
  {date:'2024-01-03',value:null,returnFactor:null,externalFlow:0}];
 const result=periodPerformance(base,'MAX');assert.equal(result.endDate,'2024-01-03');assert.equal(result.twr,null);
 assert.deepEqual(result.points.map(p=>p.portfolio),[0,10.000000000000009,null]);
 const leading=periodPerformance([{...base[0],value:null,returnFactor:null},...base.slice(1)],'MAX');
 assert.equal(leading.twr,null);assert.ok(leading.points.every(p=>p.portfolio===null));
});
test('une période sans capital et une période trop courte expliquent leur indisponibilité',()=>{
 assert.match(periodPerformance([{date:'2024-01-01',value:0,externalFlow:0,returnFactor:1}], 'MAX').reason,/capital/);
 assert.match(periodPerformance([{date:'2024-01-01',value:100,externalFlow:100,inception:true,returnFactor:1}], 'MAX').reason,/deux dates/);
 assert.deepEqual(selectPeriod([],'MAX'),[]);assert.throws(()=>periodStart('2024-01-01','2Y'),/invalide/);
});
