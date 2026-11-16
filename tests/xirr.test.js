import {test} from 'node:test';
import assert from 'node:assert/strict';
import {xirr,xirrResult} from '../src/xirr.js';
const annual=amounts=>amounts.map((amount,i)=>({date:`${2017+i}-01-01`,amount}));
const close=(value,expected)=>{assert.notEqual(value,null);assert.ok(Math.abs(value-expected)<1e-9,`${value} != ${expected}`)};

test('XIRR trie et agrège les flux du même jour sans modifier les entrées',()=>{
 const flows=[{date:'2024-01-01',amount:220},{date:'2023-01-01',amount:-150},{date:'2023-01-01',amount:-50}],original=structuredClone(flows);
 close(xirr(flows),.1);assert.deepEqual(flows,original);
});
test('XIRR accepte un rendement exactement nul et une perte annuelle',()=>{close(xirr(annual([-100,100])),0);close(xirr(annual([-100,90])),-.1)});
test('XIRR suit ACT/365 y compris une année bissextile',()=>{
 const value=xirr([{date:'2024-01-01',amount:-100},{date:'2025-01-01',amount:110}]);
 close(value,1.1**(365/366)-1);
});
test('XIRR résout des flux non conventionnels à racine unique',()=>{close(xirr(annual([-100,50,-20,94.6])),.1)});
test('XIRR refuse deux racines dont une égale zéro',()=>{assert.equal(xirr(annual([-100,210,-110])),null)});
test('XIRR refuse deux racines très proches',()=>{assert.equal(xirr(annual([-100,220.01,-121.011])),null)});
test('XIRR refuse trois racines et une tangence non certifiable',()=>{
 assert.equal(xirr(annual([-100,360,-431,171.6])),null);
 const result=xirrResult(annual([-100,200,-100]));assert.equal(result.value,null);assert.match(result.reason,/tangence/);
});
test('XIRR est invariant à une échelle monétaire très grande ou petite',()=>{
 for(const scale of [1e-200,1e200])close(xirr(annual([-100*scale,110*scale])),.1);
});
test('XIRR ne dépend pas d’une grille ou d’une limite de rendement de 14 en logarithme',()=>{
 const result=xirr([{date:'2024-01-01',amount:-100},{date:'2024-01-02',amount:200}]);
 assert.ok(Math.abs(Math.log1p(result)-365*Math.log(2))<1e-9);
});
test('XIRR refuse les entrées invalides, les flux de même signe et les dates identiques',()=>{
 for(const flows of [[],annual([-100,-10]),annual([100,10]),[{date:'2024-02-30',amount:-100},{date:'2025-01-01',amount:110}],
  [{date:'2024-01-01',amount:-100},{date:'2024-01-01',amount:110}],annual([-100,Infinity]),annual([-100,NaN]),annual([-100,null])]){
  assert.equal(xirr(flows),null);
 }
});
test('XIRR refuse une solution arrondie à −100 %',()=>{assert.equal(xirr(annual([-100,1e-50])),null)});
