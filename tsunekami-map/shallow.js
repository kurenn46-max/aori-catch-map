(function(){
'use strict';
// Private, local-only data import. Never uploads a user's licensed chart or sounding file.
var KEY='oka-tsunekami-shallow-v1',B={minLat:35.56,maxLat:35.70,minLon:135.76,maxLon:135.92};
var state={map:null,L:null,group:null,records:[],loaded:false,status:function(){},onModel:function(){}};
function el(t,s,root){var x=document.createElement(t);if(s!==undefined)x.textContent=s;if(root)root.appendChild(x);return x;}
function depth(p){for(var k of ['depth_m','depth','DEPTH','VALDCO','DEPTH_M','Depth','water_depth'])if(p&&p[k]!==undefined&&p[k]!==null){var n=Number(p[k]);if(Number.isFinite(n)&&n>=0&&n<=100)return Math.round(n*10)/10;}return null;}
function ok(lat,lon){return Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=B.minLat&&lat<=B.maxLat&&lon>=B.minLon&&lon<=B.maxLon;}
function point(lat,lon){lat=Number(lat);lon=Number(lon);return ok(lat,lon)?[lat,lon]:null;}
function shade(d){return d<=2?'#37bd5b':d<=5?'#08a2bc':d<=10?'#146ef2':d<=20?'#eda121':'#9656ce';}
function countVertices(rs){return rs.reduce(function(n,r){return n+(r.coords?r.coords.length:1);},0);}
function processGeo(json){
 var fs=json.type==='FeatureCollection'?json.features:json.type==='Feature'?[json]:Array.isArray(json.features)?json.features:[];
 if(!Array.isArray(fs))throw Error('GeoJSONのfeaturesを読み取れません');
 var out=[];
 for(var f of fs){if(!f||!f.geometry)continue;var d=depth(f.properties||{});if(d===null)continue;var t=f.geometry.type,cc=f.geometry.coordinates;
   if(t==='Point'&&Array.isArray(cc)){var p=point(cc[1],cc[0]);if(p)out.push({kind:'point',depth:d,coords:p});}
   if(t==='LineString'||t==='MultiLineString'){
     var paths=t==='LineString'?[cc]:cc;if(!Array.isArray(paths))continue;
     for(var path of paths){if(!Array.isArray(path))continue;var pts=path.map(p=>Array.isArray(p)?point(p[1],p[0]):null).filter(Boolean);
       if(pts.length>=2)out.push({kind:'line',depth:d,coords:pts});
     }
   }
 }
 return out;
}
function parseText(input){
 // Accept GeoJSON, 4-column MIRC ASCII and latitude,longitude,depth CSV
 var s=input.replace(/^\ufeff/,'').trimStart();if(s.startsWith('{')||s.startsWith('[')){
  var j=JSON.parse(s);return processGeo(j);
 }
 var out=[],block=[],blockDepth=null,header=null,grouped=new Map(),hasHeader=false;
 function flush(){if(block.length>=2)out.push({kind:'line',depth:blockDepth,coords:block.slice()});else if(block.length===1)out.push({kind:'point',depth:blockDepth,coords:block[0]});block=[];blockDepth=null;}
 var lines=input.replace(/\r/g,'').split('\n');
 for(var raw of lines){var line=raw.trim();if(!line){flush();continue;}if(line.startsWith('#')||line.startsWith('//'))continue;
   var values=line.indexOf(',')>=0?line.split(',').map(v=>v.trim().replace(/^"|"$/g,'')):line.split(/\s+/);
   if(!header && /(?:lat|latitude|緯度|longitude|経度)/i.test(line)){
    header=values.map(v=>v.toLowerCase());hasHeader=true;flush();continue;
   }
   var la,lo,de,groupId='';
   if(hasHeader){
    function val(keys){for(var k of keys){var i=header.indexOf(k);if(i>=0)return values[i];}return undefined;}
    la=val(['lat','latitude','緯度']);lo=val(['lon','lng','longitude','経度']);de=val(['depth','depth_m','depth(m)','水深','水深m']);groupId=val(['line_id','line','group'])||'';
   }else{la=values[0];lo=values[1];de=values[2];}
   la=Number(la);lo=Number(lo);de=Number(de);
   if(!ok(la,lo)||!Number.isFinite(de)||de<0||de>100)continue;de=Math.round(de*10)/10;
   if(hasHeader){if(groupId){var id=groupId+'|'+de;if(!grouped.has(id))grouped.set(id,[]);grouped.get(id).push([la,lo]);}else out.push({kind:'point',depth:de,coords:[la,lo]});}
   else{
    // Four-column MIRC ASCII is grouped into lines separated by blank lines.
    if(blockDepth!==null&&de!==blockDepth)flush();
    blockDepth=de;block.push([la,lo]);
   }
 }
 flush();
 grouped.forEach(function(ps,key){out.push({kind:ps.length>=2?'line':'point',depth:Number(key.slice(key.lastIndexOf('|')+1)),coords:ps.length>=2?ps:ps[0]});});
 return out;
}
function draw(){
 if(!state.group)return;state.group.clearLayers();
 for(var r of state.records){var d=r.depth,color=shade(d);
  if(r.kind==='line'){state.L.polyline(r.coords,{color:color,weight:d<=10?4:3,opacity:.95})
   .bindPopup('読み込み済み等深線：'+d+'m<br>端末内の資料から表示。測量日・出典は元資料を確認してな。').addTo(state.group);
  }else{
   state.L.circleMarker(r.coords,{radius:5,color:'#fff',weight:1.5,fillColor:color,fillOpacity:.95})
    .bindPopup('水深記録：'+d+'m<br>端末内の資料から表示。出典と測量日を確認してな。').addTo(state.group);
  }
 }
 state.group.bringToFront();
 var t=document.getElementById('shallowCount');if(t)t.textContent='端末内の浅場データ：'+state.records.length+'件';
}
function persist(){
 try{localStorage.setItem(KEY,JSON.stringify(state.records));return true;}catch(e){state.status('端末の保存容量が足りへん。小さい範囲に絞って再度読み込んでな。',6500);return false;}
}
function restore(){
 try{var d=JSON.parse(localStorage.getItem(KEY)||'[]');if(Array.isArray(d))state.records=d.filter(r=>r&&['point','line'].includes(r.kind)&&Number.isFinite(r.depth)&&r.depth<=100).slice(0,3500);}catch(e){state.records=[];}
 draw();
}
function row(root,tag,title){var x=el(tag,title,root);x.style.marginTop='10px';return x;}
function link(root,name,url){var p=el('p',undefined,root),a=el('a',name+' ↗',p);a.href=url;a.target='_blank';a.rel='noopener noreferrer';}
function open(){
 var sheet=document.getElementById('sheet'),shade=document.getElementById('shade'),body=document.getElementById('details');
 sheet.querySelector('h2').textContent='浅場の水深（2m・5m・10m）';body.textContent='';shade.hidden=false;sheet.hidden=false;
 row(body,'p','現在、常神の2m・5m・10mを実測した公開データは未収録。海しるで取得できた20m・50mとは区別して表示するで。');
 var c=row(body,'p','端末内の浅場データ：'+state.records.length+'件');c.id='shallowCount';c.style.fontWeight='800';
 var legend=row(body,'p','線の色：2m＝緑／5m＝水色／10m＝青。取得した資料の深さをそのまま表示し、推測の線は作らへん。');legend.className='muted';
 var b=el('div',undefined,body);b.className='warning';b.textContent='購入した海図の取込は、複製・加工と私的利用が許可されている場合だけ。第三者に無断公開せず、元資料の測量日と測深基準を確認してな。';
 var consent=el('label',undefined,body);consent.style.cssText='display:flex;gap:8px;align-items:center;margin:13px 0 7px;font-size:12px;font-weight:700';var cb=el('input',undefined,consent);cb.type='checkbox';cb.id='shallowConsent';cb.style.cssText='width:19px;height:19px;flex-shrink:0';el('span','このファイルを読み込む権利・許可がある',consent);
 var lab=row(body,'label','GeoJSON／CSV／4列テキストを選ぶ');
 var file=el('input',undefined,body);file.id='shallowFile';file.type='file';file.accept='.geojson,.json,.csv,.txt,.asc,text/plain,application/json';file.disabled=true;file.style.cssText='display:block;width:100%;padding:11px 3px;font-size:12px;max-width:100%';
 cb.onchange=function(){file.disabled=!this.checked;};
 var msg=el('div','※最大4MB・常神周辺の座標だけ取得。保存先は今使っているブラウザ内だけ。',body);msg.style.fontSize='11px';
 file.onchange=async function(){
  var f=this.files&&this.files[0];if(!f)return;
  if(f.size>4*1024*1024){state.status('4MB以下の常神周辺データに分割してな。',6500);return;}
  try{
   var content=await f.text(),rows=parseText(content);
   if(!rows.length)throw Error('対象範囲の水深データが0件。緯度・経度・水深とファイル形式を確認してな。');
   if(state.records.length+rows.length>3500||countVertices(rows)+countVertices(state.records)>30000)throw Error('データが多すぎる。常神周辺だけに絞ってな。');
   state.records=state.records.concat(rows);persist();draw();c.textContent='端末内の浅場データ：'+state.records.length+'件';
   state.status(rows.length+'件を端末内に読み込んだで。',5100);
  }catch(e){state.status('読込できへん：'+e.message,7400);}
  this.value='';
 };
 var clear=el('button','端末内の水深データを削除',body);clear.style.cssText='margin:9px 0;padding:9px;color:#7c2830;background:#fff;border:1px solid #ddbabf;border-radius:9px';
 clear.onclick=function(){if(!confirm('この端末に読み込んだ浅場データを全部削除する？'))return;state.records=[];persist();draw();c.textContent='端末内の浅場データ：0件';state.status('端末内の取込データを削除したで。');};
 var approx=el('button','沖側の概算水深を切り替える',body);approx.style.cssText='margin:9px 0 0 6px;padding:9px;border:1px solid #b6d4df;border-radius:9px;background:#e6f2f7;color:#14556b';approx.onclick=state.onModel;
 row(body,'h3','実際の浅い海図を確認する');link(body,'日本水路協会・小型船用電子データ（5m・10m）','https://www.jha.or.jp/jp/shop/products/digital/index.html');link(body,'new pec（全国沿岸・2m/5m/10m）','https://www.newpec.jp/');link(body,'国土地理院の地図','https://maps.gsi.go.jp/');
 row(body,'p','取込形式：GeoJSONのPoint／LineString／MultiLineStringにdepth_m属性、またはCSVのlatitude,longitude,depth_m（点データ）。線はline_id列で結合できる。MIRC系の緯度 経度 水深 属性（4列、空行で線を区切る）にも対応。').className='muted';
}
window.TsunekamiShallow={
 start:function(map,L,opts){state.map=map;state.L=L;state.group=L.layerGroup().addTo(map);state.status=opts.status||state.status;state.onModel=opts.onModel||state.onModel;restore();},
 open:open,count:function(){return state.records.length;},isReady:function(){return !!state.group;}
};
})();