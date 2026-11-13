import {test} from 'node:test';import assert from 'node:assert/strict';import {dcf} from '../src/valuation.js';
test('DCF calcule les flux actualisés et déduit la dette',()=>{let x=dcf({fcf:100,growth:0,discount:.1,terminal:0,netDebt:100,shares:10});assert.ok(Math.abs(x-90)<1e-8)});
test('DCF refuse les hypothèses incohérentes',()=>{assert.throws(()=>dcf({fcf:100,growth:.02,discount:.02,terminal:.02,netDebt:0,shares:10}));assert.throws(()=>dcf({fcf:100,growth:0,discount:.1,terminal:0,netDebt:0,shares:0}));});
