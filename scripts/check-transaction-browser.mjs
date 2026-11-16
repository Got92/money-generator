import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('..',import.meta.url)),directory=await mkdtemp(path.join(tmpdir(),'atlas-transactions-'));
let child,browser;const errors=[];
try{
 child=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_transaction_fixture.py'],{cwd:root,env:{...process.env,ATLAS_DB:path.join(directory,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:directory},stdio:['ignore','pipe','pipe']});
 child.stderr.on('data',c=>{if(c.toString().includes('Traceback'))process.stderr.write(c)});
 const lines=createInterface({input:child.stdout});
 const url=await Promise.race([once(lines,'line').then(([s])=>JSON.parse(s).url),once(child,'exit').then(([c])=>{throw Error('Fixture exited: '+c)}),once(child,'error').then(([e])=>{throw e})]);
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000},timezoneId:'Europe/Paris'});page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('atlas-last-auto-sync',String(Date.now())));
 const state=async()=> (await (await page.request.get(url+'/api/state')).json());
 const snapshot=async()=>JSON.stringify(await state());
 const open=async()=>{await page.locator('#addTx').click();await page.locator('#reviewTransaction').waitFor()};
 const cancel=async()=>page.locator('#modal [data-cancel]').last().click();
 const choose=async ticker=>page.locator('.instrument-suggestion').filter({hasText:ticker}).first().click();
 const enter=async(k,v)=>page.locator(`#modal [name="${k}"]`).fill(String(v));
 const save=async()=>{await page.locator('#reviewTransaction').click();await page.locator('#confirmTransaction').click();await page.waitForFunction(()=>!document.querySelector('#modal').open)};
 await page.goto(url);await page.locator('#addTx').waitFor();const initial=await snapshot();
 await open();
 assert.equal(await page.locator('#modal input:visible, #modal select:visible').count(),6);
 assert.equal(await page.locator('[name=ratio]').count(),0);assert.equal(await page.locator('[name=targetCurrency]').count(),0);
 assert.equal(await page.locator('[name=date]').inputValue(),await page.evaluate(()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}));
 await enter('instrumentSearch','Microsoft');await page.locator('.instrument-suggestion').filter({hasText:'NASDAQ'}).waitFor();await choose('MSFT');
 await page.waitForFunction(()=>document.querySelector('[name=price]')?.value==='420');
 assert.equal(await page.locator('[name=currency]').inputValue(),'USD');assert.match(await page.locator('#instrumentInfo').textContent(),/indicatif.*Fixture synthétique/);
 await enter('quantity',5);if(process.env.ATLAS_SCREENSHOT)await page.screenshot({path:process.env.ATLAS_SCREENSHOT,fullPage:true});await page.locator('#modal summary').click();await enter('fee',1);
 await page.waitForFunction(()=>document.querySelector('#transactionPreview').textContent.includes('2 101'));
 assert.match(await page.locator('#transactionPreview').textContent(),/Cash débité/);
 await page.locator('#reviewTransaction').click();assert.equal(await snapshot(),initial);await cancel();assert.equal(await snapshot(),initial);
 // A server save error keeps the transaction unchanged and leaves cancellation available.
 await open();await choose('TEST');await enter('quantity',1);await enter('price',120);await page.locator('#reviewTransaction').click();
 await page.route('**/api/state',route=>route.request().method()==='PUT'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Échec de sauvegarde de test'})}):route.continue());
 await page.locator('#confirmTransaction').click();await page.waitForFunction(()=>document.querySelector('#error')?.textContent.includes('Échec de sauvegarde'));assert.equal(await snapshot(),initial);await cancel();await page.unroute('**/api/state');
 // Repeating the form and confirming must persist exactly once.
 await open();await choose('TEST');await enter('quantity',2);await enter('price',120);await save();
 let current=await state();assert.equal(current.data.transactions.length,3);const bought=current.data.transactions.at(-1);assert.equal(bought.ticker,'TEST');
 await page.locator('[data-page="Portefeuilles"]').first().click();
 await open();await page.locator('[name=type]').selectOption('sell');await choose('TEST');await enter('quantity',8);await enter('price',110);
 assert.match(await page.locator('#heldQuantity').textContent(),/7/);assert.equal(await page.locator('#reviewTransaction').isDisabled(),true);
 await enter('quantity',6);await enter('date','2024-01-01');assert.equal(await page.locator('#reviewTransaction').isDisabled(),true);
 await enter('date',await page.evaluate(()=>new Date().toLocaleDateString('en-CA')));await enter('quantity',3);await save();
 const beforeEdit=await snapshot();await page.locator('[data-edit="buy"]').click();await enter('quantity',0.5);assert.equal(await page.locator('#reviewTransaction').isDisabled(),true);await cancel();assert.equal(await snapshot(),beforeEdit);
 // Cash, dividends, split, corrections and FX expose only relevant fields and really save.
 for(const [kind,values] of [['deposit',{amount:100}],['withdrawal',{amount:10}],['dividend',{amount:5}],['split',{ratio:2,note:'2:1'}],['adjustment',{quantityDelta:1,note:'Relevé vérifié'}],['exchange',{amount:90,targetCurrency:'USD',targetAmount:100}]]){
  await open();await page.locator(`[data-kind="${['deposit','withdrawal'].includes(kind)?'deposit':'dividend'}"]`).click();await page.locator('[name=type]').selectOption(kind);
  if(['dividend','split','adjustment'].includes(kind))await choose('TEST');
  if(['deposit','withdrawal','exchange'].includes(kind))await enter('currency','EUR');
  for(const [key,value] of Object.entries(values))await enter(key,value);
  assert.equal(await page.locator('[name=price]').count(),0);await save();
 }
 // Opening position records no purchase and no cash movement.
 await page.locator('#portfolio').selectOption('empty');await open();await page.locator('[data-kind=dividend]').click();await page.locator('[name=type]').selectOption('opening');await choose('TEST');
 assert.equal(await page.locator('[name=price]').inputValue(),'');await enter('quantity',10);await enter('price',95);await save();
 current=await state();assert.equal(current.data.transactions.filter(t=>t.portfolioId==='empty')[0].type,'opening');
 await page.locator('[data-page="Dashboard"]').click();await page.waitForFunction(()=>document.querySelector('#historyChart')?.textContent.includes('Historique incomplet'));
 // Recognized CSV skips manual columns; mappings confirmed once are reused on subsequent files.
 await page.locator('#portfolio').selectOption('p');await page.locator('[data-page="Portefeuilles"]').first().click();
 const csv=(id,action='Market buy')=>`Action,Time,ID,Ticker,No. of shares,Price / share,Currency (Price / share),Total (EUR)\n${action},2026-11-16 10:00:00,${id},TEST,1,100,EUR,100\n`;
 const upload=async content=>{await page.locator('#import').click();await page.locator('[name=file]').setInputFiles({name:'history.csv',mimeType:'text/csv',buffer:Buffer.from(content)});await page.locator('#next').click();await page.waitForFunction(()=>!document.querySelector('#modal h2')?.textContent.includes('1/4')||document.querySelector('#error')?.textContent.length>0)};
 let before=await snapshot();await upload(csv('one'));assert.match(await page.locator('#modal').textContent(),/Mapping automatique/);assert.equal(await page.locator('select[name=date]').count(),0);
 await page.locator('#next').click();await cancel();assert.equal(await snapshot(),before);
 await upload(csv('one'));await page.locator('#next').click();await page.locator('#confirm').click();await page.waitForFunction(()=>!document.querySelector('#modal').open);
 await upload(csv('two'));assert.equal(await page.locator('[name=symbol0]').count(),0);assert.match(await page.locator('#modal').textContent(),/précédemment validée/);await page.locator('#recheckSymbols').click();assert.equal(await page.locator('[name=symbol0]').count(),1);await cancel();
 // Duplicate IDs and unsupported operations never result in partial imports.
 before=await snapshot();await upload(csv('one'));await page.locator('#next').click();assert.match(await page.locator('#error').textContent(),/déjà importé/);await cancel();assert.equal(await snapshot(),before);
 await upload(csv('unknown','Unknown action'));assert.match(await page.locator('#error').textContent(),/non prise en charge/);await cancel();assert.equal(await snapshot(),before);
 await upload(csv('fee').replace('Total (EUR)','Total (EUR),Unexpected fee (EUR)').replace('EUR,100\n','EUR,100,1\n'));assert.match(await page.locator('#error').textContent(),/non pris en charge/);await cancel();assert.equal(await snapshot(),before);
 // Unknown formats retain the advanced manual mapping screen.
 await upload('date,type,amount,currency\n2026-11-16,deposit,12,EUR\n');assert.equal(await page.locator('select[name=date]').count(),1);await cancel();
 // The compact mobile dialog remains usable without horizontal overflow.
 await page.setViewportSize({width:390,height:844});await open();await choose('TEST');await enter('quantity',1);await enter('price',100);
 assert.equal(await page.locator('#modal').evaluate(d=>d.scrollWidth<=d.clientWidth),true);await page.locator('#reviewTransaction').click();await cancel();
 assert.deepEqual(errors,[]);console.log('Transaction browser: purchases, dated sales, edits, cash, dividends, splits, corrections, FX, opening positions, imports, reuse, duplicates and cancellation passed.');
}finally{
 await browser?.close();if(child?.exitCode===null){const done=once(child,'exit');child.kill('SIGTERM');await done}await rm(directory,{recursive:true,force:true});
}
