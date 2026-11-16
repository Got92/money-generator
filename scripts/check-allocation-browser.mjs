// Disposable synthetic fixture; no user database or external provider.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('..',import.meta.url));
const dir=await mkdtemp('/workspace/work/atlas-allocation-browser-');
let server,browser;
try {
 server=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_history_fixture.py'],{cwd:root,env:{...process.env,ATLAS_DB:path.join(dir,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:dir},stdio:['ignore','pipe','pipe']});
 const lines=createInterface({input:server.stdout});
 const url=await Promise.race([once(lines,'line').then(([s])=>JSON.parse(s).url),once(server,'exit').then(([code])=>{throw Error('Fixture exited '+code)})]);
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);await page.locator('#historyChart svg').waitFor();
 const before=await (await page.request.get(url+'/api/state')).json();
 assert.match(await page.locator('.allocation-card').textContent(),/Non renseigné/);
 assert.match(await page.locator('.allocation-card').textContent(),/100\.0 %/);
 await page.locator('[data-page="Analytics & Risk"]').click();
 assert.equal(await page.locator('#allocationBasis').inputValue(),'invested');
 assert.match(await page.locator('main').textContent(),/Allocation par industrie/);
 assert.match(await page.locator('main').textContent(),/Allocation par classe d’actifs/);
 await page.locator('#allocationBasis').selectOption('total');
 const cards=page.locator('.grid .card');
 assert.match(await cards.nth(0).textContent(),/Liquidités/);
 assert.match(await cards.nth(0).textContent(),/52\.4 %/);
 assert.match(await cards.nth(2).textContent(),/USD/);
 await page.locator('#allocationBasis').selectOption('invested');
 assert.doesNotMatch(await cards.nth(0).textContent(),/Liquidités/);
 await page.locator('#portfolio').selectOption('stale');
 assert.match(await cards.nth(0).textContent(),/indisponible/);
 await page.locator('[data-page="Dashboard"]').click();
 assert.match(await page.locator('.allocation-card').textContent(),/indisponible/);
 assert.equal((await (await page.request.get(url+'/api/state')).json()).revision,before.revision);
 assert.deepEqual(errors,[]);
 console.log('PASS: dashboard, Analytics, invested/cash denominator, unknown and missing valuations; no state writes.');
} finally {
 if(browser)await browser.close();
 if(server&&server.exitCode===null){const stopped=once(server,'exit');server.kill('SIGTERM');await stopped}
 await rm(dir,{recursive:true,force:true});
}
