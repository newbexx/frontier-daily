'use strict';

// 仅用于迁移基础版已收藏的历史条目，不进入每日资讯列表。
const legacyArticles = [
  { id: 'gpt4o-20240513', category: 'AI', title: 'GPT-4o：让文字、视觉和语音在同一个模型里相遇', summary: 'OpenAI 发布 GPT-4o，将文字、视觉与音频能力整合进同一模型，探索更自然的人机交互。', source: 'OpenAI', date: '2024-05-13', url: 'https://openai.com/index/hello-gpt-4o/', featured: true },
  { id: 'claude35-20240621', category: 'AI', title: 'Claude 3.5 Sonnet 发布，Artifacts 让生成内容有了独立空间', summary: 'Anthropic 推出 Claude 3.5 Sonnet，并预览 Artifacts，让代码和文档等内容可以在对话旁单独查看与编辑。', source: 'Anthropic', date: '2024-06-21', url: 'https://www.anthropic.com/news/claude-3-5-sonnet' },
  { id: 'blackwell-20240318', category: '芯片', title: 'NVIDIA 发布 Blackwell，瞄准大规模生成式 AI 计算', summary: 'Blackwell 平台以新 GPU 架构和互联技术，支持更大规模模型的训练与推理。', source: 'NVIDIA', date: '2024-03-18', url: 'https://nvidianews.nvidia.com/news/nvidia-blackwell-platform-arrives-to-power-a-new-era-of-computing' },
  { id: 'alphafold3-20240508', category: '生命科学', title: 'AlphaFold 3：从预测蛋白质，走向预测分子间的相互作用', summary: '研究团队在 Nature 发表 AlphaFold 3，将结构预测扩展到包含蛋白质、核酸和小分子等成分的复合物。', source: 'Nature · 原始论文', date: '2024-05-08', url: 'https://www.nature.com/articles/s41586-024-07487-w' },
  { id: 'rt2-20230728', category: '机器人', title: 'RT-2：把视觉与语言理解，转化为机器人的动作', summary: 'Google DeepMind 展示视觉—语言—动作模型 RT-2，尝试将网络知识迁移到真实机器人的操作任务。', source: 'Google DeepMind', date: '2023-07-28', url: 'https://deepmind.google/blog/rt-2-new-model-translates-vision-and-language-into-action/' },
  { id: 'gemini15-20240215', category: 'AI', title: 'Gemini 1.5 探索长上下文，一次处理更多信息', summary: 'Google 发布 Gemini 1.5，并向部分开发者开放百万 token 上下文的实验性预览，探索长文档与多模态理解。', source: 'Google', date: '2024-02-15', url: 'https://blog.google/innovation-and-ai/products/google-gemini-next-generation-model-february-2024/' },
  { id: 'europa-20241014', category: '航天', title: 'Europa Clipper 升空，启程探索木卫二的海洋世界', summary: 'NASA 发射 Europa Clipper，计划通过多次近距离飞掠，研究木卫二是否具备适合生命存在的条件。', source: 'NASA', date: '2024-10-14', url: 'https://www.nasa.gov/news-release/liftoff-nasas-europa-clipper-sails-toward-ocean-moon-of-jupiter/' },
  { id: 'llama3-20240418', category: 'AI', title: 'Meta 推出 Llama 3，让 AI 助手走进更多日常场景', summary: 'Meta 发布基于 Llama 3 的 Meta AI 升级，将问答、创作与信息获取能力引入旗下多款应用。', source: 'Meta', date: '2024-04-18', url: 'https://about.fb.com/news/2024/04/meta-ai-assistant-built-with-llama-3/' },
  { id: 'ultra200v-20240903', category: '芯片', title: 'Intel Core Ultra 200V 发布，让 AI 运算更多地留在电脑上', summary: 'Intel 面向轻薄笔记本推出 Core Ultra 200V 系列，结合 CPU、GPU 与 NPU 加强端侧 AI 运算能力。', source: 'Intel', date: '2024-09-03', url: 'https://www.intel.com/content/www/us/en/newsroom/news/core-ultra-200v-series-mobile.html' },
  { id: 'imo-20240725', category: 'AI', title: 'AI 解答奥数难题，达到国际数学奥林匹克银牌分数线', summary: 'DeepMind 的 AlphaProof 与 AlphaGeometry 2 解出 2024 年 IMO 六道题中的四道，在评估中达到银牌标准。', source: 'Google DeepMind', date: '2024-07-25', url: 'https://deepmind.google/blog/ai-solves-imo-problems-at-silver-medal-level/' }
];

const categoryClasses = { AI: 'ai', '芯片': 'chip', '机器人': 'robot', '航天': 'space', '生命科学': 'bio', '医疗健康': 'health', '新能源': 'energy', '气候环境': 'climate', '量子科技': 'quantum', '网络安全': 'security' };
const storageKey = 'frontier-daily:personal:v1';
const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
let articles = [];
let historyArticles = [];
let dateFilter = 'edition';
let selected = new Map();
let digest = null;
let category = '全部';
let region = 'all';
let query = '';
let savedOnly = false;
let toastTimer;
let checking = false;
let loadFailed = false;
let refreshState = '';  // running | ready | editor-unavailable | failed | offline
let refreshRequestedAt = 0;
let state;


// Evidence definitions are shared by the masthead and every article.
const evidenceTypes = {
  '人体临床': {tier:'solid', cells:3, phrase:'来自人体临床研究'},
  '实测或观测': {tier:'solid', cells:3, phrase:'有实测或观测数据'},
  '动物或细胞': {tier:'early', cells:2, phrase:'还在动物或细胞阶段'},
  '计算或模拟': {tier:'early', cells:2, phrase:'只做了计算或模拟'},
  '方法提出': {tier:'early', cells:2, phrase:'是尚未验证的新方法'},
  '厂商宣称': {tier:'claim', cells:1, phrase:'是厂商的说法'},
  '计划或合同': {tier:'claim', cells:1, phrase:'是计划或合同'},
  '其他': {tier:'claim', cells:1, phrase:'是其他类型'}
};
function evidenceOf(article) {
  return Object.hasOwn(evidenceTypes, article.evidence) ? {...evidenceTypes[article.evidence], label:article.evidence} : {tier:'unknown', cells:0, label:'未标注', phrase:'未标注证据类型'};
}
function articleTitle(article) { return article.language === 'en' && article.titleZh ? article.titleZh : article.title; }
let stripEdition = '';
function updateSummary() {
  const counts = new Map();
  for (const article of articles) { const info = evidenceOf(article); if (info.cells) counts.set(info.label, (counts.get(info.label) || 0) + 1); }
  const parts = [...counts].sort((a,b) => b[1] - a[1]).map(([label,count]) => count + ' 条' + evidenceTypes[label].phrase);
  $('#hero-title').textContent = '今天 ' + articles.length + ' 条。' + (parts.length ? parts.join('，') + '。' : '');
  // Rebuild only when this edition changes, so filtering never replays the intro animation.
  const signature = JSON.stringify(articles.map(article => [article.id,article.evidence,articleTitle(article)]));
  if (signature !== stripEdition) {
    stripEdition = signature;
    $('#evidence-strip').style.setProperty('--count', Math.max(1,articles.length));
    $('#evidence-strip').innerHTML = articles.map((article,index) => '<a class="tier-' + evidenceOf(article).tier + '" href="#article-' + article.id + '" data-jump="' + article.id + '" style="--i:' + index + '" aria-label="第 ' + (index+1) + ' 条：' + evidenceOf(article).label + '，' + escapeHtml(articleTitle(article)) + '"></a>').join('');
  }
}
function jumpToArticle(id) {
  if (!articles.some(article => article.id === id)) return;
  if (savedOnly || dateFilter !== 'edition' || !filteredArticles().some(article => article.id === id)) resetView();
  const target = $('#article-' + id);
  target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',block:'start'});
  target.classList.remove('flash');
  void target.offsetWidth;
  target.classList.add('flash');
  target.focus({preventScroll:true});
}

state = readState();

function articleRegion(article) {
  const host = new URL(article.url).hostname.toLowerCase();
  return ['ithome.com', 'qbitai.com', 'sciencenet.cn'].some(domain => host === domain || host.endsWith('.' + domain)) ? 'domestic' : 'overseas';
}
function cleanArticle(value) {
  if (!value || typeof value !== 'object' || !/^[a-zA-Z0-9_-]{1,100}$/.test(value.id) || !Object.hasOwn(categoryClasses, value.category)) return null;
  if (!['title', 'summary', 'source', 'date', 'url'].every(key => typeof value[key] === 'string')) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value.date)) return null;
  try { const url = new URL(value.url); if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null; } catch { return null; }
  return { evidence: Object.hasOwn(evidenceTypes, value.evidence) ? value.evidence : '', publishedAt: typeof value.publishedAt === 'string' && Number.isFinite(Date.parse(value.publishedAt)) ? value.publishedAt : '', titleZh: typeof value.titleZh === 'string' ? value.titleZh.slice(0, 500).trim() : '', summaryZh: typeof value.summaryZh === 'string' ? value.summaryZh.slice(0, 2000).trim() : '', brief: typeof value.brief === 'string' ? value.brief.slice(0, 200).trim() : '', why: typeof value.why === 'string' ? value.why.slice(0, 120).trim() : '', id: value.id, category: value.category, title: value.title.slice(0, 500), summary: value.summary.slice(0, 1000), source: value.source.slice(0, 100), date: value.date, url: value.url, language: value.language === 'en' ? 'en' : 'zh', featured: value.featured === true, summaryType: ['source-excerpt', 'source-teaser'].includes(value.summaryType) ? value.summaryType : 'legacy' };
}

function readState() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey) || localStorage.getItem('frontier-daily:v2') || localStorage.getItem('frontier-daily:v1') || '{}');
    const ids = values => Array.isArray(values) ? [...new Set(values.filter(id => typeof id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(id)))] : [];
    const saved = ids(raw?.saved);
    const archive = Object.create(null);
    for (const value of [...legacyArticles, ...Object.values(raw?.archive || {})]) { const article = cleanArticle(value); if (article && saved.includes(article.id)) archive[article.id] = article; }
    return { saved, read: ids(raw?.read), archive };
  } catch { return { saved: [], read: [], archive: Object.create(null) }; }
}
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(state)); return true; } catch { return false; }
}
function collection() {
  return state.saved.map(id => findArticle(id)).filter(Boolean);
}
function toast(message) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 3000);
}
function applyDigest(value) {
  if (!value || value.version !== 2 || !Array.isArray(value.articles) || !['ok', 'partial', 'failed'].includes(value.status)) throw new Error('invalid digest');
  const next = value.articles.map(cleanArticle).filter(Boolean);
  if (next.length !== value.articles.length || new Set(next.map(article => article.id)).size !== next.length) throw new Error('invalid articles');
  if (!value.lastAttemptAt || !Number.isFinite(Date.parse(value.lastAttemptAt))) throw new Error('invalid timestamp');
  const changed = JSON.stringify(digest) !== JSON.stringify(value);
  digest = value;
  const merged = new Map();
  for (const row of [...historyArticles, ...(Array.isArray(value.historyArticles) ? value.historyArticles : []), ...next]) {
    const item = cleanArticle(row);
    if (item) merged.set(item.id, {...merged.get(item.id), ...item});
  }
  articles = next;
  historyArticles = [...merged.values()].sort((a, b) => articleTime(b) - articleTime(a));
  for (const item of historyArticles) if (selected.has(item.id)) selected.set(item.id, item);
  for (const article of historyArticles) if (state.saved.includes(article.id)) state.archive[article.id] = article;
  persist();
  if (changed) render();
  updateStatus();
}
function timeLabel(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return '尚未成功更新';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}
function isStale() {
  const success = digest?.lastSuccessAt ? Date.parse(digest.lastSuccessAt) : NaN;
  // The date is evaluated in Beijing time, independent of the browser's own timezone.
  const cst = new Date(Date.now() + 8 * 3600_000);
  const target = Date.UTC(cst.getUTCFullYear(), cst.getUTCMonth(), cst.getUTCDate(), 0) - (cst.getUTCHours() < 8 ? 86400_000 : 0);
  return !Number.isFinite(success) || success < target;
}
function editionLimit() {
  return Number.isInteger(digest?.articleLimit) && digest.articleLimit > 0 ? digest.articleLimit : 15;
}
function updateStatus() {
  const stale = isStale();
  const problem = loadFailed || digest?.status === 'failed' || stale;
  const refreshing = { running: ['正在更新', '正在采集，并由 AI 挑选和整理新闻，大约 1–3 分钟。先看上一刊。'], ready: ['新刊已就绪', '新的一刊已生成，点右侧载入。'], 'editor-unavailable': ['暂未更新', 'AI 编辑暂时连不上，今天还没出新刊，先看上一刊。检查 API 转发服务后，重新打开页面会再试。'], failed: ['暂未更新', '这次采集没有成功，保留上一刊，稍后打开页面会再试。'], offline: ['暂未更新', '今天的新刊还没生成。运行桌面的「启动简报.cmd」即可更新。'] }[refreshState];
  $('#update-label').textContent = refreshing ? refreshing[0] : !digest ? '等待更新' : problem ? '保留上一刊' : digest.status === 'partial' ? '部分更新' : '已更新';
  $('#update-notice').classList.toggle('update-warning', refreshState !== 'ready' && (problem || digest?.status === 'partial'));
  const issue = refreshing ? refreshing[1] : !digest ? '尚无可用简报，请通过“启动简报.cmd”采集内容。' : loadFailed ? '暂时无法读取更新，保留当前已加载内容。' : digest.status === 'failed' ? '最近采集失败，保留上次成功内容。' : stale && digest.pendingReason === 'editor-unavailable' ? '定时更新时 AI 编辑没连上，打开页面时会再试。当前显示上一刊。' : stale ? '今天的计划更新尚未完成，当前显示上次成功内容。' : digest.status === 'partial' ? '部分来源暂时不可用，已用可用来源生成本刊。' : '从近 72 小时国内外资讯中，由 AI 挑出值得读的最多 ' + editionLimit() + ' 篇，并用一句话说清每条讲了什么。';
  const sources = Array.isArray(digest?.sources) ? digest.sources : [];
  $('#update-copy').textContent = refreshing || problem || digest?.status !== 'ok' ? issue : sources.length + ' 个来源全部正常';
  $('#update-copy').title = issue;
  $('#update-notice').dataset.state = refreshState === 'running' ? 'running' : refreshState === 'ready' ? 'ready' : problem || digest?.status === 'partial' ? 'warning' : 'ready';
  $('#reload-edition').textContent = refreshState === 'ready' ? '载入新刊' : '现在检查更新';
  $('#update-time').textContent = timeLabel(digest?.lastSuccessAt) + (digest?.lastSuccessAt ? ' 更新' : '');
  $('#edition-label').textContent = digest?.editionDate ? digest.editionDate.replaceAll('-', '.') + ' 刊' : '每日简报';
  $('#sources-status').replaceChildren();
  for (const source of Array.isArray(digest?.sources) ? digest.sources : []) {
    const row = document.createElement('li');
    row.textContent = String(source.name || '资讯源') + ' · ' + (source.status === 'ok' ? '已连接' : '暂不可用');
    row.className = source.status === 'ok' ? 'source-ok' : 'source-error';
    $('#sources-status').appendChild(row);
  }
}
async function reloadEdition(manual = false) {
  if (checking) return;
  if (!['http:', 'https:'].includes(location.protocol)) { if (manual) location.reload(); return; }
  checking = true;
  $('#reload-edition').disabled = true;
  try {
    const response = await fetch('data/latest.json?t=' + Date.now(), { cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const value = await response.json();
    loadFailed = false;
    applyDigest(value);
    if (manual) toast('已载入最新采集刊：' + (digest.editionDate || '暂无成功刊'));
  } catch {
    loadFailed = true;
    updateStatus();
    if (manual) toast('暂时读取失败，已保留当前内容');
  } finally { checking = false; $('#reload-edition').disabled = false; }
}
// Collection runs in the local service; the page asks for it when today's edition is missing.
const serviceBase = () => location.protocol === 'file:' ? 'http://127.0.0.1:8768' : location.origin;
async function requestRefresh() {
  if (!digest || !isStale() || refreshState === 'running' || Date.now() - refreshRequestedAt < 10 * 60_000) return;
  refreshRequestedAt = Date.now();
  try {
    const response = await fetch(serviceBase() + '/api/refresh', { method: 'POST', credentials: 'omit' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    refreshState = 'running';
  } catch { refreshState = 'offline'; }
  updateStatus();
  while (refreshState === 'running') {
    await new Promise(resolve => setTimeout(resolve, 5000));
    try {
      const status = await (await fetch(serviceBase() + '/api/refresh', { credentials: 'omit' })).json();
      if (!status.running) refreshState = status.exitCode === 0 ? 'ready' : status.exitCode === 3 ? 'editor-unavailable' : 'failed';
    } catch { refreshState = 'offline'; }
  }
  if (refreshState === 'ready' && location.protocol !== 'file:') { refreshState = ''; await reloadEdition(); }
  updateStatus();
}
function ago(article, now = Date.now()) {
  if (!article.publishedAt) return '';
  const hours = Math.floor((now - Date.parse(article.publishedAt)) / 3600_000);
  return hours < 1 ? '刚刚' : hours < 24 ? hours + ' 小时前' : hours < 72 ? Math.floor(hours / 24) + ' 天前' : '';
}
function cstDate(now = Date.now()) { return new Date(now + 8 * 3600_000).toISOString().slice(0, 10); }
function articleTime(article) { return Date.parse(article.publishedAt || article.date + 'T00:00:00+08:00'); }
function recentArticles(now = Date.now()) { return historyArticles.filter(article => articleTime(article) >= now - 72 * 3600_000 && articleTime(article) <= now); }
function findArticle(id) { return articles.find(article => article.id === id) || historyArticles.find(article => article.id === id) || state.archive[id] || selected.get(id); }
function dateOptions(now = Date.now()) {
  const dates = new Set();
  for (let time = now; time >= now - 72 * 3600_000; time -= 24 * 3600_000) dates.add(cstDate(time));
  return [...dates];
}
function filteredArticles(now = Date.now()) {
  const pool = savedOnly ? collection() : dateFilter === 'edition' ? articles : recentArticles(now);
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return pool.filter(article => (dateFilter === 'edition' || (articleTime(article) >= now - 72 * 3600_000 && articleTime(article) <= now && (dateFilter === 'recent' || cstDate(articleTime(article)) === dateFilter))) && (region === 'all' || articleRegion(article) === region) && (category === '全部' || article.category === category) && words.every(word => [article.title, article.summary, article.titleZh, article.summaryZh, article.brief, article.why, article.source, article.category, article.date].join(' ').toLocaleLowerCase().includes(word)));
}
function updateFilters() {
  const dates = dateOptions();
  if (!['edition', 'recent', ...dates].includes(dateFilter)) dateFilter = 'edition';
  $('#date-filter').innerHTML = '<option value="edition">' + (savedOnly ? '全部收藏' : '本刊') + '</option><option value="recent">近三天</option>' + dates.map(date => '<option value="' + date + '">' + date.replaceAll('-', '.') + '</option>').join('');
  $('#date-filter').value = dateFilter;
  const counted = savedOnly ? collection() : dateFilter === 'edition' ? articles : recentArticles();
  const topics = ['全部', ...Object.keys(categoryClasses)];
  $('#topic-chips').innerHTML = topics.map(topic => {
    const count = topic === '全部' ? counted.length : counted.filter(article => article.category === topic).length;
    if (!count && topic !== '全部' && category !== topic) return '';
    return '<button class="topic-chip" type="button" data-category="' + topic + '" aria-pressed="' + (topic === category) + '">' + (topic === 'AI' ? '人工智能' : topic) + '<span>' + count + '</span></button>';
  }).join('');
  $('#clear-filters').hidden = !(query || category !== '全部' || region !== 'all' || dateFilter !== 'edition');
  $('#topic-filter').value = category; $('#region-filter').value = region;
  $('#filter-context').textContent = savedOnly ? '收藏跨刊保留；指定日期后只显示近 72 小时内容。' : dateFilter === 'edition' ? '本刊由 AI 挑选，最多 ' + editionLimit() + ' 条；选择日期可回看已收录新闻' : '近 72 小时已收录 ' + recentArticles().length + ' 条；以发布时间筛选，逐刊累积';
}
function updateSelection() {
  $('#selection-dock').hidden = selected.size === 0;
  $('#selection-count').textContent = selected.size;
  $('#selection-summary').textContent = '最多 6 条 · 切换筛选也会保留';
  $('#create-cards').disabled = selected.size === 0;
}
function selectArticle(id, checked) {
  if (!checked) selected.delete(id);
  else if (!selected.has(id)) {
    if (selected.size >= 6) { toast('一组最多 6 条新闻，先移除一条再添加。'); return false; }
    const article = findArticle(id); if (!article) return false;
    selected.set(id, article);
  }
  return true;
}
function render() {
  updateFilters();
  const pool = savedOnly ? collection() : dateFilter === 'edition' ? articles : recentArticles();
  const visible = filteredArticles();
  const ranked = !savedOnly && dateFilter === 'edition';
  updateSummary();
  $('#articles').innerHTML = visible.map(article => {
    const saved = state.saved.includes(article.id), read = state.read.includes(article.id);
    const current = articles.some(value => value.id === article.id), info = evidenceOf(article);
    const rank = articles.findIndex(value => value.id === article.id) + 1;
    const title = articleTitle(article), summary = article.language === 'en' && article.summaryZh ? article.summaryZh : article.summary;
    const translated = article.language === 'en' && (article.titleZh || article.summaryZh);
    const translationLabel = article.titleZh && article.summaryZh ? (article.brief ? '中文译文，AI 翻译' : '中文译文，机器翻译') : translated ? '部分中文，机器翻译' : '英文原文，翻译待补';
    const excerpt = '<details class="article-original"><summary>看来源原文摘录</summary><div>' +
      (article.language === 'en' ? '<p class="translation-label">' + translationLabel + '</p>' + (translated ? '<p>' + escapeHtml(summary) + '</p>' : '') + '<div lang="en"><p class="original-title">' + escapeHtml(article.title) + '</p><p>' + escapeHtml(article.summary) + '</p></div>' : '<p>' + escapeHtml(article.summary) + '</p>') + '</div></details>';
    return '<article id="article-' + article.id + '" tabindex="-1" class="article tier-' + info.tier + (ranked ? ' ranked' : '') + (ranked && rank === 1 ? ' lead' : '') + (read ? ' read' : '') + (selected.has(article.id) ? ' selected' : '') + '" data-id="' + article.id + '">' +
      (ranked ? '<span class="article-rank" aria-label="本刊第 ' + rank + ' 条">' + rank + '</span>' : '') + '<div class="evidence-gauge" aria-hidden="true">' + [1,2,3].map(cell => '<i' + (cell <= info.cells ? ' class="filled"' : '') + '></i>').join('') + '</div><div class="article-content">' +
      '<div class="article-tags"><span class="evidence-label">' + info.label + '</span><span>' + (article.category === 'AI' ? '人工智能' : article.category) + '</span><span>' + (articleRegion(article) === 'domestic' ? '国内' : '海外') + '</span>' + (!current ? '<span>往期</span>' : '') + (read ? '<span class="article-read-tag">读过</span>' : '') + '</div>' +
      '<h3><a href="' + escapeHtml(article.url) + '" target="_blank" rel="noopener noreferrer" data-read="' + article.id + '" aria-label="' + escapeHtml(title) + '（新窗口打开原文）">' + escapeHtml(title) + '</a></h3>' +
      '<p class="article-summary' + (!article.brief && article.summaryType === 'source-teaser' ? ' teaser' : '') + '">' + (!article.brief && article.summaryType === 'source-teaser' ? '<span class="excerpt-label">来源导语</span>' : '') + escapeHtml(article.brief || summary) + '</p>' +
      (article.why ? '<p class="article-why">' + escapeHtml(article.why) + '</p>' : '') + excerpt +
      '<div class="article-footer"><div class="article-meta"><span class="source-name">' + escapeHtml(article.source) + '</span><time datetime="' + escapeHtml(article.publishedAt || article.date) + '">' + (ago(article) || article.date.replaceAll('-', '.')) + '</time></div><div class="article-actions">' +
      '<button class="explain-button" type="button" data-explain="' + article.id + '" aria-label="问 AI：' + escapeHtml(title) + '">问 AI</button><a class="article-link" href="' + escapeHtml(article.url) + '" target="_blank" rel="noopener noreferrer" data-read="' + article.id + '">读原文</a>' +
      '<button class="article-icon" type="button" data-save="' + article.id + '" aria-pressed="' + saved + '" aria-label="' + (saved ? '取消收藏：' : '收藏：') + escapeHtml(title) + '"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h12v17l-6-4-6 4z"/></svg></button>' +
      '<button class="article-icon" type="button" data-select="' + article.id + '" aria-pressed="' + selected.has(article.id) + '" aria-label="' + (selected.has(article.id) ? '移出卡片：' : '选入卡片：') + escapeHtml(title) + '"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="m8 12 3 3 5-6"/></svg></button></div></div></div></article>';
  }).join('');
  $('#result-count').textContent = visible.length;
  $('#saved-count').textContent = collection().length;
  $('#saved-nav').setAttribute('aria-pressed', String(savedOnly));
  $('#feed-title').firstChild.textContent = savedOnly ? '我的收藏' : dateFilter === 'edition' ? '本刊精选' : dateFilter === 'recent' ? '近三天资讯' : dateFilter.replaceAll('-', '.');
  $('#active-view').hidden = ranked;
  $('#active-view-copy').textContent = savedOnly ? '正在查看收藏；顶部总结仍是本刊。' : '正在查看' + (dateFilter === 'recent' ? '近三天新闻' : dateFilter.replaceAll('-', '.')) + '；顶部总结仍是本刊。';
  $('#empty-state').hidden = visible.length !== 0;
  $('#list-end').hidden = visible.length === 0;
  const collectionEmpty = savedOnly && pool.length === 0;
  $('#empty-title').textContent = collectionEmpty ? '还没有收藏' : !savedOnly && !articles.length ? '还没有可用的简报' : '没有符合条件的新闻';
  $('#empty-copy').textContent = collectionEmpty ? '点击资讯右侧的书签图标，就能跨刊保留它。' : !savedOnly && !articles.length ? '启动简报后会自动采集，请稍后载入最新刊。' : '清除筛选后查看全部新闻。';
  document.querySelectorAll('.legacy-filter').forEach(button => {
    const active = button.dataset.category === category;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    if (button.dataset.category === '全部') button.querySelector('span').textContent = pool.length;
  });
  document.querySelectorAll('[data-region]').forEach(button => {
    const active = button.dataset.region === region;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    button.querySelector('span').textContent = pool.filter(article => button.dataset.region === 'all' || articleRegion(article) === button.dataset.region).length;
  });
  document.querySelectorAll('[data-topic]').forEach(button => { button.lastElementChild.textContent = String(articles.filter(article => article.category === button.dataset.topic).length); });
  updateProgress();
  updateSelection();
}
function updateProgress() {
  const count = articles.filter(article => state.read.includes(article.id)).length;
  $('#read-fraction').textContent = String(count);
  document.querySelector('.progress-track')?.setAttribute('aria-valuenow', String(articles.length ? Math.round(count / articles.length * 100) : 0));
  $('#progress-fill').style.width = (articles.length ? count / articles.length * 100 : 0) + '%';
  $('#progress-copy').textContent = count && count === articles.length ? '本刊 ' + articles.length + ' 条原文已全部打开。' : count ? '本刊 ' + articles.length + ' 条，已打开 ' + count + ' 条原文。' : '打开一条原文开始阅读。';
}
function resetView() { dateFilter = 'edition'; savedOnly = false; category = '全部'; region = 'all'; query = ''; $('#search').value = ''; render(); }
function scrollToFeed() { $('#news').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }); }
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { category = button.dataset.category; render(); }));
$('#topic-chips').addEventListener('click', event => {
  const button = event.target.closest('[data-category]'); if (!button) return;
  category = button.dataset.category; render();
  document.querySelector('#topic-chips [data-category="' + category + '"]')?.focus({preventScroll:true});
});
$('#evidence-strip').addEventListener('click', event => {
  const link = event.target.closest('[data-jump]'); if (!link) return;
  event.preventDefault(); jumpToArticle(link.dataset.jump);
});
document.querySelectorAll('[data-region]').forEach(button => button.addEventListener('click', () => { region = button.dataset.region; render(); }));
document.querySelectorAll('[data-topic]').forEach(button => button.addEventListener('click', () => { category = button.dataset.topic; region = 'all'; savedOnly = false; query = ''; $('#search').value = ''; render(); scrollToFeed(); }));
$('#date-filter').addEventListener('change', event => { dateFilter = event.target.value; render(); });
$('#topic-filter').addEventListener('change', event => { category = event.target.value; render(); });
$('#region-filter').addEventListener('change', event => { region = event.target.value; render(); });
$('#clear-filters').addEventListener('click', resetView);
$('#studio-start').addEventListener('click', () => { scrollToFeed(); toast('点新闻底部的选入卡片按钮，选 1–6 条后点击底部“生成卡片”。'); });
$('#clear-selection').addEventListener('click', () => { selected.clear(); render(); });
$('#create-cards').addEventListener('click', () => { if (selected.size) FrontierShare.open([...selected.values()]); });
FrontierShare.init({onChange(ids) { selected = new Map(ids.map(id => [id, findArticle(id)]).filter(([, row]) => row)); render(); }});
$('#search').addEventListener('input', event => { query = event.target.value; render(); });
$('#search').addEventListener('keydown', event => { if (event.key === 'Escape') { query = ''; event.target.value = ''; render(); event.target.blur(); } });
$('#saved-nav').addEventListener('click', () => { savedOnly = !savedOnly; dateFilter = 'edition'; category = '全部'; region = 'all'; query = ''; $('#search').value = ''; render(); scrollToFeed(); });
$('#back-all').addEventListener('click', resetView);
$('#reset-filters').addEventListener('click', resetView);
$('#reload-edition').addEventListener('click', () => { if (refreshState === 'ready') refreshState = ''; reloadEdition(true); });
$('#reset-reading').addEventListener('click', () => { const ids = new Set(articles.map(article => article.id)); state.read = state.read.filter(id => !ids.has(id)); const stored = persist(); render(); toast(stored ? '本刊阅读进度已重置' : '本次进度已重置，浏览器未允许保存'); });
FrontierReader.init(evidenceOf);
$('#articles').addEventListener('click', event => {
  const choice = event.target.closest('[data-select]');
  if (choice) { selectArticle(choice.dataset.select, !selected.has(choice.dataset.select)); render(); document.querySelector('[data-select="' + choice.dataset.select + '"]')?.focus({preventScroll:true}); return; }
  const explain = event.target.closest('[data-explain]');
  if (explain) {
    const article = findArticle(explain.dataset.explain);
    if (article) FrontierReader.open(article);
    return;
  }
  const bookmark = event.target.closest('[data-save]');
  if (bookmark) {
    const id = bookmark.dataset.save;
    const article = findArticle(id);
    if (!article) return;
    const saved = state.saved.includes(id);
    if (saved) { state.saved = state.saved.filter(value => value !== id); delete state.archive[id]; }
    else { state.saved.push(id); state.archive[id] = article; }
    const stored = persist();
    render();
    (document.querySelector('[data-save="' + id + '"]') || $('#saved-nav')).focus({ preventScroll: true });
    toast(stored ? (saved ? '已取消收藏' : '已收藏，往后更新也会保留') : '已在本次页面更新，浏览器未允许保存');
    return;
  }
  const link = event.target.closest('[data-read]');
  if (link && !state.read.includes(link.dataset.read)) {
    state.read.push(link.dataset.read);
    persist();
    const card = link.closest('.article');
    card.classList.add('read');
    const tag = document.createElement('span');
    tag.className = 'article-read-tag'; tag.textContent = '读过';
    card.querySelector('.article-tags').appendChild(tag);
    updateProgress();
  }
});
document.addEventListener('keydown', event => { if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName) && !document.activeElement.isContentEditable) { event.preventDefault(); $('#search').focus(); } });
window.addEventListener('storage', event => { if (event.key === storageKey || event.key === null) { state = readState(); render(); } });
window.addEventListener('focus', () => { reloadEdition(); requestRefresh(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) { reloadEdition(); requestRefresh(); } });
document.querySelectorAll('.brand, .footer-brand').forEach(link => link.addEventListener('click', resetView));
$('#today-date').textContent = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
try { if (window.__FRONTIER_DATA__) applyDigest(window.__FRONTIER_DATA__); } catch { loadFailed = true; }
render(); updateStatus(); reloadEdition(); requestRefresh();
setInterval(() => { render(); updateStatus(); if (!document.hidden) { reloadEdition(); requestRefresh(); } }, 60_000);
