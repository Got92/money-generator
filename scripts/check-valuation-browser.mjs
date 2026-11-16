import {chromium} from 'playwright-core';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const dir=mkdtempSync(join(tmpdir(),'atlas-valuation-browser-'));
const port=19000+Math.floor(Math.random()*1000),url=`http://127.0.0.1:${port}`;
const server=spawn(process.env.ATLAS_PYTHON||'.venv/bin/python',['server.py'],{env:{...process.env,ATLAS_DB:join(dir,'test.sqlite'),PORT:String(port)},stdio:'ignore'});
let browser;
try{
 let ready=false;for(let n=0;n<100;n++){try{await fetch(url+'/');ready=true;break}catch{await new Promise(r=>setTimeout(r,100))}}if(!ready)throw Error('Server did not start');
 browser=await chromium.launch({headless:true,executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',args:['--no-sandbox']});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const initial=await (await page.request.get(url+'/api/state')).json();
 const fixture={portfolios:[{id:'test',name:'Test',currency:'EUR'}],transactions:[],watchlist:['SYN'],marketData:{SYN:{symbol:'SYN',name:'Société synthétique',currency:'USD',price:20,priceDate:'2024-01-01',fetchedAt:'2024-01-01',source:'Fixture',metrics:{}}}};
 assert.equal((await page.request.put(url+'/api/state',{data:{revision:initial.revision,data:fixture}})).status(),200);
 await page.goto(url);await page.locator('[data-page="Watchlist"]').click();await page.locator('[data-company="SYN"]').click();
 await page.locator('#loadValuation').click();await page.waitForFunction(()=>document.querySelector('#valuationResult').textContent.includes('Historique indisponible'));
 assert.match(await page.locator('#valuationResult').innerText(),/Aucune observation disponible/);
 await page.selectOption('#entryForm [name=kind]','enterprise');await page.fill('#entryForm [name=target]','8');await page.fill('#entryForm [name=base]','100');await page.fill('#entryForm [name=shares]','50');await page.fill('#entryForm [name=debt]','200');await page.click('#entryForm button');assert.match(await page.locator('#entryResult').innerText(),/12 par action/);
 assert.equal((await page.request.get(url+'/api/valuation/history?symbol=bad%26symbol')).status(),400);assert.deepEqual(errors,[]);
 console.log('PASS: navigation réelle, API vide et validation, prix EV par action.');
}finally{if(browser)await browser.close();if(server.pid&&server.exitCode===null){const stopped=once(server,'exit');server.kill();await stopped}rmSync(dir,{recursive:true,force:true})}
