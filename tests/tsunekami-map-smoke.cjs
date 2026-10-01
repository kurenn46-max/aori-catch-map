const {chromium,devices}=require('playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 fs.mkdirSync('test-results/tsunekami',{recursive:true});
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({...devices['Pixel 7'],locale:'ja-JP',timezoneId:'Asia/Tokyo',permissions:['geolocation'],geolocation:{latitude:35.633,longitude:135.82}});
 const page=await context.newPage(),errors=[],failures=[],checks=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('response',r=>{if(/tsunekami-map\/(contours.geojson|coarse.json|shallow.js)/.test(r.url())&&r.status()!==200)failures.push(r.url()+' '+r.status());});
 page.on('requestfailed',r=>{if(/tsunekami-map\/(contours.geojson|coarse.json)/.test(r.url()))failures.push(r.url()+' '+r.failure()?.errorText);});
 async function ck(name,fn){try{let extra=await fn();checks.push({name,result:'PASS',extra:extra||''});}catch(e){checks.push({name,result:'FAIL',error:e.stack||String(e)});await page.screenshot({path:'test-results/tsunekami/FAIL-'+checks.length+'.png'});}}
 try{
  await page.goto(process.env.TEST_URL||'http://127.0.0.1:8765/tsunekami-map/',{waitUntil:'domcontentloaded',timeout:40000});
  await ck('Map starts and official depth files load',async()=>{
    await page.waitForFunction(()=>window.__tsunekamiTest?.dataReady,{timeout:30000});
    const x=await page.evaluate(()=>window.__tsunekamiTest);
    assert.equal(x.started,true);assert.equal(x.shallowReady,true,'private shallow module missing');assert(x.contoursLoaded>=2,'No official contour features');assert(x.depthValues.includes(20)&&x.depthValues.includes(50),'Missing true 20/50m contour');assert(x.modelNodes>=30,'Model unavailable');assert.equal(x.errors.length,0,'App data errors: '+x.errors);return JSON.stringify(x);
  });
  await ck('GSI imagery actually displays',async()=>{
    await page.waitForFunction(()=>[...document.querySelectorAll('img.leaflet-tile')].some(x=>x.complete&&x.naturalWidth>0),{timeout:30000});return 'real image pixels loaded';
  });
  await ck('Mobile screen shows all five bottom controls without overflow',async()=>{
    const v=page.viewportSize();for(const id of ['top','map','foot','coarse','pick']){let b=await page.locator('#'+id).boundingBox();assert(b,'missing '+id);assert(b.x>=-1&&b.x+b.width<=v.width+1,'clipped '+id+' '+JSON.stringify(b));}return JSON.stringify(v);
  });
  await ck('20m and 50m labels really drawn',async()=>{
    const counts=await page.locator('.label-depth').count();assert(counts>=2,'no visible official contour labels');return counts+' labels';
  });
  await page.screenshot({path:'test-results/tsunekami/01-tsunekami.png',fullPage:true});
  await ck('All four subareas switch and official depth stays loaded',async()=>{
    for(const z of ['miko','ogawa','yushi','tsunekami']){await page.locator('#area').selectOption(z);await page.waitForTimeout(400);assert.equal(await page.locator('#area').inputValue(),z);assert.equal(await page.evaluate(()=>window.__tsunekamiTest.contoursLoaded>=2),true);}
  });
  await ck('Switch 300m/500m/1km',async()=>{
    for(const m of [500,1000,300]){await page.locator('[data-range="'+m+'"]').click();assert.equal(await page.locator('[data-range="'+m+'"]').evaluate(e=>e.classList.contains('on')),true);}
  });
  await ck('No fake shallow depths are preloaded',async()=>{
    const n=await page.evaluate(()=>window.TsunekamiShallow.count());assert.equal(n,0);
    assert.equal(await page.locator('.depth-private').count(),0);
  });
  await ck('Private 2m/5m/10m GeoJSON import needs permission and displays actual file values',async()=>{
    await page.locator('#coarse').click();
    const f=page.locator('#shallowFile');assert.equal(await f.isDisabled(),true);
    await page.locator('#shallowConsent').check();assert.equal(await f.isDisabled(),false);
    const fixture={type:'FeatureCollection',features:[
      {type:'Feature',properties:{depth_m:2},geometry:{type:'LineString',coordinates:[[135.820,35.637],[135.821,35.637]]}},
      {type:'Feature',properties:{depth_m:5},geometry:{type:'LineString',coordinates:[[135.821,35.6373],[135.8215,35.6373]]}},
      {type:'Feature',properties:{depth_m:10},geometry:{type:'LineString',coordinates:[[135.8208,35.6375],[135.8213,35.6375]]}},
      {type:'Feature',properties:{depth_m:8.5},geometry:{type:'Point',coordinates:[135.8205,35.6372]}}
    ]};
    await f.setInputFiles({name:'TEST_ONLY_FAKE_CONTOURS.geojson',mimeType:'application/geo+json',buffer:Buffer.from(JSON.stringify(fixture))});
    await page.waitForFunction(()=>window.TsunekamiShallow.count()===4,{timeout:7000});
    assert.match(await page.locator('#shallowCount').innerText(),/4件/);
    const layers=await page.locator('.depth-private').count();assert.equal(layers,4,'all four locally imported shapes must render');
    await page.locator('#close').click();return 'only generated fixture imported locally in test browser';
  });
  await ck('Private import persists within same browser and can be deleted',async()=>{
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>window.__tsunekamiTest?.dataReady && window.__tsunekamiTest.shallowReady,{timeout:30000});
    assert.equal(await page.evaluate(()=>window.TsunekamiShallow.count()),4);
    await page.locator('#coarse').click();
    page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'端末内の水深データを削除'}).click();
    await page.waitForFunction(()=>window.TsunekamiShallow.count()===0,{timeout:5000});
    await page.locator('#close').click();
  });
  await ck('Estimated depths can be shown only through a separate clearly labelled action',async()=>{
    await page.locator('#coarse').click();
    await page.getByRole('button',{name:'沖側の概算水深を切り替える'}).click();
    assert(await page.locator('.coarsepin').count()>10,'coarse data labels absent');
    assert.match(await page.locator('.coarsepin').first().innerText(),/約/);
    await page.getByRole('button',{name:'沖側の概算水深を切り替える'}).click();
    await page.locator('#close').click();
  });
  await ck('Photo/standard switch',async()=>{
    await page.locator('#base').click();assert.equal(await page.locator('#base').innerText(),'標準地図');await page.locator('#base').click();assert.equal(await page.locator('#base').innerText(),'航空写真');
  });
  await ck('Tapping map shows distance without inventing exact local depth',async()=>{
    await page.locator('#map').click({position:{x:190,y:480}});await page.waitForTimeout(250);
    const s=await page.locator('.leaflet-popup-content').innerText();assert.match(s,/正確な水深は未取得/);assert.match(s,/釣り座から/);
  });
  await ck('Shore can be changed and map remains interactive',async()=>{
    await page.locator('#pick').click();await page.locator('#map').click({position:{x:180,y:460}});assert.equal(await page.locator('#pick').evaluate(e=>e.classList.contains('on')),false);
  });
  await ck('Sources and limitations are accessible',async()=>{
    await page.locator('#info').click();assert.match(await page.locator('#details').innerText(),/20m・50m/);assert.match(await page.locator('#details').innerText(),/実測値ではない/);await page.locator('#close').click();
  });
  await ck('No runtime/data request errors',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);});
  await page.screenshot({path:'test-results/tsunekami/02-final.png',fullPage:true});
  const report={checks,errors,failures};fs.writeFileSync('test-results/tsunekami/report.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  if(checks.some(c=>c.result==='FAIL'))process.exitCode=1;else console.log('TSUNEKAMI_REAL_CONTOURS_TEST_PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});