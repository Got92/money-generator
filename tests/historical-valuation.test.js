import {test} from 'node:test';
import assert from 'node:assert/strict';
import {entryPrice} from '../src/historical-valuation-ui.js';
test('price targets apply enterprise debt, yield and safety margin correctly',()=>{
 assert.equal(entryPrice({kind:'equity',target:15,base:100,shares:50}),30);
 assert.equal(entryPrice({kind:'enterprise',target:8,base:100,netDebt:200,shares:50}),12);
 assert.equal(entryPrice({kind:'enterprise',target:8,base:100,netDebt:-100,shares:50}),18);
 assert.equal(entryPrice({kind:'yield',target:.05,base:100,shares:50}),40);
 assert.equal(entryPrice({kind:'margin',fairValue:100,margin:.25}),75);
 assert.equal(entryPrice({kind:'yield',target:0,base:100,shares:50}),null);
 assert.equal(entryPrice({kind:'enterprise',target:8,base:100,shares:50,netDebt:NaN}),null);
});
