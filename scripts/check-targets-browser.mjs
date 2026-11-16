// Disposable synthetic fixture; no user database or external provider.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('..',import.meta.url));
const dir=await mkdtemp(path.join(tmpdir(),'atlas-allocation-browser-'));
let server,browser;
try {
 server=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_history_fixture.py'],{cwd:root,env:{...process.env,ATLAS_DB:path.join(dir,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:dir},stdio:['ignore','pipe','pipe']});
 const lines=createInterface({input:server.stdout});
 const url=await Promise.race([once(lines,'line').then(([s])=>JSON.parse(s).url),once(server,'exit').then(([code])=>{throw Error('Fixture exited '+code)}),once(server,'error').then(([error])=>{throw error})]);
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url); await page.locator('.nav[data-page="Portefeuilles"]').click();
 await page.locator('#addTarget').click();
 const row=page.locator('[data-target-row]').first();
 await row.locator('[data-field="key"]').fill('ABC');
 await row.locator('[data-field="min"]').fill('10');
 await row.locator('[data-field="target"]').fill('50');
 await row.locator('[data-field="max"]').fill('80');
 await page.locator('#targetBasis').selectOption('total');
 await page.locator('#saveTargets').click();
 await page.getByText('Cibles enregistrées.').waitFor();
 const selected=await page.locator('#portfolio').inputValue();
 const saved=await (await page.request.get(url+'/api/portfolio/targets?portfolioId='+encodeURIComponent(selected))).json();
 assert.equal(saved.basis,'total');assert.equal(saved.targets[0].target,.5);
 await page.reload();await page.locator('.nav[data-page="Portefeuilles"]').click();
 await page.locator('[data-target-row]').waitFor();
 assert.equal(await page.locator('[data-field="key"]').inputValue(),'ABC');
 await page.locator('#portfolio').selectOption('stale');
 await page.locator('#addTarget').waitFor();
 assert.equal(await page.locator('[data-target-row]').count(),0);
 await page.locator('#portfolio').selectOption(selected);
 await page.locator('[data-target-row]').waitFor();
 await page.locator('[data-field="min"]').fill('90');
 await page.locator('#saveTargets').click();
 await page.locator('#targetStatus').getByText(/bornes/).waitFor();
 const invalid=await page.request.put(url+'/api/portfolio/targets',{data:{...saved,targets:[{...saved.targets[0],target:2}]}});
 assert.equal(invalid.status(),400);
 assert.deepEqual(errors,[]);
 console.log('PASS: portfolio targets editor, persistence, isolation and API validation.');
} finally {
 if(browser)await browser.close();
 if(server&&server.exitCode===null){const stopped=once(server,'exit');server.kill('SIGTERM');await stopped}
 await rm(dir,{recursive:true,force:true});
}
