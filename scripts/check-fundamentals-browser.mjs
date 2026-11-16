import {chromium} from 'playwright-core';
import {spawn} from 'node:child_process';
import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const dir=mkdtempSync(join(tmpdir(),'atlas-fundamental-browser-'));
const port=18400+Math.floor(Math.random()*1000);
const server=spawn('.venv/bin/python',['server.py'],{env:{...process.env,ATLAS_DB:join(dir,'test.sqlite'),PORT:String(port)},stdio:'ignore'});
let browser, spawnError;
server.on('error',error=>{spawnError=error});
try {
  let ready=false;
  for(let n=0;n<100;n++){if(spawnError)throw spawnError;if(server.exitCode!==null)throw Error(`Server exited: ${server.exitCode}`);try{await fetch(`http://127.0.0.1:${port}/`);ready=true;break}catch{await new Promise(r=>setTimeout(r,100))}}
  if(!ready)throw Error('Server did not start');
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
  const page=await browser.newPage();
  await page.route('**/api/fundamentals/history?*',async route=>{
    const url=new URL(route.request().url()); const quarterly=url.searchParams.get('period')==='quarterly';
    await route.fulfill({json:{period:quarterly?'quarterly':'annual',coverage:{periodEnds:quarterly?[]:['2023-12-31'],firstPeriodEnd:'2023-12-31',lastPeriodEnd:'2023-12-31',byPeriod:quarterly?[]:[{periodEnd:'2023-12-31',missingMetrics:['gross_profit']}]},fetch:{error:quarterly?'Quota':null},data:quarterly?[]:[{periodEnd:'2023-12-31',statement:'income',metric:'revenue',value:100,currency:'USD',unit:'currency',source:'Fixture',fetchedAt:'2024-02-01'}]}});
  });
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.evaluate(async()=>{
    document.body.innerHTML='<section id="fundamentalHistory" data-symbol="IBM"><select id="fundamentalPeriod"><option value="annual">Annual</option><option value="quarterly">Quarterly</option></select><button id="loadFundamentals">Load</button><button id="refreshFundamentals">Refresh</button><button id="downloadFundamentals" disabled>Download</button><div id="fundamentalResult"></div></section>';
    const {wireFundamentals}=await import('/src/fundamental-ui.js');wireFundamentals();
  });
  await page.click('#loadFundamentals'); await page.waitForSelector('text=Chiffre d’affaires');
  assert.equal(await page.locator('#downloadFundamentals').isDisabled(),false);
  assert.match(await page.locator('#fundamentalResult').innerText(),/2023-12-31/);
  assert.match(await page.locator('#fundamentalResult').innerText(),/métadonnées actuelles/);
  await page.locator('summary').click();
  assert.match(await page.locator('#fundamentalResult').innerText(),/Marge brute/);
  await page.selectOption('#fundamentalPeriod','quarterly');
  assert.equal(await page.locator('#downloadFundamentals').isDisabled(),true);
  await page.click('#refreshFundamentals'); await page.waitForSelector('text=Quota');
  assert.match(await page.locator('#fundamentalResult').innerText(),/Aucune donnée disponible/);
  console.log('PASS: annual coverage, download, period change, empty and provider error states');
} finally {if(browser)await browser.close();server.kill();rmSync(dir,{recursive:true,force:true});}
