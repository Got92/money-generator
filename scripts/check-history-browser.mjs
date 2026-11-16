// Offline integration check. No user database or external provider is accessed.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const root=fileURLToPath(new URL('..',import.meta.url));
const directory=await mkdtemp(path.join(tmpdir(),'atlas-browser-'));
let child,browser;
const errors=[];
async function startServer(){
 child=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_history_fixture.py'],{
  cwd:root,env:{...process.env,ATLAS_DB:path.join(directory,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:directory},stdio:['ignore','pipe','pipe']
 });
 child.stderr.on('data',chunk=>{if(chunk.toString().includes('Traceback'))process.stderr.write(chunk)});
 const lines=createInterface({input:child.stdout});
 return await Promise.race([
  once(lines,'line').then(([line])=>JSON.parse(line).url),
  once(child,'exit').then(([code])=>{throw Error('Fixture server exited: '+code)}),
  once(child,'error').then(([error])=>{throw error})
 ]);
}
async function stopServer(){const exited=once(child,'exit');child.kill('SIGTERM');await exited}
async function counts(){return JSON.parse(await readFile(path.join(directory,'counts.json'),'utf8'))}
try{
 let url=await startServer();
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(10000);
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);
 await page.locator('#historyChart svg').waitFor();
 assert.match(await page.locator('#historyStatus').textContent(),/observations/);
 assert.deepEqual(await counts(),{prices:1,fx:1});
 const initial=await (await page.request.get(url+'/api/state')).json();

 await page.reload();
 await page.locator('#historyChart svg').waitFor();
 assert.deepEqual(await counts(),{prices:1,fx:1});
 const second=await browser.newPage();
 await second.goto(url);
 await second.locator('#historyChart svg').waitFor();
 assert.deepEqual(await counts(),{prices:1,fx:1});
 await second.close();

 // A real server-process restart must reuse SQLite without calling either provider.
 await stopServer();
 url=await startServer();
 await page.goto(url);
 await page.locator('#historyChart svg').waitFor();
 assert.deepEqual(await counts(),{prices:1,fx:1});

 const oldTotal=await page.locator('.stats .stat strong').first().textContent();
 await writeFile(path.join(directory,'new-rate'),'1');
 await page.locator('#refreshHistory').click();
 await page.waitForFunction(old=>document.querySelector('.stats .stat strong')?.textContent!==old,oldTotal);
 await page.locator('#historyChart svg').waitFor();
 assert.deepEqual(await counts(),{prices:2,fx:2});

 await writeFile(path.join(directory,'offline'),'1');
 await page.locator('#refreshHistory').click();
 await page.waitForFunction(()=>document.querySelector('#historyStatus')?.textContent.includes('Panne de test'));
 await page.locator('#historyChart svg').waitFor();
 assert.match(await page.locator('#historyStatus').textContent(),/fraîcheur non confirmée/);
 assert.deepEqual(await counts(),{prices:3,fx:3});

 await page.locator('[data-page="Settings"]').click();
 await page.locator('#refreshFx').click();
 await page.waitForFunction(()=>document.querySelector('#fxStatus')?.textContent.includes('Panne de test'));
 assert.match(await page.locator('#fxStatus').textContent(),/fraîcheur non confirmée/);

 await page.locator('#addTx').click();
 await page.locator('#modal [name="type"]').selectOption('deposit');
 await page.locator('#modal [name="amount"]').fill('10');
 await page.locator('#modal [value="save"]').click();
 await page.waitForFunction(()=>!document.querySelector('#modal')?.open);
 const saved=await (await page.request.get(url+'/api/state')).json();
 assert.equal(saved.revision,initial.revision+1);
 assert.equal(saved.data.transactions.length,initial.data.transactions.length+1);
 const history=await (await page.request.get(url+'/api/market/history?symbol=FIXTURE')).json();
 const rates=await (await page.request.get(url+'/api/market/fx?from=USD&to=EUR')).json();
 assert(history.data.length>1&&rates.data.length>1);
 assert.equal(history.cache.status,'stale');
 assert.deepEqual(errors,[]);
 console.log('PASS: chargement, rechargement, nouvel onglet, redémarrage serveur, taux corrigé et valorisation actualisée, panne cours/change, avertissements et sauvegarde sans purge.');
}finally{
 if(browser)await browser.close();
 if(child&&child.exitCode===null)await stopServer();
 await rm(directory,{recursive:true,force:true});
}
