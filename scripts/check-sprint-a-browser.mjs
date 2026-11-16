import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('..',import.meta.url)), dir=await mkdtemp(path.join(tmpdir(),'atlas-sprint-a-'));
let server,browser;
try{
 server=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_phase2_fixture.py'],{cwd:root,env:{...process.env,ATLAS_DB:path.join(dir,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:dir},stdio:['ignore','pipe','pipe']});
 let logs='';server.stderr.on('data',b=>logs+=b.toString());
 const url=await Promise.race([once(createInterface({input:server.stdout}),'line').then(([s])=>JSON.parse(s).url),once(server,'exit').then(()=>{throw Error(logs)})]);
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);await page.locator('.nav[data-page="Portefeuilles"]').click();
 await page.locator('#addTx').click();await page.locator('#modal [name=type]').selectOption('split');
 await page.locator('#modal [name=date]').fill('2030-01-01');await page.locator('#modal [name=ticker]').fill('SYNTHCO');await page.locator('#modal [name=ratio]').fill('2');await page.locator('#modal [name=note]').fill('Split 2:1');
 await page.locator('#modal button[value=save]').click();await page.locator('#modal').waitFor({state:'hidden'});
 assert.ok(await page.getByText('Split / regroupement').count());
 await page.locator('[data-page="Settings"]').click();const [download]=await Promise.all([page.waitForEvent('download'),page.getByText('Exporter la base SQLite complète').click()]);
 const file=path.join(dir,'export.sqlite3');await download.saveAs(file);
 page.once('dialog',dialog=>dialog.accept());const chooser=page.waitForEvent('filechooser');await page.locator('#restoreDb').click();const response=page.waitForResponse(r=>r.url().endsWith('/api/backup/restore'));const navigation=page.waitForNavigation();await (await chooser).setFiles(file);assert.equal((await response).status(),200);await navigation;await page.locator('.nav[data-page="Portefeuilles"]').click();assert.ok(await page.getByText('Split / regroupement').count());assert.deepEqual(errors,[]);
 console.log('PASS: saisie et historique du split, téléchargement et restauration SQLite en navigateur.');
}finally{if(browser)await browser.close();if(server){server.kill();await once(server,'exit').catch(()=>{})}await rm(dir,{recursive:true,force:true})}
