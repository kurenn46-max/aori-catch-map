const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const html=fs.readFileSync('index.html','utf8');
const match=html.match(/function directSourceUnavailable\(checks\)\{[\s\S]*?\n\}/);
assert.ok(match,'direct source outage helper missing');
const directSourceUnavailable=vm.runInNewContext('('+match[0]+')');

assert.equal(directSourceUnavailable([]),false);
assert.equal(directSourceUnavailable(null),false);
assert.equal(directSourceUnavailable([{lane:'broad',status:'blocked'}]),false);
assert.equal(directSourceUnavailable([{lane:'direct',status:'blocked'},{lane:'direct',status:'error'}]),true);
assert.equal(directSourceUnavailable([{lane:'direct',status:'blocked'},{lane:'direct',status:'no_new'}]),false);
assert.equal(directSourceUnavailable([{lane:'direct',status:'ok'},{lane:'hot',status:'blocked'}]),false);
assert.equal(directSourceUnavailable([{source:'エギCOM / 越前',status:'blocked'}]),true);
assert.equal(directSourceUnavailable([{lane:'direct',status:'blocked'},{lane:'broad',status:'ok'}]),true);
assert.match(html,/fallback:sourceStatus\.fallback\|\|v4Health\.fallback/,'direct fallback metadata should be preserved');
assert.match(html,/直接釣果の自動取得停止中/,'map status must show direct collection outage');
assert.match(html,/エギCOM公式の投稿を見る/,'link to official source is required');
console.log('Direct source outage UI checks: PASS');
