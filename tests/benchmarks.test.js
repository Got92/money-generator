import test from 'node:test';
import assert from 'node:assert/strict';
import {BENCHMARKS,benchmarkVariants,compareBenchmark} from '../src/benchmarks.js';
const p=(date,value,returnFactor=1)=>({date,value,returnFactor,externalFlow:0,inception:false});
const q=(date,price,currency='USD')=>({date,price,currency,ticker:'^GSPC'});
const fx=(date,rate)=>({date,rate,from:'USD',to:'EUR'});
test('registre extensible et distinction TR, prix et proxy',()=>{
 assert.equal(BENCHMARKS.length,6);assert.equal(new Set(benchmarkVariants.map(v=>v.symbol)).size,benchmarkVariants.length);
 assert.equal(benchmarkVariants.find(v=>v.symbol==='^SP500TR').kind,'TR');assert.equal(benchmarkVariants.find(v=>v.symbol==='^XNDX').kind,'TR');
 assert.equal(benchmarkVariants.find(v=>v.symbol==='URTH').proxy,true);
 assert.equal(benchmarkVariants.find(v=>v.symbol==='URTH').kind,'PR');
});
test('compare aux mêmes extrémités en EUR sans déplacer la fenêtre originale',()=>{
 const points=[p('2024-01-01',100),p('2024-01-02',110,1.1),p('2024-01-03',121,1.1),p('2024-01-12',130,1.1)];
 const result=compareBenchmark(points,[q('2024-01-02',100),q('2024-01-03',110)],[fx('2024-01-02',.9),fx('2024-01-03',1)],'^GSPC');
 assert.equal(result.startDate,'2024-01-02');assert.equal(result.endDate,'2024-01-03');
 assert.ok(Math.abs(result.portfolioReturn-.1)<1e-12);assert.ok(Math.abs(result.benchmarkReturn-(110/90-1))<1e-12);
 assert.equal(result.lines[0].portfolio,0);assert.equal(points[0].date,'2024-01-01');
});
test('taux futurs, devise absente et prix ou taux trop anciens ne créent pas de couverture',()=>{
 const points=[p('2024-01-01',100),p('2024-01-02',100)];
 assert.equal(compareBenchmark(points,[q('2024-01-01',100),q('2024-01-02',110)],[fx('2024-01-03',1)],'^GSPC').available,false);
 assert.equal(compareBenchmark(points,[q('2024-01-01',100,''),q('2024-01-02',110,'')],[{date:'2024-01-01',from:'',to:'EUR',rate:1}], '^GSPC').available,false);
 const later=[p('2024-01-10',100),p('2024-01-11',100)];
 assert.equal(compareBenchmark(later,[q('2024-01-01',100)],[fx('2024-01-01',1)],'^GSPC').available,false);
});
test('lacunes internes et pertes de valorisation bloquent la comparaison',()=>{
 const points=[p('2024-01-01',100),p('2024-01-10',null,null),p('2024-01-11',120,null)];
 const quotes=[q('2024-01-01',100,'EUR'),q('2024-01-11',120,'EUR')];
 assert.equal(compareBenchmark(points,quotes,[],'^GSPC').available,false);
});
test('le rendement commun démarre à la clôture même le jour de financement',()=>{
 const points=[{...p('2024-01-01',99,.99),inception:true,externalFlow:100},p('2024-01-02',110,110/99)];
 const r=compareBenchmark(points,[q('2024-01-01',100,'EUR'),q('2024-01-02',110,'EUR')],[],'^GSPC');
 assert.ok(Math.abs(r.portfolioReturn-(110/99-1))<1e-12);assert.equal(r.lines[0].portfolio,0);
});
