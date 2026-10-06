const { chromium, devices } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');

function hourlyTimes(){
  const out=[]; const d=new Date('2026-10-05T00:00:00+09:00');
  for(let day=0;day<3;day++) for(let h=0;h<24;h++){
    const dd=new Date(d); dd.setDate(dd.getDate()+day); dd.setHours(h,0,0,0);
    const y=dd.getFullYear(),m=String(dd.getMonth()+1).padStart(2,'0'),da=String(dd.getDate()).padStart(2,'0');
    out.push(`${y}-${m}-${da}T${String(h).padStart(2,'0')}:00`);
  }
  return out;
}
const times=hourlyTimes();
const weatherBody={
  current:{time:'2026-10-05T19:00',wind_speed_10m:3.2,wind_direction_10m:320,wind_gusts_10m:5.5,precipitation:0},
  hourly:{time:times,wind_speed_10m:times.map(()=>3.2),wind_direction_10m:times.map(()=>320),wind_gusts_10m:times.map(()=>5.5),precipitation:times.map(()=>0)},
  daily:{time:['2026-10-05','2026-10-06','2026-10-07'],sunrise:['2026-10-05T05:55','2026-10-06T05:56','2026-10-07T05:57'],sunset:['2026-10-05T17:38','2026-10-06T17:36','2026-10-07T17:35']}
};
const marineBody={
  current:{time:'2026-10-05T19:00',wave_height:0.35,swell_wave_height:0.2,sea_surface_temperature:24.1,sea_level_height_msl:0.18,ocean_current_velocity:0.7},
  hourly:{time:times,wave_height:times.map(()=>0.35),swell_wave_height:times.map(()=>0.2),sea_surface_temperature:times.map((_,i)=>23.8+(i%24)*0.01)}
};

(async()=>{
  fs.mkdirSync('test-results',{recursive:true});
  const browser=await chromium.launch({headless:true});
  const report={checks:[]};
  async function withPage(optionalFailure=false,apiDelayMs=0){
    const context=await browser.newContext({...devices['Pixel 7'],locale:'ja-JP',timezoneId:'Asia/Tokyo'});
    const page=await context.newPage();
    const errors=[];
    const requests=[];
    page.on('request',r=>requests.push(r.url()));
    page.on('pageerror',e=>errors.push(String(e)));
    page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text());});
    await page.route('https://api.open-meteo.com/**',async r=>{
      if(apiDelayMs)await new Promise(resolve=>setTimeout(resolve,apiDelayMs));
      await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(weatherBody)});
    });
    await page.route('https://marine-api.open-meteo.com/**',async r=>{
      if(apiDelayMs)await new Promise(resolve=>setTimeout(resolve,apiDelayMs));
      await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(marineBody)});
    });
    if(optionalFailure) await page.route('**/data/strategy.json*',r=>r.abort());
    return {context,page,errors,requests};
  }
  async function check(name,fn){try{const d=await fn();report.checks.push({name,result:'PASS',details:d||''});}catch(e){report.checks.push({name,result:'FAIL',details:e.message});}}

  const base=process.env.TEST_URL||'http://127.0.0.1:8765/';
  const {context,page,errors,requests}=await withPage(false);
  try{
    await page.goto(base,{waitUntil:'domcontentloaded',timeout:30000});
    await page.waitForFunction(()=>document.querySelector('#spotCount')?.textContent!=='0',{timeout:20000});

    await check('Main catch map loads on Pixel 7',async()=>{
      assert(await page.locator('.leaflet-container').count(), 'Leaflet map missing');
      const leafletSrc=await page.locator('script[src*="leaflet"]').getAttribute('src');
      assert(leafletSrc && leafletSrc.startsWith('./assets/'),'Leaflet is not local: '+leafletSrc);
      const n=Number(await page.locator('#spotCount').innerText());
      assert(n>0,'catch rows did not render');
      return n+' rows visible';
    });

    await check('Map remains useful size on mobile',async()=>{
      const box=await page.locator('#map').boundingBox();
      assert(box && box.width>=390 && box.height>=300, 'map too small: '+JSON.stringify(box));
      return JSON.stringify(box);
    });

    await check('Filters work without page reload',async()=>{
      await page.locator('#dateRow button[data-range="today"]').click();
      const today=await page.locator('#status').innerText();
      assert.match(today,/今日/);
      await page.locator('#area').selectOption({label:'敦賀'});
      assert.match(await page.locator('#status').innerText(),/件（直接/);
      await page.locator('#modeRow button[data-mode="shore"]').click();
      assert.match(await page.locator('#status').innerText(),/件（直接/);
      await page.locator('#area').selectOption('all');
      await page.locator('#dateRow button[data-range="7"]').click();
    });

    await check('V4 live feed fixes yesterday zero-data regression',async()=>{
      await page.locator('#dateRow button[data-range="yesterday"]').click();
      await page.locator('#modeRow button[data-mode="shore"]').click();
      const n=Number(await page.locator('#shoreCount').innerText());
      const status=await page.locator('#status').innerText();
      assert(n>=1,'yesterday shore feed unexpectedly empty');
      assert.match(status,/昨日/);
      assert.match(status,/補助/);
      await page.locator('#modeRow button[data-mode="all"]').click();
      await page.locator('#dateRow button[data-range="7"]').click();
      return status;
    });

    await check('Freshness uses session-compressed counts',async()=>{
      const values=await page.evaluate(()=>{
        const a=areaFreshness('敦賀'), s=strategyArea('敦賀');
        return {fresh48:a.recent2,fresh7:a.recent7,strategy48:s?.last48h_sessions?.shore,strategy7:s?.last7_sessions?.shore};
      });
      assert.equal(values.fresh48,values.strategy48);
      assert.equal(values.fresh7,values.strategy7);
      return JSON.stringify(values);
    });

    await check('Panels open and close',async()=>{
      const pairs=[['#trendToggle','#trendPanel','#trendClose'],['#freshToggle','#freshPanel','#freshClose'],['#strategyToggle','#strategyPanel','#strategyClose'],['#newToggle','#newPanel','#newClose']];
      for(const [open,panel,close] of pairs){await page.locator(open).click();assert(await page.locator(panel).evaluate(e=>e.classList.contains('open')));await page.locator(close).click();}
    });

    await check('Trusted shore discovery context is surfaced separately',async()=>{
      const ctx=await page.evaluate(()=>strategyArea('敦賀')?.shore_context||null);
      assert(ctx,'shore discovery context missing');
      assert(Number(ctx.last7_signals||0)>=1,'trusted shore signals were not carried into strategy');
      await page.locator('#strategyToggle').click();
      const txt=await page.locator('#strategyGrid').innerText();
      assert.match(txt,/外部補助釣果/);
      assert.match(txt,/岸・別枠/);
      await page.locator('#strategyClose').click();
      return JSON.stringify(ctx);
    });

    await check('Strategy shows boat depth as separate context',async()=>{
      await page.evaluate(()=>{
        const s=strategyArea('舞鶴');
        if(!s)throw new Error('Maizuru strategy missing');
        s.boat_context={
          latest_date:'2026-09-19',
          last7_sessions:2,
          sources_14d:2,
          day_sessions_7d:1,
          night_sessions_7d:1,
          negative_sessions_7d:0,
          day_depth_signals:[{
            date:'2026-09-19',source:'MIYAMOTOMARU2',time_mode:'day',
            depth_m:[],bottom_offset_m:[5],tana_m:[],depth_confidence:'A'
          }],
          night_depth_signals:[{
            date:'2026-09-28',source:'OCEANS',time_mode:'night',
            depth_m:[13,30],bottom_offset_m:[],tana_m:[],depth_confidence:'B'
          }]
        };
        renderStrategy();
      });
      await page.locator('#strategyToggle').click();
      const txt=await page.locator('#strategyGrid').innerText();
      assert.match(txt,/沖の実測/);
      assert.match(txt,/ボトム上 5m/);
      assert.match(txt,/水深 13〜30m/);
      assert.match(txt,/岸評価とは別枠/);
      await page.locator('#strategyClose').click();
      return 'day/night boat depth rendered without shore-score wording';
    });

    await check('Sea and shelter modes render with API data',async()=>{
      await page.locator('button[data-view="sea"]').click();
      await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('最新海況'),{timeout:10000});
      assert.match(await page.locator('#status').innerText(),/5エリア取得/);
      await page.locator('button[data-view="shelter"]').click();
      await page.waitForFunction(()=>document.querySelector('#status')?.textContent.includes('風裏候補'),{timeout:10000});
      await page.locator('button[data-view="catch"]').click();
    });

    await check('Heavy tide DB is lazy-loaded',async()=>{
      assert(!requests.some(u=>u.includes('/data/tides.json')),'tides.json loaded before target view');
      return 'initial view skipped heavy tide DB';
    });

    await check('Target ranking renders',async()=>{
      await page.locator('#targetToggle').click();
      await page.waitForFunction(()=>document.querySelectorAll('#rankList .rankCard').length>=3,{timeout:15000});
      assert.match(await page.locator('#targetMeta').innerText(),/時間別期待指数/);
      assert(requests.some(u=>u.includes('/data/tides.json')),'tides.json was not loaded on target view');
      await page.locator('#targetClose').click();
    });

    await check('Rapid Today/Tomorrow switch keeps latest selection',async()=>{
      await page.locator('#targetToggle').click();
      await page.locator('#targetPanel button[data-target-day="0"]').click();
      await page.locator('#targetPanel button[data-target-day="1"]').click();
      await page.waitForFunction(()=>document.querySelector('#targetMeta')?.textContent.startsWith('明日'),{timeout:15000});
      assert.match(await page.locator('#targetMeta').innerText(),/^明日/);
      await page.locator('#targetClose').click();
    });

    await check('Manual reload keeps catches visible',async()=>{
      await page.locator('#reloadData').click();
      await page.waitForFunction(()=>document.querySelector('#reloadData')?.textContent==='✓',{timeout:10000});
      assert(Number(await page.locator('#spotCount').innerText())>0);
    });

    await check('No runtime errors in normal flow',async()=>assert.deepEqual(errors,[]));
    await page.screenshot({path:'test-results/main-normal.png',fullPage:true,animations:'disabled'});
  } finally { await context.close(); }

  const raceCase=await withPage(false,450);
  try{
    await raceCase.page.goto(base,{waitUntil:'domcontentloaded',timeout:30000});
    await raceCase.page.waitForFunction(()=>document.querySelector('#spotCount')?.textContent!=='0',{timeout:20000});
    await check('Slow sea response cannot overwrite a newer catch view',async()=>{
      await raceCase.page.locator('button[data-view="sea"]').click();
      await raceCase.page.waitForTimeout(50);
      await raceCase.page.locator('button[data-view="catch"]').click();
      await raceCase.page.waitForTimeout(1200);
      const state=await raceCase.page.evaluate(()=>({
        viewMode,
        status:document.querySelector('#status')?.textContent||'',
        intelLayers:groups.intel.getLayers().length
      }));
      assert.equal(state.viewMode,'catch');
      assert.match(state.status,/件（直接/);
      assert.equal(state.intelLayers,0,'stale sea markers were added after leaving sea view');
      return JSON.stringify(state);
    });
  } finally { await raceCase.context.close(); }

  const failCase=await withPage(true);
  try{
    await failCase.page.goto(base,{waitUntil:'domcontentloaded',timeout:30000});
    await failCase.page.waitForTimeout(5000);
    await check('Optional JSON failure does not kill catch map',async()=>{
      const status=await failCase.page.locator('#status').innerText();
      const n=Number(await failCase.page.locator('#spotCount').innerText());
      assert(n>0,'catch map lost because one optional JSON failed');
      assert(!/データ読込に失敗/.test(status),'whole app failed on optional dataset');
      return status;
    });
    await failCase.page.screenshot({path:'test-results/main-optional-failure.png',fullPage:true,animations:'disabled'});
  } finally { await failCase.context.close(); }

  fs.writeFileSync('test-results/results.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
  const failed=report.checks.filter(x=>x.result==='FAIL');
  if(failed.length){console.error('FAILED:',failed.map(x=>x.name).join(', '));process.exitCode=1;} else console.log('ALL_MAIN_APP_TESTS_PASS');
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
