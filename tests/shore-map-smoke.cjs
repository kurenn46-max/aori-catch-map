const { chromium, devices } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
(async () => {
  fs.mkdirSync('test-results',{recursive:true});
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({...devices['Pixel 7'],locale:'ja-JP',timezoneId:'Asia/Tokyo',permissions:['geolocation'],geolocation:{latitude:35.513,longitude:135.754}});
  const page = await context.newPage();
  const errors=[], resources=[], failures=[];
  page.on('pageerror',e => errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text());});
  page.on('response',r=>{if(/(cyberjapandata\.gsi\.go\.jp|unpkg\.com|jsdelivr\.net)/.test(r.url()))resources.push({status:r.status(),url:r.url()});});
  page.on('requestfailed',r=>{if(/(cyberjapandata\.gsi\.go\.jp|unpkg\.com|jsdelivr\.net)/.test(r.url()))failures.push({url:r.url(),error:r.failure()?.errorText});});
  async function snap(name){await page.screenshot({path:'test-results/'+name+'.png',fullPage:true,animations:'disabled'});}
  const report={checks:[],errors,resources,failures};
  async function check(name,fn){try{let ret=await fn();report.checks.push({name,result:'PASS',details:ret||''});}catch(e){report.checks.push({name,result:'FAIL',details:e.message}); await snap('FAIL-'+report.checks.length);}}
  try{
    await page.goto('http://127.0.0.1:8765/shore-map/',{waitUntil:'domcontentloaded',timeout:30000});
    await page.waitForTimeout(3000);
    await check('Leaflet loads and map initializes',async()=>{
      await page.waitForFunction(()=>typeof L!=='undefined' && document.querySelector('.leaflet-container'),{timeout:20000});
      assert.equal(await page.locator('#fallback').evaluate(e=>getComputedStyle(e).display==='none'),true);
    });
    await check('Real GSI map photo and basemap tile load',async()=>{
      await page.waitForFunction(()=>[...document.querySelectorAll('#map img.leaflet-tile')].some(im=>im.complete && im.naturalWidth>0),{timeout:25000});
      return await page.locator('#map img.leaflet-tile').evaluateAll(a=>a.filter(im=>im.complete&&im.naturalWidth>0).length+' tiles loaded');
    });
    await check('Map dominates mobile viewport',async()=>{
      const dim=await page.locator('#map').boundingBox();
      assert(dim&&dim.width>350&&dim.height>750,'map bounding box too small');
      return JSON.stringify(dim);
    });
    await snap('initial');
    await check('Photo/standard toggle',async()=>{
      await page.locator('#base').click();assert.equal(await page.locator('#base').innerText(),'地図');
      await page.locator('#base').click();assert.equal(await page.locator('#base').innerText(),'写真');
    });
    await check('Zoom',async()=>{await page.locator('#zoomIn').click();await page.locator('#zoomOut').click();});
    await check('Select shore and 300m/1km',async()=>{
      await page.locator('#map').click({position:{x:130,y:350}});
      await page.locator('button[data-range="300"]').click();
      await page.locator('button[data-range="1000"]').click();
      assert.match(await page.locator('#distance').innerText(),/1\.00km|1km/);
    });
    await check('Nearshore coastal layer toggle',async()=>{await page.locator('#coast').click();assert(await page.locator('#coast').evaluate(e=>e.classList.contains('active')));await page.locator('#coast').click();});
    await check('Map tap distance',async()=>{await page.locator('#map').click({position:{x:170,y:400}});assert.match(await page.locator('#distance').innerText(),/岸から/);});
    await check('Depth form, saving and listing',async()=>{
      await page.locator('#addDepth').click();
      const dialog=page.locator('#sheet');
      assert.equal(await dialog.isVisible(),true);
      await dialog.locator('input[type=number]').fill('8.5');
      await dialog.getByRole('button',{name:'この地点を保存'}).click();
      await page.locator('#listPoints').click();
      assert.match(await page.locator('#sheetBody').innerText(),/8\.5m/);
      await page.locator('#close').click();
    });
    await check('Region change and GPS',async()=>{await page.locator('#region').selectOption('maizuru');await page.locator('#gps').click();});
    await snap('end');
    await check('No JavaScript runtime errors',async()=>{assert.deepEqual(errors,[]);});
    fs.writeFileSync('test-results/results.json',JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
    const fail=report.checks.filter(x=>x.result==='FAIL');
    if(fail.length){console.error('FAILED:',fail.map(x=>x.name).join(', '));process.exitCode=1;}else console.log('ALL_BROWSER_TESTS_PASS');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});