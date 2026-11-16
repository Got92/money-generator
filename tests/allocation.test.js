import test from 'node:test';
import assert from 'node:assert/strict';
import {calculateAllocation} from '../src/allocation.js';
import {positions,cashBalances,cashValue} from '../src/finance.js';
const p=[{value:120,quote:{sector:'Tech',industry:'Logiciels',currency:'USD',country:'États-Unis',assetClass:'EQUITY'}},{value:80,quote:{currency:'EUR'}}];
const cash=[{currency:'EUR',value:50},{currency:'USD',value:-25}];
test('invested and cash-inclusive denominators retain unknown and signed cash',()=>{
 const invested=calculateAllocation(p,cash,'sector');
 assert.equal(invested.denominator,200);assert.deepEqual(invested.groups.map(x=>[x.category,x.weight]),[['Tech',.6],[null,.4]]);
 const total=calculateAllocation(p,cash,'sector','total');
 assert.equal(total.denominator,225);assert.equal(total.groups.find(x=>x.cash).value,25);
 const currencies=calculateAllocation(p,cash,'currency','total');
 assert.equal(currencies.groups.find(x=>x.category==='USD').value,95);assert.equal(currencies.groups.find(x=>x.category==='EUR').value,130);
 const overdrawn=calculateAllocation(p,[{currency:'EUR',value:-100}],'sector','total');
 assert.equal(overdrawn.groups.find(x=>x.category==='Tech').weight,1.2);assert.equal(overdrawn.groups.find(x=>x.cash).weight,-1);
});
test('missing values invalidate only the selected basis; zero or negative totals cannot define weights',()=>{
 assert.equal(calculateAllocation(p,[{value:null}],'sector').status,'ok');
 assert.equal(calculateAllocation(p,[{value:null}],'sector','total').status,'missing');
 assert.equal(calculateAllocation([{value:null}],[],'sector').status,'missing');
 assert.equal(calculateAllocation([{value:0}],[],'sector').status,'nonpositive');
 assert.equal(calculateAllocation(p,[{value:-200}],'sector','total').status,'nonpositive');
 assert.equal(calculateAllocation(p,[{value:-201}],'sector','total').status,'nonpositive');
});
test('fees, balances, missing prices and FX flow through existing finance calculations',()=>{
 const tx=[{portfolioId:'p',date:'2024-01-01',type:'deposit',amount:200,currency:'USD'}, {portfolioId:'p',date:'2024-01-02',type:'buy',ticker:'A',quantity:1,price:100,fee:5,currency:'USD'}];
 const rates=[{from:'USD',to:'EUR',date:'2024-01-01',rate:.9}];
 const balances=cashBalances(tx,'p');assert.equal(balances.USD,95);assert.equal(cashValue(balances,rates,'2024-01-03'),85.5);
 const quoted=positions(tx,'p',{A:{price:110,currency:'USD',priceDate:'2024-01-03',industry:'Software'}},false,rates);
 assert.equal(quoted[0].value,99);assert.equal(calculateAllocation(quoted,[], 'industry').groups[0].weight,1);
 assert.equal(calculateAllocation(positions(tx,'p',{},false,rates),[],'sector').status,'missing');
 assert.equal(calculateAllocation(positions(tx,'p',{A:{price:110,currency:'USD',priceDate:'2024-01-03'}},false,[]),[],'sector').status,'missing');
});
