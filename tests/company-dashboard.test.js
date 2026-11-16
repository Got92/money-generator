import {test} from 'node:test';
import assert from 'node:assert/strict';
import {windowPoints,renderCompanyDashboard} from '../src/company-dashboard.js';
test('fenêtre ancrée à la dernière période observée, sans inventer des années',()=>{
 const points=['2012-12-31','2020-12-31','2024-12-31'].map(periodEnd=>({periodEnd}));
 assert.deepEqual(windowPoints(points,3).map(p=>p.periodEnd),['2024-12-31']);
 assert.deepEqual(windowPoints(points,5).map(p=>p.periodEnd),['2020-12-31','2024-12-31']);
 assert.deepEqual(windowPoints([],10),[]);
});
test('les données de profil sont échappées et les champs absents explicites',()=>{
 const html=renderCompanyDashboard('<test>',{source:'<script>',metrics:{marketCap:10}});
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/Valeur d’entreprise : Indisponible/);
});
