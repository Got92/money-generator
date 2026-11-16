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
 await page.goto(url);await page.locator('#historyChart svg').waitFor();
 const before=await (await page.request.get(url+'/api/state')).json();
 await page.locator('[data-reinforcement="FIXTURE"]').first().click();
 await page.locator('#reinforcementForm [name=size]').fill('210');
 await page.locator('#reinforcementForm [name=fee]').fill('10');
 await page.locator('#reinforcementForm [name=price]').fill('100');
 await page.locator('#reinforcementForm button[type=submit], #reinforcementForm button.primary').click();
 await page.locator('#reinforcementResult').getByText(/Quantité/).waitFor();
 assert.match(await page.locator('#reinforcementResult').textContent(),/achat 2/);
 assert.match(await page.locator('#reinforcementResult').textContent(),/prix hypothétique : 100 USD/);
 assert.match(await page.locator('#reinforcementResult').textContent(),/Cibles : Service indisponible/);
 assert.match(await page.locator('#reinforcementResult').textContent(),/hors frais et dividendes/);
 await page.route('**/api/portfolio/targets?*',route=>route.fulfill({json:{portfolioId:'gap',basis:'invested',targets:[]}}));
 await page.route('**/api/valuation/scenarios?*',route=>route.fulfill({json:{symbol:'FIXTURE',scenarios:[]}}));
 await page.locator('#reinforcementForm .close').click();
 await page.locator('[data-company="FIXTURE"]').first().click();
 await page.locator('[data-reinforcement="FIXTURE"]').click();
 await page.locator('#reinforcementForm [name=portfolioId]').selectOption('gap');
 await page.locator('#reinforcementForm [name=mode]').selectOption('quantity');
 await page.locator('#reinforcementForm [name=size]').fill('1');
 await page.locator('#reinforcementForm button.primary').click();
 await page.locator('#reinforcementResult').getByText(/Quantité/).waitFor();
 assert.match(await page.locator('#reinforcementResult').textContent(),/Aucune cible enregistrée/);
 assert.match(await page.locator('#reinforcementResult').textContent(),/Aucun scénario enregistré/);
 const after=await (await page.request.get(url+'/api/state')).json();
 assert.deepEqual(after,before);assert.deepEqual(errors,[]);
 console.log('PASS: position and company navigation, portfolio selection, simulations preserve state and revision.');
} finally {
 if(browser)await browser.close();
 if(server&&server.exitCode===null){const stopped=once(server,'exit');server.kill('SIGTERM');await stopped}
 await rm(dir,{recursive:true,force:true});
}
