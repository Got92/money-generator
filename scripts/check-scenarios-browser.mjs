import {chromium} from 'playwright-core';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const dir=mkdtempSync(join(tmpdir(),'atlas-scenarios-')),port=19400+Math.floor(Math.random()*1000),url=`http://127.0.0.1:${port}`;
const server=spawn(process.env.ATLAS_PYTHON||'.venv/bin/python',['server.py'],{env:{...process.env,ATLAS_DB:join(dir,'test.sqlite'),PORT:String(port)},stdio:'ignore'});let browser;
try{for(let i=0;i<100;i++){try{await fetch(url);break}catch{await new Promise(r=>setTimeout(r,100))}}
 browser=await chromium.launch({headless:true,executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',args:['--no-sandbox']});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);const initial=await (await page.request.get(url+'/api/state')).json();const fixture={portfolios:[{id:'p',name:'Fixture',currency:'EUR'}],transactions:[],watchlist:['TEST'],marketData:{TEST:{symbol:'TEST',name:'Société synthétique',currency:'EUR',price:10,source:'Fixture',fetchedAt:'2024-01-01',metrics:{}}}};
 assert.equal((await page.request.put(url+'/api/state',{data:{revision:initial.revision,data:fixture}})).status(),200);await page.reload();await page.locator('[data-page="Watchlist"]').click();await page.locator('[data-company="TEST"]').click();await page.locator('#scenarioForm').waitFor();
 assert.equal(await page.locator('[name="shares"]').last().inputValue(),'');
 for(const [key,value] of Object.entries({currency:'EUR',unit:'millions',discount:'10',terminalGrowth:'2',postYear5Growth:'4',netDebt:'20',shares:'10',marginOfSafety:'20',flow0:'10',flow1:'11',flow2:'12',flow3:'13',flow4:'14'}))await page.locator('#scenarioForm [name="'+key+'"]').fill(value);
 await page.locator('#scenarioForm button[type="submit"]').click();await page.getByText('Scénario enregistré.').waitFor();assert.match(await page.locator('#scenarioResult').innerText(),/rendement annualisé du prix/);
 const api=url+'/api/valuation/scenarios?symbol=TEST';let saved=await (await page.request.get(api)).json();assert.equal(saved.scenarios[0].name,'Bear');assert.equal(saved.scenarios[0].years[4].flow,14);
 await page.selectOption('#scenarioName','Bull');await page.selectOption('#scenarioName','Bear');assert.equal(await page.locator('#scenarioForm [name="flow4"]').inputValue(),'14');await page.reload();await page.locator('[data-page="Watchlist"]').click();await page.locator('[data-company="TEST"]').click();await page.locator('#scenarioForm').waitFor();assert.equal(await page.locator('#scenarioForm [name="flow4"]').inputValue(),'14');
 const bad=await page.request.put(api,{data:{...saved.scenarios[0],shares:0}});assert.equal(bad.status(),400);assert.equal((await (await page.request.get(api)).json()).scenarios[0].shares,10);
 await page.locator('#scenarioDelete').click();await page.getByText('Scénario supprimé.').waitFor();assert.equal((await (await page.request.get(api)).json()).scenarios.length,0);assert.deepEqual(errors,[]);console.log('PASS navigation, API validation, persistence and deletion');
}finally{if(browser)await browser.close();if(server.exitCode===null){const stopped=once(server,'exit');server.kill();await stopped}rmSync(dir,{recursive:true,force:true})}
