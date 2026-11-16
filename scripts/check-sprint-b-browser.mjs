import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {once} from 'node:events';import {mkdtemp,rm} from 'node:fs/promises';import {tmpdir} from 'node:os';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createInterface} from 'node:readline';import {chromium} from 'playwright-core';
const root=fileURLToPath(new URL('..',import.meta.url)),dir=await mkdtemp(path.join(tmpdir(),'atlas-sprint-b-'));let server,browser;
try{
 server=spawn(process.env.ATLAS_PYTHON||path.join(root,'.venv/bin/python'),['tests/browser_phase2_fixture.py'],{cwd:root,env:{...process.env,ATLAS_DB:path.join(dir,'atlas.sqlite3'),ATLAS_BROWSER_FIXTURE_DIR:dir},stdio:['ignore','pipe','pipe']});let logs='';server.stderr.on('data',b=>logs+=b.toString());
 const url=await Promise.race([once(createInterface({input:server.stdout}),'line').then(([s])=>JSON.parse(s).url),once(server,'exit').then(()=>{throw Error(logs)})]);
 browser=await chromium.launch({executablePath:process.env.ATLAS_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url);await page.locator('.nav[data-page="Settings"]').click();await page.locator('#syncAll').click();await page.locator('#syncStatus').getByText('2 cours actualisé(s)',{exact:false}).waitFor();
 await page.locator('.nav[data-page="Portefeuilles"]').click();const date=new Date().toISOString().slice(0,10),year=Number(date.slice(0,4))-1;
 const csv=`type,from,asOf,positionsComplete,cashComplete,ticker,quantity,averageEUR,valueEUR,currency,amount\nmeta,${year}-01-01,${date},true,true,,,,,,\nposition,,,,,SYNTHCO,11,10,200,,\ncash,,,,,,,,,EUR,1900\nfees_none,,,,,,,,,,\ndividends_none,,,,,,,,,,`;
 await page.locator('#brokerFile').setInputFiles({name:'releve.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});await page.locator('#reconcile').click();await page.locator('#reconcileResult').getByText('Écart',{exact:false}).first().waitFor();assert.match(await page.locator('#reconcileResult').textContent(),/Quantité/);assert.deepEqual(errors,[]);
 console.log('PASS: synchronisation des titres et rapprochement CSV avec signalement d’un écart.');
}finally{if(browser)await browser.close();if(server){server.kill();await once(server,'exit').catch(()=>{})}await rm(dir,{recursive:true,force:true})}
