import {test} from 'node:test';import assert from 'node:assert/strict';
test('les historiques et taux restent propres à chaque document',async()=>{
 const original=globalThis.fetch;let calls=0;globalThis.fetch=async url=>({ok:true,json:async()=>({data:url.includes('/fx?')?[{from:'USD',to:'EUR',date:'2024-01-01',rate:.9}]:[{ticker:'IBM',date:'2024-01-01',price:100,currency:'USD'}]})});
 try {const a=await import('../src/session-market.js?tab=a'),b=await import('../src/session-market.js?tab=b');await a.loadHistory('IBM');await a.loadFx('USD');assert.equal(a.sessionRates().length,1);assert.equal(b.sessionRates().length,0);const saved=globalThis.fetch;globalThis.fetch=async(...args)=>{calls++;return saved(...args)};await a.loadHistory('IBM');assert.equal(calls,0);await b.loadHistory('IBM');assert.equal(calls,1)} finally {globalThis.fetch=original}
});
