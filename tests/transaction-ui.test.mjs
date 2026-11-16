import test from 'node:test';
import assert from 'node:assert/strict';
import {previewTransaction,positions,cashBalance,validateTransactions} from '../src/finance.js';
import {performanceSeries} from '../src/performance.js';
import {guessColumns,prepareImport,reusableImportSymbols} from '../src/import-workflow.js';

const tx=(fields={})=>({id:'b',portfolioId:'p',type:'buy',ticker:'MSFT',currency:'EUR',date:'2026-11-16',quantity:5,price:420,fee:1,...fields});
test('preview of 5 shares at 420 plus 1 fee uses engine and never mutates data',()=>{
 const existing=[tx({id:'d',type:'deposit',amount:3000,ticker:''})],copy=structuredClone(existing);
 const p=previewTransaction(existing,tx(),{MSFT:{price:420,priceDate:'2026-11-16',currency:'EUR'}});
 assert.equal(p.gross,2100);assert.equal(p.movement.EUR,-2101);assert.equal(p.cashAfterEUR,899);
 assert.equal(p.quantityAfter,5);assert.equal(p.averageAfter,420.2);assert.equal(p.fee,1);
 assert.ok(Math.abs(p.weight-2100/2999*100)<1e-10);assert.deepEqual(existing,copy);
});
test('sale is checked on its date and editing revalidates later sales',()=>{
 const buy=tx({date:'2026-11-15'}),sell=tx({id:'s',date:'2026-11-17',type:'sell',quantity:5});
 assert.throws(()=>previewTransaction([buy],tx({id:'s',date:'2026-11-14',type:'sell',quantity:1})),/Vente supérieure/);
 assert.throws(()=>previewTransaction([buy,sell],{...buy,quantity:4}),/Vente supérieure/);
 assert.equal(previewTransaction([buy],{...sell,quantity:3}).quantityAfter,2);
});
test('foreign settlement and missing FX remain explicit, no invented conversion',()=>{
 const t=tx({currency:'USD',fee:0,settlementCurrency:'EUR',settlementAmount:1900,settlementFee:1});
 const p=previewTransaction([],t);assert.equal(p.movement.EUR,-1900);assert.equal(p.fee,1);assert.equal(p.averageAfter,380);
 const missing=previewTransaction([],tx({currency:'USD'}));assert.equal(missing.averageAfter,null);assert.equal(missing.cashAfterEUR,null);assert.equal(missing.weight,null);
});
test('initial position establishes reference basis without cash or invented performance',()=>{
 const opening=tx({type:'opening',fee:0});validateTransactions([opening]);
 assert.equal(cashBalance([opening],'p'),0);assert.equal(positions([opening],'p',{})[0].average,420);
 assert.equal(previewTransaction([],opening).quantityAfter,5);
 assert.equal(cashBalance([{...opening,currency:'USD'}],'p'),0);
 const result=performanceSeries([opening],'p',[],[],'2026-11-17');assert.deepEqual(result.points,[]);assert.match(result.xirrReason,/incomplet/);
 assert.throws(()=>validateTransactions([tx({id:'earlier',date:'2026-11-14'}),opening]),/initiale/);
 assert.throws(()=>validateTransactions([opening,{...opening,id:'second'}]),/initiale/);
});
test('dividend, cash, split and FX previews retain their engine semantics',()=>{
 assert.equal(previewTransaction([],tx({type:'deposit',ticker:'',amount:500})).movement.EUR,500);
 assert.equal(previewTransaction([],tx({type:'withdrawal',ticker:'',amount:50})).movement.EUR,-50);
 assert.equal(previewTransaction([],tx({type:'dividend',amount:12})).movement.EUR,12);
 assert.equal(previewTransaction([tx({id:'old',date:'2026-11-15'})],tx({id:'split',type:'split',ratio:2,note:'2:1'})).quantityAfter,10);
 assert.deepEqual(previewTransaction([],tx({type:'exchange',ticker:'',amount:90,targetCurrency:'USD',targetAmount:100})).movement,{EUR:-90,USD:100});
});
test('reuse requires a confirmed broker source identity and rejects conflicting targets',()=>{
 const headers=['date','type','ticker','quantity','price','currency','brokerRef','sourceIsin'],mapping=guessColumns(headers);
 const rows=[['2026-11-17','buy','MSFT','1','420','USD','trading212:new','US5949181045']];
 const prior=tx({currency:'USD',ticker:'MSFT',sourceTicker:'MSFT',sourceIsin:'US5949181045',instrumentId:'i',brokerRef:'trading212:old'});
 const args={rows,mapping,existing:[prior],registry:[{id:'i',ticker:'MSFT',isin:'US5949181045',currency:'USD'}],portfolioId:'p'};
 assert.deepEqual(reusableImportSymbols(args),{MSFT:'MSFT'});
 assert.deepEqual(reusableImportSymbols({...args,existing:[{...prior,sourceTicker:undefined}]}),{});
 assert.deepEqual(reusableImportSymbols({...args,existing:[prior,{...prior,ticker:'MSFT.DE',instrumentId:'other'}]}),{});
 assert.deepEqual(reusableImportSymbols({...args,rows:[rows[0],rows[0].map((x,i)=>i===5?'EUR':x)]}),{});
 const imported=prepareImport({rows,mapping,portfolioId:'p',idFactory:()=> 'new'}).transactions[0];assert.equal(imported.sourceTicker,'MSFT');
});
test('editing an acquisition before a same-day sale preserves insertion order',()=>{
 const b=tx(),s=tx({id:'sell',type:'sell',quantity:3});
 const preview=previewTransaction([b,s],{...b,price:410});
 assert.equal(preview.quantityBefore,0);assert.equal(preview.quantityAfter,5);assert.equal(preview.averageAfter,410.2);
 assert.equal(previewTransaction([b,s],{...s,quantity:4}).quantityBefore,5);
});
test('initial position rejects cash fees and settlement fields and later overselling',()=>{
 assert.throws(()=>validateTransactions([tx({type:'opening',fee:1})]),/frais/);
 assert.throws(()=>validateTransactions([tx({type:'opening',fee:0,settlementCurrency:'EUR',settlementAmount:10})]),/règlement/);
 assert.throws(()=>validateTransactions([tx({type:'opening',fee:0}),tx({id:'sale',type:'sell',quantity:6,date:'2026-11-17'})]),/Vente supérieure/);
});
test('preview omits weights based on a quote observed after transaction date',()=>{
 const p=previewTransaction([],tx(),{MSFT:{price:420,currency:'EUR',priceDate:'2026-11-17'}});
 assert.equal(p.weight,null);
});
