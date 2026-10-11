const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8').split("document.querySelectorAll('.filter').forEach(button => button.addEventListener")[0];
function setup(initial = {}) {
  const store = new Map(Object.entries(initial));
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', hidden: false, dataset: {}, style: {setProperty(key,value){this[key]=value;}}, firstChild: {textContent: ''}, classList: {toggle(){},add(){},remove(){}}, setAttribute(){}, replaceChildren(){ this.children = []; }, scrollIntoView(options){this.scrolled=options;}, focus(){this.focused=true;}, appendChild(child){ (this.children ||= []).push(child); } });
    return elements.get(id);
  }
  const context = vm.createContext({ console, URL, Intl, Date, setTimeout, clearTimeout, matchMedia(){return {matches:true};}, localStorage: {getItem(key){return store.get(key)||null;},setItem(key,value){store.set(key,value);}}, document: { querySelector: element, querySelectorAll(){return [];}, createElement(){return {};}} });
  vm.runInContext(source, context);
  return { run: expression => vm.runInContext(expression, context), store, element };
}
function article(id = 'news-one', title = '新模型发布') { return {id,title,category:'AI',summary:'模型支持新的任务。',source:'Test',date:'2026-10-10',url:'https://example.com/'+id,language:'zh',summaryType:'source-excerpt'}; }
function edition(articles, status = 'ok') { return {version:2,status,articles,lastAttemptAt:new Date().toISOString(),lastSuccessAt:new Date().toISOString(),editionDate:'2026-10-10',sources:[{name:'Test',status:'ok'}]}; }
test('saved snapshots and reading IDs survive a daily replacement and reload', () => {
  const app = setup();
  app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  app.run("state.saved.push('news-one'); state.archive['news-one'] = articles[0]; state.read.push('news-one'); persist()");
  app.run(`applyDigest(${JSON.stringify(edition([article('news-two')]))})`);
  assert.equal(app.run('collection()[0].id'), 'news-one');
  assert.equal(app.run('state.read.includes("news-one")'), true);
  assert.equal(app.element('#read-fraction').textContent, '0');
  app.run('savedOnly=true; render()');
  assert.match(app.element('#articles').innerHTML, /<span>往期<\/span>/);
  const reopened = setup(Object.fromEntries(app.store));
  assert.equal(reopened.run('collection()[0].id'), 'news-one');
});
test('v1 sample bookmarks migrate with their full article snapshot', () => {
  const app = setup({'frontier-daily:v1':JSON.stringify({saved:['gpt4o-20240513'],read:['gpt4o-20240513']})});
  assert.equal(app.run('collection()[0].source'), 'OpenAI');
  app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  assert.equal(app.run('collection()[0].date'), '2024-05-13');
  assert.ok(app.store.has('frontier-daily:personal:v1'));
});
test('unsafe URLs, hostile IDs and unknown categories cannot enter rendered articles', () => {
  const app = setup();
  for (const bad of [{...article(),url:'javascript:alert(1)'},{...article(),id:'x" onclick="oops'},{...article(),category:'__proto__'}]) {
    assert.equal(app.run(`cleanArticle(${JSON.stringify(bad)})`), null);
  }
  app.run(`applyDigest(${JSON.stringify(edition([article('news-safe','<img src=x onerror=alert(1)>')]))})`);
  assert.match(app.element('#articles').innerHTML, /&lt;img/);
  assert.doesNotMatch(app.element('#articles').innerHTML, /<img/);
});
test('failed collection and unreachable edition both expose retained data status', () => {
  const app = setup();
  app.run(`applyDigest(${JSON.stringify(edition([article()], 'failed'))})`);
  assert.match(app.element('#update-copy').textContent, /采集失败/);
  assert.equal(app.run('articles.length'), 1);
  app.run('loadFailed=true; updateStatus()');
  assert.match(app.element('#update-copy').textContent, /无法读取更新/);
  assert.equal(app.run('articles.length'), 1);
});
test('no data has a truthful empty state and zero-safe progress', () => {
  const app = setup(); app.run('render(); updateStatus()');
  assert.equal(app.element('#read-fraction').textContent, '0');
  assert.equal(app.element('#progress-fill').style.width, '0%');
  assert.match(app.element('#empty-title').textContent, /还没有可用/);
});


test('domestic and overseas originals remain available and region filters combine with search', () => {
  const app = setup();
  const foreign = {...article('news-nasa', 'NASA robot mission'), url:'https://www.nasa.gov/mission', language:'en', source:'NASA'};
  app.run(`applyDigest(${JSON.stringify(edition([{...article(),url:'https://www.ithome.com/news-one'},foreign]))})`);
  assert.equal(app.run('articles.length'), 2);
  app.run("region='overseas'; render()");
  assert.match(app.element('#articles').innerHTML, /NASA robot mission/);
  assert.doesNotMatch(app.element('#articles').innerHTML, /新模型发布/);
  app.run("region='domestic'; render()");
  assert.doesNotMatch(app.element('#articles').innerHTML, /NASA robot mission/);
  app.run("region='overseas'; query='missing'; render()");
  assert.equal(app.element('#articles').innerHTML, '');
  app.run("query=''; state.saved.push('news-nasa'); state.archive['news-nasa']=articles[1]; persist()");
  const reopened = setup(Object.fromEntries(app.store));
  assert.equal(reopened.run('collection()[0].source'), 'NASA');
});

test('personal edition migrates v2 overseas bookmarks without losing snapshots', () => {
  const foreign = {...article('news-old'),url:'https://www.nasa.gov/old',language:'en'};
  const app = setup({'frontier-daily:v2':JSON.stringify({saved:[foreign.id],archive:{[foreign.id]:foreign}})});
  assert.equal(app.run('collection()[0].url'),foreign.url);
  app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  assert.ok(app.store.has('frontier-daily:personal:v1'));
});

test('translated overseas articles support bilingual search and saved snapshots', () => {
  const app = setup();
  const row = {...article('news-translated', 'Space station plans'), language:'en', summary:'A new station.', titleZh:'商业空间站计划', summaryZh:'计划建设新的空间站。'};
  app.run(`applyDigest(${JSON.stringify(edition([row]))})`);
  assert.match(app.element('#articles').innerHTML, /商业空间站计划/);
  assert.match(app.element('#articles').innerHTML, /看来源原文摘录/);
  assert.match(app.element('#articles').innerHTML, /lang="en"/);
  for (const text of ['空间站', 'Space station']) {
    app.run(`query=${JSON.stringify(text)}; render()`);
    assert.equal(app.element('#result-count').textContent, 1);
  }
  app.run("state.saved.push('news-translated'); state.archive['news-translated']=articles[0]; persist()");
  const reopened = setup(Object.fromEntries(app.store));
  assert.equal(reopened.run('collection()[0].summaryZh'), row.summaryZh);
});
test('partial and absent translations fall back per field', () => {
  const app = setup();
  const row = {...article('news-fallback', 'Space station plans'), language:'en', summary:'Original summary.', titleZh:'空间站计划'};
  app.run(`applyDigest(${JSON.stringify(edition([row]))})`);
  assert.match(app.element('#articles').innerHTML, /部分中文，机器翻译/);
  assert.match(app.element('#articles').innerHTML, /Original summary/);
  delete row.titleZh;
  app.run(`applyDigest(${JSON.stringify(edition([row]))})`);
  assert.match(app.element('#articles').innerHTML, /翻译待补/);
  assert.match(app.element('#articles').innerHTML, /看来源原文摘录/);
  assert.match(app.element('#articles').innerHTML, /lang="en"/);
});
test('translation markup is escaped in headings, summaries and accessible labels', () => {
  const app = setup();
  const row = {...article('news-safe-translation'), language:'en', titleZh:'中文<img src=x>', summaryZh:'中文<script>alert(1)</script>'};
  app.run(`applyDigest(${JSON.stringify(edition([row]))})`);
  assert.match(app.element('#articles').innerHTML, /&lt;img/);
  assert.match(app.element('#articles').innerHTML, /&lt;script/);
  assert.doesNotMatch(app.element('#articles').innerHTML, /<img|<script/);
});

test('72-hour archive filters use precise timestamps and Beijing calendar dates', () => {
  const app = setup();
  const now = Date.parse('2026-10-11T08:00:00+08:00');
  const row = (id, publishedAt) => ({...article(id), publishedAt, date:publishedAt.slice(0,10)});
  const current = row('current', '2026-10-11T07:00:00+08:00');
  const boundary = {...row('boundary', '2026-10-08T08:00:00+08:00'),title:'boundary model',url:'https://www.nasa.gov/boundary'};
  const stale = row('stale', '2026-10-08T07:59:59+08:00');
  const future = row('future', '2026-10-11T08:00:01+08:00');
  const utc = row('utc', '2026-10-09T17:00:00Z');
  app.run(`applyDigest(${JSON.stringify({...edition([current]),historyArticles:[boundary,stale,future,utc]})})`);
  assert.equal(app.run(`filteredArticles(${now}).length`),1);
  app.run("dateFilter='recent'");
  assert.equal(app.run(`filteredArticles(${now}).length`),3);
  app.run("dateFilter='2026-10-10'");
  assert.equal(app.run(`filteredArticles(${now})[0].id`),'utc');
  app.run("dateFilter='recent'; region='overseas'; category='AI'; query='boundary'");
  assert.equal(app.run(`filteredArticles(${now})[0].id`),'boundary');
  assert.equal(app.run(`cstDate(Date.parse('2026-10-09T17:00:00Z'))`),'2026-10-10');
  assert.equal(app.run(`dateOptions(${now}).length`),4);
});
test('saved history is unrestricted by default and selection survives filtering with a six-item limit', () => {
  const app = setup();
  const rows = Array.from({length:7}, (_,i) => article('row-'+i));
  app.run(`applyDigest(${JSON.stringify(edition(rows))})`);
  assert.equal(app.run("selectArticle('row-0',true)"),true);
  app.run("query='no matching news'; render()");
  assert.equal(app.run('selected.size'),1);
  assert.equal(app.element('#selection-dock').hidden,false);
  for(let i=1;i<6;i++) assert.equal(app.run(`selectArticle('row-${i}',true)`),true);
  assert.equal(app.run("selectArticle('row-6',true)"),false);
  app.run("selectArticle('row-0',false)");
  assert.equal(app.run("selectArticle('row-6',true)"),true);
  const old = {...article('old'),date:'2024-05-13'};
  app.run(`state.saved=['old']; state.archive.old=cleanArticle(${JSON.stringify(old)}); savedOnly=true; query=''; dateFilter='edition'`);
  assert.equal(app.run('filteredArticles().length'),1);
  app.run("dateFilter='recent'"); assert.equal(app.run('filteredArticles().length'),0);
});
test('one-line source hooks are labelled as teasers and show relative time', () => {
  const app = setup();
  const row = {...article(), summary:'大写的方便', summaryType:'source-teaser', publishedAt:new Date(Date.now() - 5 * 3600_000).toISOString()};
  app.run(`applyDigest(${JSON.stringify(edition([row]))}); render()`);
  assert.match(app.element('#articles').innerHTML, /来源导语/);
  assert.match(app.element('#articles').innerHTML, /article-summary teaser/);
  assert.match(app.element('#articles').innerHTML, /5 小时前/);
});
test('AI editor notes replace the excerpt and keep the source excerpt one click away', () => {
  const app = setup();
  const row = {...article(), language:'en', title:'Nuclear clock', summary:'Scientists built…', titleZh:'核时钟', summaryZh:'科学家造出…', brief:'科学家造出首个核时钟。', why:'新方法：有实验支撑。'};
  app.run(`applyDigest(${JSON.stringify(edition([row]))}); render()`);
  const html = app.element('#articles').innerHTML;
  assert.match(html, /class="article-summary">科学家造出首个核时钟。/);
  assert.match(html, /class="article-why">新方法：有实验支撑。/);
  assert.match(html, /看来源原文摘录.*科学家造出….*Scientists built…/s);
  assert.match(html, /AI 翻译/);
});
test('a postponed edition explains that the AI editor was unreachable', () => {
  const app = setup();
  const old = {...edition([article()]), lastSuccessAt:'2020-01-01T00:00:00Z', pendingReason:'editor-unavailable'};
  app.run(`applyDigest(${JSON.stringify(old)}); updateStatus()`);
  assert.match(app.element('#update-copy').textContent, /AI 编辑没连上/);
});

test('edition limit appears in both status and filter text and follows replacements', () => {
  const app = setup();
  for (const limit of [10, 1, 20]) {
    app.run(`applyDigest(${JSON.stringify({...edition([article()]),articleLimit:limit})})`);
    assert.match(app.element('#update-copy').title, new RegExp('最多 ' + limit + ' 篇'));
    assert.match(app.element('#filter-context').textContent, new RegExp('最多 ' + limit + ' 条'));
  }
});
test('legacy and invalid edition limits display the default without injecting text', () => {
  const app = setup();
  for (const limit of [undefined, null, true, false, 0, -1, 1.5, '10', '<img src=x>']) {
    app.run(`applyDigest(${JSON.stringify({...edition([article()]),articleLimit:limit})})`);
    assert.match(app.element('#update-copy').title, /最多 15 篇/);
    assert.match(app.element('#filter-context').textContent, /最多 15 条/);
  }
});

test('ScienceNet domains are domestic and lookalike domains stay overseas', () => {
  const app = setup();
  for (const host of ['sciencenet.cn', 'www.sciencenet.cn', 'news.sciencenet.cn', 'paper.sciencenet.cn']) {
    assert.equal(app.run(`articleRegion({url:${JSON.stringify('https://' + host + '/article')}})`), 'domestic');
  }
  for (const host of ['sciencenet.cn.example.com', 'notsciencenet.cn', 'example.com']) {
    assert.equal(app.run(`articleRegion({url:${JSON.stringify('https://' + host + '/article')}})`), 'overseas');
  }
});


test('evidence classification covers all types and legacy rows without inventing evidence', () => {
  const app = setup();
  const groups = {solid:['人体临床','实测或观测'],early:['动物或细胞','计算或模拟','方法提出'],claim:['厂商宣称','计划或合同','其他'],unknown:['',null,'未知','__proto__']};
  for (const [tier,labels] of Object.entries(groups)) for (const evidence of labels) {
    const row = {...article(),evidence};
    assert.equal(app.run(`evidenceOf(cleanArticle(${JSON.stringify(row)})).tier`),tier);
    assert.equal(app.run(`evidenceOf(cleanArticle(${JSON.stringify(row)})).cells`),{solid:3,early:2,claim:1,unknown:0}[tier]);
  }
});
test('evidence survives bookmarking, replacement and browser reload', () => {
  const app = setup();
  app.run(`applyDigest(${JSON.stringify(edition([{...article(),evidence:'人体临床'}]))})`);
  app.run("state.saved.push('news-one'); state.archive['news-one']=articles[0]; persist()");
  app.run(`applyDigest(${JSON.stringify(edition([article('next')]))})`);
  assert.equal(setup(Object.fromEntries(app.store)).run('collection()[0].evidence'),'人体临床');
});
test('edition summary counts evidence types by frequency and ignores history and view filters', () => {
  const app = setup();
  const rows = ['人体临床','动物或细胞','人体临床','实测或观测','人体临床'].map((evidence,i) => ({...article('row-'+i),evidence}));
  app.run(`applyDigest(${JSON.stringify({...edition(rows),historyArticles:[{...article('old'),evidence:'厂商宣称'}]})})`);
  assert.equal(app.element('#hero-title').textContent,'今天 5 条。3 条来自人体临床研究，1 条还在动物或细胞阶段，1 条有实测或观测数据。');
  const summary = app.element('#hero-title').textContent, strip = app.element('#evidence-strip').innerHTML;
  app.run("savedOnly=true; query='missing'; render()");
  assert.equal(app.element('#hero-title').textContent,summary);
  assert.equal(app.element('#evidence-strip').innerHTML,strip);
  app.run(`applyDigest(${JSON.stringify(edition([article('legacy')]))})`);
  assert.equal(app.element('#hero-title').textContent,'今天 1 条。');
});
test('evidence strip preserves editorial order, labels links and escapes translated titles', () => {
  const app = setup();
  const rows = [{...article('first','<unsafe>'),evidence:'动物或细胞'}, {...article('second'),evidence:'人体临床'}];
  app.run(`applyDigest(${JSON.stringify(edition(rows))})`);
  const strip = app.element('#evidence-strip').innerHTML;
  assert.match(strip,/第 1 条：动物或细胞，&lt;unsafe&gt;/);
  assert.ok(strip.indexOf('#article-first') < strip.indexOf('#article-second'));
  assert.equal((strip.match(/data-jump=/g)||[]).length,2);
});
test('rank keeps original edition position and disappears in saved and history views', () => {
  const app = setup();
  app.run(`applyDigest(${JSON.stringify(edition([article('first','first'),article('second','second')]))})`);
  app.run("query='second'; render()");
  assert.match(app.element('#articles').innerHTML,/本刊第 2 条/);
  assert.doesNotMatch(app.element('#articles').innerHTML,/ ranked lead/);
  app.run("query=''; state.saved=['first']; state.archive.first=articles[0]; savedOnly=true; render()");
  assert.doesNotMatch(app.element('#articles').innerHTML,/article-rank/);
  assert.equal(app.element('#active-view').hidden,false);
  app.run("savedOnly=false; dateFilter='recent'; render()");
  assert.doesNotMatch(app.element('#articles').innerHTML,/article-rank/);
});
test('zero-count topic chips hide unless selected and filter reset appears only when needed', () => {
  const app = setup(); app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  assert.doesNotMatch(app.element('#topic-chips').innerHTML,/data-category="航天"/);
  assert.equal(app.element('#clear-filters').hidden,true);
  app.run("category='航天'; render()");
  assert.match(app.element('#topic-chips').innerHTML,/data-category="航天" aria-pressed="true".*?<span>0/);
  assert.equal(app.element('#clear-filters').hidden,false);
  app.run('resetView()'); assert.equal(app.element('#clear-filters').hidden,true);
});
test('strip jump resets hidden or non-edition views and focuses the requested article', () => {
  const app = setup(); app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  app.run("query='missing'; savedOnly=true; dateFilter='recent'; jumpToArticle('news-one')");
  assert.equal(app.run("query === '' && !savedOnly && dateFilter === 'edition'"),true);
  assert.equal(app.element('#article-news-one').focused,true);
  assert.equal(app.element('#article-news-one').scrolled.behavior,'instant');
});
test('legacy entries have neutral gauges, explicit evidence labels and accessible action buttons', () => {
  const app = setup(); app.run(`applyDigest(${JSON.stringify(edition([article()]))})`);
  const html = app.element('#articles').innerHTML;
  assert.match(html,/tier-unknown/); assert.match(html,/>未标注<\/span>/);
  assert.doesNotMatch(html,/class="filled"/);
  assert.match(html,/data-save="news-one" aria-pressed="false" aria-label="收藏：/);
  assert.match(html,/data-select="news-one" aria-pressed="false" aria-label="选入卡片：/);
  assert.doesNotMatch(html,/type="checkbox"|AI 整理|值得看：/);
  app.run("state.read.push('news-one'); render()");
  assert.match(app.element('#articles').innerHTML,/tier-unknown ranked lead read/);
  assert.match(app.element('#articles').innerHTML,/>读过<\/span>/);
});
