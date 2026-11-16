import {chromium} from 'playwright-core';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';

// All companies, responses and SQLite records below are disposable fixtures.
const dir=mkdtempSync(join(tmpdir(),'atlas-fundamental-browser-'));
const port=18400+Math.floor(Math.random()*1000),url=`http://127.0.0.1:${port}`;
const server=spawn(process.env.ATLAS_PYTHON||'.venv/bin/python',['server.py'],{env:{...process.env,ATLAS_DB:join(dir,'test.sqlite'),PORT:String(port)},stdio:'ignore'});
let browser,spawnError;
server.on('error',error=>{spawnError=error});
try{
 let ready=false;
 for(let n=0;n<100;n++){
  if(spawnError)throw spawnError;
  if(server.exitCode!==null)throw Error(`Server exited: ${server.exitCode}`);
  try{await fetch(url+'/');ready=true;break}catch{await new Promise(r=>setTimeout(r,100))}
 }
 if(!ready)throw Error('Server did not start');
 browser=await chromium.launch({headless:true,executablePath:process.env.ATLAS_CHROMIUM||process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage(),errors=[];
 page.setDefaultTimeout(10000);page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/fundamentals/history?*',async route=>{
  const query=new URL(route.request().url()),quarterly=query.searchParams.get('period')==='quarterly';
  await route.fulfill({json:{period:quarterly?'quarterly':'annual',coverage:{periodEnds:quarterly?[]:['2023-12-31'],firstPeriodEnd:'2023-12-31',lastPeriodEnd:'2023-12-31',byPeriod:quarterly?[]:[{periodEnd:'2023-12-31',missingMetrics:['gross_profit']}]},fetch:{error:quarterly?'Quota de test':null},data:quarterly?[]:[{periodEnd:'2023-12-31',statement:'income',metric:'revenue',value:100,currency:'USD',unit:'currency',source:'Fixture synthétique',fetchedAt:'2024-02-01'}]}});
 });
 await page.goto(url);
 await page.locator('[data-page="Research"]').click();
 await page.locator('[data-company]').first().click();
 assert.equal(await page.locator('#fundamentalHistory').count(),0);
 assert.match(await page.locator('main').textContent(),/entreprises fictives de démonstration/);
 const initial=await (await page.request.get(url+'/api/state')).json();
 const fixture={portfolios:[{id:'fund-test',name:'États financiers — fixture synthétique',currency:'EUR'}],transactions:[],watchlist:['FUNDTEST'],marketData:{FUNDTEST:{symbol:'FUNDTEST',name:'Société synthétique de test',currency:'EUR',financialCurrency:'USD',price:100,priceDate:'2024-02-01',fetchedAt:'2024-02-01',source:'Fixture synthétique',metrics:{}}}};
 const saved=await page.request.put(url+'/api/state',{data:{revision:initial.revision,data:fixture}});
 assert.equal(saved.status(),200);
 const revision=(await saved.json()).revision;
 await page.reload();
 await page.locator('[data-page="Watchlist"]').click();
 await page.locator('[data-company="FUNDTEST"]').click();
 await page.locator('#loadFundamentals').click();
 await page.waitForSelector('text=Chiffre d’affaires');
 assert.equal(await page.locator('#downloadFundamentals').isDisabled(),false);
 assert.match(await page.locator('#fundamentalResult').innerText(),/2023-12-31/);
 assert.match(await page.locator('#fundamentalResult').innerText(),/métadonnées actuelles/);
 await page.locator('#fundamentalResult summary').click();
 assert.match(await page.locator('#fundamentalResult').innerText(),/Marge brute/);
 const downloaded=page.waitForEvent('download');
 await page.locator('#downloadFundamentals').click();
 const file=await downloaded,payload=JSON.parse(readFileSync(await file.path(),'utf8'));
 assert.equal(payload.data[0].value,100);assert.equal(payload.data[0].source,'Fixture synthétique');
 await page.selectOption('#fundamentalPeriod','quarterly');
 assert.equal(await page.locator('#downloadFundamentals').isDisabled(),true);
 await page.click('#refreshFundamentals');await page.waitForSelector('text=Quota de test');
 assert.match(await page.locator('#fundamentalResult').innerText(),/Aucune donnée disponible/);
 assert.equal((await (await page.request.get(url+'/api/state')).json()).revision,revision);
 assert.deepEqual(errors,[]);
 console.log('PASS: vraie navigation entreprise, séparation démo, couverture annuelle, JSON téléchargé, changement de période, données absentes et erreur fournisseur ; transactions inchangées.');
}finally{
 if(browser)await browser.close();
 if(server.pid&&server.exitCode===null&&server.signalCode===null){const stopped=once(server,'exit');server.kill();await stopped}
 rmSync(dir,{recursive:true,force:true});
}
