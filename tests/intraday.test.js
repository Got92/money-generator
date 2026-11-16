import {test} from 'node:test';import assert from 'node:assert/strict';
import {intradayPortfolio,intradayBenchmark} from '../src/intraday.js';
const t=(time,price)=>({timestamp:`2024-01-02T${time}:00Z`,price});
const tx=[{portfolioId:'p',date:'2024-01-01',type:'deposit',amount:100,currency:'EUR'},{portfolioId:'p',date:'2024-01-01',type:'buy',ticker:'A',quantity:1,price:100,currency:'EUR'}];
test('reconstruit la valeur avec des cours intrajournaliers horodatés',()=>{const data={A:{currency:'EUR',sessionDate:'2024-01-02',points:[t('10:00',100),t('10:05',102)]}};const r=intradayPortfolio(tx,'p',data,[],'converted','2024-01-02');assert.deepEqual(r.map(p=>p.value),[100,102]);assert.throws(()=>intradayPortfolio([...tx,{portfolioId:'p',date:'2024-01-02',type:'deposit',amount:5}], 'p',data,[],'converted','2024-01-02'),/heure/)});
test('utilise le change intrajournalier antérieur, jamais futur',()=>{const data={A:{currency:'USD',sessionDate:'2024-01-02',points:[t('10:00',100),t('10:05',100)]},'USDEUR=X':{points:[t('10:05',.9)]}};const r=intradayPortfolio(tx,'p',data,[],'converted','2024-01-02');assert.deepEqual(r.map(p=>p.value),[null,90]);assert.deepEqual(intradayBenchmark(r,data,'A'),[null,90])});
test('refuse des séances de marché différentes',()=>{const data={A:{currency:'EUR',sessionDate:'2024-01-01',points:[t('10:00',100)]}};assert.throws(()=>intradayPortfolio(tx,'p',data,[],'converted','2024-01-02'),/même date/)});
test('une position liquidée ne réclame plus ses cours intrajournaliers',()=>{
 const sold=[...tx,{portfolioId:'p',date:'2024-01-01',type:'sell',ticker:'A',quantity:1,price:100}];
 const cash=[...sold,{portfolioId:'p',date:'2024-01-01',type:'exchange',amount:100,currency:'EUR',targetAmount:100,targetCurrency:'USD'}];
 const data={'USDEUR=X':{points:[t('10:00',.9),t('10:05',.95)]}};
 assert.deepEqual(intradayPortfolio(cash,'p',data,[],'multi','2024-01-02').map(p=>p.value),[90,95]);
});
test('un solde nul ne réclame pas un taux intrajournalier inutile',()=>{
 const cash=[...tx,{portfolioId:'p',date:'2024-01-01',type:'deposit',currency:'USD',amount:5},{portfolioId:'p',date:'2024-01-01',type:'withdrawal',currency:'USD',amount:5}];
 const data={A:{currency:'EUR',sessionDate:'2024-01-02',points:[t('10:00',100),t('10:05',102)]}};
 assert.deepEqual(intradayPortfolio(cash,'p',data,[],'multi','2024-01-02').map(p=>p.value),[100,102]);
});
test('trie les observations intrajournalières et refuse les prix invalides et le change nul',()=>{
 const data={A:{currency:'USD',sessionDate:'2024-01-02',points:[t('10:05',101),t('10:00',100),t('10:10',NaN)]},'USDEUR=X':{points:[t('10:00',0),t('10:05',.9)]}};
 assert.deepEqual(intradayPortfolio(tx,'p',data,[],'converted','2024-01-02').map(p=>p.value),[null,90.9]);
});
test('une cotation intrajournalière de plus de trente minutes ne valorise pas un point',()=>{
 const data={A:{currency:'USD',sessionDate:'2024-01-02',points:[t('10:00',100),t('11:00',100)]},'USDEUR=X':{points:[t('10:00',.9)]}};
 assert.deepEqual(intradayPortfolio(tx,'p',data,[],'converted','2024-01-02').map(p=>p.value),[90,null]);
});
test('le cash converti ne réutilise pas un taux historique périmé',()=>{
 const cash=[{portfolioId:'p',date:'2024-01-10',type:'deposit',amount:100,currency:'USD'}];
 assert.throws(()=>intradayPortfolio(cash,'p',{},[{from:'USD',to:'EUR',date:'2024-01-01',rate:.9}],'converted','2024-01-11'),/historique manquant/);
});
