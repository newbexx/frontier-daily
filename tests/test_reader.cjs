const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const box = {globalThis:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../reader.js'),'utf8'),box);
const r=box.globalThis.FrontierReader;
test('terms match English and Chinese without embedded ASCII false positives',()=>{
 assert.ok(r.matchTerms({title:'FDA-approved epilepsy drug for osteoarthritis'}).some(t=>t.name==='FDA'));
 assert.ok(r.matchTerms({title:'DDR5 4F² DRAM 发布'}).some(t=>t.name==='4F² 内存单元'));
 assert.equal(r.matchTerms({title:'Internal evaluation of a global resource'}).length,0);
});
test('term matches are unique and limited for readable knowledge cards',()=>{
 const list=r.matchTerms({title:'FDA FDA fda 大模型 智能体 多模态 GPU DRAM NAS NPU DDR5 量子 纠缠'});
 assert.equal(new Set(list.map(t=>t.name)).size,list.length); assert.ok(list.length<=8);
});
test('unknown concepts return a truthful empty match',()=>assert.equal(r.matchTerms({title:'新的发现'}).length,0));
test('prompt includes bilingual source, scope limits and user focus',()=>{
 const p=r.buildPrompt({title:'NASA plans',titleZh:'NASA 计划',summary:'A plan',summaryZh:'一项计划',source:'NASA',url:'https://example.com',language:'en'},'空间站是什么？','补充正文','上一轮解读');
 for(const text of ['NASA 计划','NASA plans','A plan','一项计划','空间站是什么？','补充正文','上一轮解读','不声称已经访问','不要把摘要没写']) assert.ok(p.includes(text));
});
test('all ten categories have background reading guidance',()=>assert.equal(Object.keys(r.guides).length,10));
test('a single pasted news URL is recognized without treating prose as a URL',()=>{
 assert.equal(r.pastedUrl('  https://example.com/news?a=1  '),'https://example.com/news?a=1');
 assert.equal(r.pastedUrl('www.example.com/story'),'https://www.example.com/story');
 for(const text of ['一段新闻正文','See https://example.com/story','javascript:alert(1)','https://example.com/\nother']) assert.equal(r.pastedUrl(text),'');
});
test('fetched article text includes its own provenance and truncation limits',()=>{
 const p=r.buildPrompt({title:'摘要标题',summary:'摘要',url:'https://example.com/source'},'背景是什么？','网页正文','',{url:'https://example.com/final',title:'正文网页标题',truncated:true});
 for(const text of ['网页正文','https://example.com/final','网页自动提取','仅前10000字符','正文网页标题','可能遗漏图表']) assert.ok(p.includes(text));
});

test('full explanation teaches cause, principles, intent and maturity to a beginner',()=>{
 const p=r.buildPrompt({title:'一项研究',summary:'实验室验证'},'');
 for(const text of ['从零讲懂','零基础','来龙去脉','本质原理','他们到底想干什么','当前处于什么水平','顺带长点见识','材料不足','生活比喻']) assert.ok(p.includes(text),text);
});
test('specific questions use recent conversation without requesting another long overview',()=>{
 const history=[{role:'user',content:'电池是什么？'},{role:'assistant',content:'可以把它想成存能量的容器。'},{role:'user',content:'能量怎么存？'},{role:'assistant',content:'通过可逆的化学反应。'}];
 const p=r.buildPrompt({title:'新电池'},'那为什么会老化？','',history);
 for(const text of ['那为什么会老化？','电池是什么？','可逆的化学反应','100至300字','不要重新生成一整篇','与这条新闻无关的知识']) assert.ok(p.includes(text),text);
 assert.ok(!p.includes('本次任务：从零讲懂'));
});
test('conversation context is bounded and keeps recent user questions with responses',()=>{
 const history=Array.from({length:60},(_,i)=>({role:i%2?'assistant':'user',content:'第'+i+'轮 '+ '背景'.repeat(400)}));
 const context=r.conversationContext(history);
 assert.ok(context.length<=6500);
 assert.ok(context.includes('第59轮')); assert.ok(context.includes('第58轮'));
 assert.ok(!context.includes('第0轮'));
 assert.equal(r.conversationContext([{role:'system',content:'unsupported'}]),'');
});
test('overview can be explicitly selected after multiple questions',()=>{
 const p=r.buildPrompt({title:'测试新闻'},'','',[{role:'user',content:'先问一个词'}],null,'overview');
 assert.ok(p.includes('本次任务：从零讲懂')); assert.ok(p.includes('先问一个词'));
});

test('learning searches dialogue contents, counts questions and sorts by last question',()=>{
 const rows=[{article:{id:'older',title:'电池研究',category:'新能源'},messages:[{role:'user',content:'可逆反应是什么？',time:'2026-10-10T02:00:00Z'},{role:'assistant',content:'关于老化的回答',time:'2026-10-10T02:00:01Z'}],notes:[]},
 {article:{id:'newer',title:'原题',titleZh:'新电池',category:'新能源'},messages:[{role:'user',content:'第一个问题',time:'2026-10-11T01:00:00Z'},{role:'assistant',content:'答案',time:'2026-10-11T01:00:01Z'},{role:'user',content:'最后一个问题',time:'2026-10-11T02:00:00Z'}],notes:[{id:'note',content:'自己整理的笔记',time:'2026-10-11T03:00:00Z'}]}];
 assert.equal(r.filterLearning(rows)[0].record.article.id,'newer');
 assert.equal(r.filterLearning(rows)[0].questions,2);
 assert.equal(r.filterLearning(rows)[0].lastQuestion,'最后一个问题');
 assert.equal(r.filterLearning(rows,'全部','老化')[0].record.article.id,'older');
 assert.equal(r.filterLearning(rows,'全部','新电池')[0].record.article.id,'newer');
 assert.equal(r.filterLearning(rows,'AI').length,0);
 assert.equal(r.filterLearning(rows,'新能源','自己整理','notes')[0].note.id,'note');
});
test('saved conversation payload is an allowlist and omits custom API settings',()=>{
 const payload=r.recordPayload({article:{id:'story',title:'标题',category:'AI',endpoint:'secret-endpoint',apiKey:'secret-key'},messages:[{role:'user',content:'问题',time:'2026-10-11T02:00:00Z',apiKey:'secret-key'},{role:'assistant',content:'回答',model:'custom-secret-model',custom:true,time:'2026-10-11T02:00:01Z'}],body:'正文',url:'https://example.com',bodySource:{url:'https://example.com',title:'原文',truncated:false,apiKey:'secret-key'},endpoint:'secret-endpoint',apiKey:'secret-key',draft:'未发送草稿'});
 const text=JSON.stringify(payload);
 for(const secret of ['secret-key','secret-endpoint','custom-secret-model','未发送草稿']) assert.ok(!text.includes(secret));
 assert.equal(payload.body,'正文'); assert.equal(payload.messages[1].model,'');
 assert.equal(payload.bodySource.title,'原文');
});


test('learning sidebar takes the latest three questions and counts notes across all records',()=>{
 const records=Array.from({length:4},(_,i)=>({article:{id:'story-'+i,title:'新闻'+i},messages:[{role:'user',content:'问题'+i,time:'2026-10-11T0'+i+':00:00Z'},{role:'assistant',content:'回答',time:'2026-10-11T06:00:00Z'}],notes:i===0?[{id:'n1'},{id:'n2'}]:[]}));
 records.push({article:{id:'assistant-only'},messages:[{role:'assistant',content:'只有回答',time:'2026-10-11T07:00:00Z'}],notes:[{id:'n3'}]});
 const overview=r.learningOverview(records);
 assert.deepEqual(Array.from(overview.recent,row=>row.record.article.id),['story-3','story-2','story-1']);
 assert.equal(overview.recent[0].lastQuestion,'问题3'); assert.equal(overview.learned,4); assert.equal(overview.notes,3);
});
test('empty learning sidebar has zero questions and zero notes',()=>{
 const overview=r.learningOverview([]); assert.equal(overview.recent.length,0); assert.equal(overview.learned,0); assert.equal(overview.notes,0);
});
test('learning snapshots preserve evidence while omitting unrelated fields',()=>{
 const payload=r.recordPayload({article:{id:'evidence',title:'研究',evidence:'人体临床',apiKey:'secret'},messages:[],notes:[]});
 assert.equal(payload.article.evidence,'人体临床'); assert.ok(!('apiKey' in payload.article));
});
