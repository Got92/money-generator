// All assets and ledger entries in these tests are synthetic fixtures.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {performanceSeries,periodPerformance} from '../src/performance.js';
const tx=(date,type,fields={})=>({portfolioId:'p',date,type,...fields});
const quote=(date,price,currency='EUR',ticker='A')=>({date,price,currency,ticker});
const fx=(date,rate)=>({date,rate,from:'USD',to:'EUR'});
const run=(transactions,prices=[],rates=[],end='2024-01-03',mode='converted')=>performanceSeries(transactions,'p',prices,rates,end,mode);
const near=(actual,expected)=>{assert.notEqual(actual,null);assert.ok(Math.abs(actual-expected)<1e-9,`${actual} != ${expected}`)};

test('achats successifs, frais, dividende et liquidation restent internes au portefeuille',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:1000}),tx('2024-01-01','buy',{ticker:'A',quantity:10,price:50,fee:2}),
  tx('2024-01-02','buy',{ticker:'A',quantity:5,price:60,fee:3}),tx('2024-01-03','dividend',{amount:10}),
  tx('2024-01-03','sell',{ticker:'A',quantity:15,price:70,fee:5})];
 const result=run(transactions,[quote('2024-01-01',50),quote('2024-01-02',60)]);
 assert.deepEqual(result.points.map(p=>p.value),[998,1095,1250]);
 near(result.points.at(-1).index,125);near(periodPerformance(result.points,'MAX').twr,.25);
 assert.deepEqual(result.points.map(p=>p.externalFlow),[1000,0,0]);
});
test('apports et retraits sont neutralisés avec leur montant de fin de journée',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100}),
  tx('2024-01-02','deposit',{amount:50}),tx('2024-01-03','sell',{ticker:'A',quantity:1,price:121}),tx('2024-01-03','withdrawal',{amount:80})];
 const result=run(transactions,[quote('2024-01-01',100),quote('2024-01-02',110)]);
 assert.deepEqual(result.points.map(p=>p.value),[100,160,91]);near(periodPerformance(result.points,'MAX').twr,1.1*(171/160)-1);
});
test('retrait total, jours sans capital et nouvel apport ne détruisent pas le TWR',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-02','withdrawal',{amount:100}),
  tx('2024-01-04','deposit',{amount:200}),tx('2024-01-05','dividend',{amount:20})];
 const result=run(transactions,[],[],'2024-01-05');
 assert.deepEqual(result.points.map(p=>p.value),[100,0,0,200,220]);
 assert.deepEqual(result.points.map(p=>p.index),[100,100,100,100,110.00000000000001]);
 near(periodPerformance(result.points,'MAX').twr,.1);
});
test('une perte réelle de 100 % ne disparaît pas après réinvestissement',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100}),
  tx('2024-01-03','deposit',{amount:100}),tx('2024-01-03','buy',{ticker:'B',quantity:1,price:100})];
 const prices=[quote('2024-01-01',100),quote('2024-01-02',0),quote('2024-01-03',100,'EUR','B'),quote('2024-01-04',110,'EUR','B')];
 const result=run(transactions,prices,[],'2024-01-04');
 assert.deepEqual(result.points.map(p=>p.value),[100,0,100,110]);
 assert.deepEqual(result.points.map(p=>p.index),[100,0,0,0]);
 near(periodPerformance(result.points,'MAX').twr,-1);near(periodPerformance(result.points,'1D').twr,.1);
});
test('une liquidation dont les frais consomment tout le capital produit une perte réelle de 100 %',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100}),
  tx('2024-01-02','sell',{ticker:'A',quantity:1,price:100,fee:100}),tx('2024-01-03','deposit',{amount:100}),
  tx('2024-01-04','dividend',{amount:10})];
 const result=run(transactions,[quote('2024-01-01',100)],[],'2024-01-04');
 assert.deepEqual(result.points.map(p=>p.value),[100,0,100,110]);
 near(periodPerformance(result.points,'MAX').twr,-1);near(periodPerformance(result.points,'1D').twr,.1);
});
test('un trou ne réinitialise jamais l’indice depuis l’origine, un intervalle ultérieur reste calculable',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100})];
 const prices=[quote('2024-01-01',100),quote('2024-01-12',120),quote('2024-01-13',132)];
 const result=run(transactions,prices,[],'2024-01-13');
 assert.equal(result.points[8].value,null);assert.equal(result.points[11].value,120);
 assert.equal(result.points.at(-1).index,null);assert.equal(periodPerformance(result.points,'MAX').twr,null);
 near(periodPerformance(result.points,'1D').twr,.1);
 near(Math.log1p(result.xirr),Math.log(1.32)*365/12);
});
test('la valeur finale manquante invalide TWR et XIRR sans reculer la date finale',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100})];
 const result=run(transactions,[quote('2024-01-01',100)],[],'2024-01-10');
 const view=periodPerformance(result.points,'MAX');assert.equal(view.twr,null);assert.equal(view.endDate,'2024-01-10');
 assert.equal(result.xirr,null);assert.match(result.xirrReason,/finale/);
});
test('les week-ends utilisent un vrai cours antérieur daté et signalent le report',()=>{
 const transactions=[tx('2024-01-05','deposit',{amount:100}),tx('2024-01-05','buy',{ticker:'A',quantity:1,price:100})];
 const result=run(transactions,[quote('2024-01-05',100)],[],'2024-01-07');
 assert.equal(result.points.at(-1).priceDates.A,'2024-01-05');assert.equal(result.points.at(-1).carried,true);
 assert.equal(periodPerformance(result.points,'MAX').carriedDays,2);near(periodPerformance(result.points,'MAX').twr,0);
});
test('cours absents, invalides ou futurs ne sont pas remplacés par le prix de transaction',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100})];
 for(const prices of [[],[quote('2024-01-02',110)],[quote('2024-01-01',null)],[quote('2024-01-01',NaN)]]){
  assert.equal(run(transactions,prices,[],'2024-01-01').points[0].value,null);
 }
});
test('un taux absent ne supprime pas les quantités ni les soldes multidevises',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100,currency:'USD'}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100,currency:'USD'})];
 const result=run(transactions,[quote('2024-01-01',100,'USD')],[fx('2024-01-02',.9),fx('2024-01-03',.95)],'2024-01-03','multi');
 assert.deepEqual(result.points.map(p=>p.value),[null,90,95]);
 assert.equal(result.xirr,null);assert.match(result.xirrReason,/conversion/);
 near(periodPerformance(result.points,'1D').twr,95/90-1);
});
test('un change interne conserve les montants réels et ne crée aucun apport externe',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','exchange',{amount:100,currency:'EUR',targetAmount:110,targetCurrency:'USD'})];
 const result=run(transactions,[],[fx('2024-01-01',.9),fx('2024-01-02',1)],'2024-01-02','multi');
 assert.deepEqual(result.points.map(p=>p.value),[99,110]);near(periodPerformance(result.points,'MAX').twr,.1);
 assert.deepEqual(result.points.map(p=>p.externalFlow),[100,0]);
});
test('sans taux de transaction, le cash converti reste inconnu malgré un taux futur',()=>{
 const transactions=[tx('2024-01-10','deposit',{amount:100,currency:'USD'})];
 const result=run(transactions,[],[fx('2024-01-01',.9),fx('2024-01-11',1)],'2024-01-11');
 assert.deepEqual(result.points.map(p=>p.value),[null,null]);assert.equal(result.xirr,null);
});
test('un change sans taux initial reste valorisable plus tard en soldes natifs',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:100}),tx('2024-01-01','exchange',{amount:100,currency:'EUR',targetAmount:100,targetCurrency:'USD'})];
 const result=run(transactions,[],[fx('2024-01-11',.9)],'2024-01-11','multi');
 assert.equal(result.points[0].value,null);assert.equal(result.points.at(-1).value,90);assert.notEqual(result.xirr,null);
});
test('les devises des cours et des transactions utilisent leurs propres taux historiques',()=>{
 const transactions=[tx('2024-01-01','deposit',{amount:1000}),tx('2024-01-01','buy',{ticker:'A',quantity:1,price:100,currency:'USD',fee:2})];
 const result=run(transactions,[quote('2024-01-01',100,'USD')],[fx('2024-01-01',.9),fx('2024-01-02',1)],'2024-01-02');
 near(result.points[0].value,998.2);near(result.points[1].value,1008.2);near(result.points[1].index,100.82);
});
test('portefeuilles et transactions futures sont isolés, les entrées restent intactes',()=>{
 const transactions=[tx('2024-01-02','dividend',{amount:10}),{...tx('2024-01-01','deposit',{amount:900}),portfolioId:'other'},tx('2024-01-01','deposit',{amount:100}),tx('2025-01-01','deposit',{amount:1000})];
 const before=structuredClone(transactions),result=run(transactions);
 assert.equal(result.points.at(-1).value,110);assert.deepEqual(transactions,before);
});
test('une valeur nette négative ou un registre invalide explique le rendement indisponible',()=>{
 const result=run([tx('2024-01-01','deposit',{amount:100}),tx('2024-01-02','withdrawal',{amount:110})]);
 assert.equal(periodPerformance(result.points,'MAX').twr,null);assert.match(result.points[1].reason,/négative/);
 assert.throws(()=>run([tx('2024-02-30','deposit',{amount:100})]),/Date/);
 assert.deepEqual(run([]).points,[]);
});
