'use strict';
globalThis.FrontierShare = (() => {
  const palettes = {
    sage: {paper:'#f6f5ed', ink:'#243e33', muted:'#71806f', line:'#d9dfd1', accent:'#d9eaa8', soft:'#edf0e4'},
    night: {paper:'#192933', ink:'#f1f0e4', muted:'#a0b4b9', line:'#3c505b', accent:'#b5d6bd', soft:'#243b47'}
  };
  const short = (value, length) => {const chars=Array.from(String(value || '').replace(/\s+/g,' ').trim());return chars.length>length ? chars.slice(0,length-1).join('')+'…' : chars.join('');};
  const categoryName = value => value === 'AI' ? '人工智能' : value;
  function buildPack(rows, options = {}) {
    if (!Array.isArray(rows) || !rows.length || rows.length>6) throw new Error('请选择 1–6 条新闻。');
    const title=short(options.title || '今天，值得知道的几件事',40);
    const items=rows.map(row=>({id:row.id,category:categoryName(row.category),title:short(row.cardTitle || row.titleZh || row.title,100),summary:short(row.cardSummary ?? (row.brief || row.summaryZh || row.summary),320),source:row.source,date:row.date,url:row.url,originalTitle:row.title,originalSummary:row.summary,language:row.language}));
    const topicTags=[...new Set(items.map(row=>row.category))].map(value=>'#'+value).join(' ');
    const caption=title+'\n\n'+items.map((row,i)=>`${i+1}. ${row.title}\n${short(row.summary,140)}\n来源：${row.source} · ${row.date}`).join('\n\n')+'\n\n把不懂的术语问清楚，再看它的创新和实际进展。\n\n#前沿科技 #科技资讯 '+topicTags+'\n\n原文出处：\n'+items.map((row,i)=>`${i+1}. ${row.url}`).join('\n');
    const narration=['今天，一起看看这 '+items.length+' 条值得关注的前沿动态。',...items.map((row,i)=>`第${i+1}条，${short(row.title,36)}。${short(row.summary,85)}`),'你最想深入了解哪一条？可以继续追问它的原理、创新，以及离应用还有多远。'];
    const seconds=Math.max(30,Math.ceil(narration.join('').replace(/\s/g,'').length/4));
    return {version:1,title,theme:palettes[options.theme]?options.theme:'sage',size:{width:1080,height:1440},createdAt:options.createdAt || new Date().toISOString(),items,caption:options.caption ?? caption,narration,estimatedSeconds:seconds};
  }
  function videoPrompt(pack) {
    return `# 用这组前沿新闻卡片制作介绍视频\n\n请在当前目录实现一段可导出的中文竖屏介绍视频，使用此包里的图卡和新闻资料。先查看已有项目；沿用现有视频制作方式，若没有项目，可创建 Remotion 项目，并提供预览与导出命令。\n\n## 视频要求\n- 画面：1080 × 1920，30 fps。风格与图卡一致（${pack.theme==='night'?'午夜蓝':'纸感绿'}），留白充足，使用缓慢推近、卡片切换和重点文字动效。\n- 标题：${pack.title}\n- 根据下方口播稿安排镜头，按正常中文语速约 ${pack.estimatedSeconds} 秒；准确性优先，避免为了固定时长加编事实。\n- 卡片图片是 1080 × 1440，应完整置入视频安全区域，避免裁掉来源和日期。提供中文字幕，字幕不得遮挡卡片核心文字。\n- 不编造创新、实验效果、排名、商用时间或人物观点。明确新闻的发布日期，不能当作实时核验。人工编辑过的卡片内容也要对照原始摘要。\n- 使用已有且可用的配音资源；若未配置配音，先完成动画与字幕，附旁白文本和音频接入位置，不伪造已有配音。不要自动发布到任何平台。\n\n## 文件对应\n- cards/00-cover.png：封面。\n${pack.items.map((row,i)=>`- cards/${String(i+1).padStart(2,'0')}-news.png：${row.title}`).join('\n')}\n- news.json：新闻原始材料、卡片文字、来源链接和发布日期。\n- caption.txt：可编辑的分享配文。\n\n## 口播稿\n${pack.narration.map((line,i)=>`${i+1}. ${line}`).join('\n\n')}\n\n## 分镜建议\n1. 封面：标题出现，使用开场旁白，约 4–6 秒。\n2. 逐条新闻：切换对应图卡，跟随各段旁白展示标题、来源和关键句；按每段实际朗读长度分配时长。\n3. 结尾：回到封面并显示“你最想读懂哪一条？”，使用结束旁白。\n\n## 新闻资料\n${pack.items.map((row,i)=>`### ${i+1}. ${row.title}\n发布日期：${row.date}\n来源：${row.source}\n原文：${row.url}\n卡片摘要：${row.summary}\n原始标题：${row.originalTitle}\n原始摘要：${row.originalSummary}`).join('\n\n')}\n\n请交付源代码、可预览版本、导出命令和最终 MP4；缺少必要依赖或配音时明确说明，并保留可继续制作的工程。\n`;
  }
  const crcTable=Uint32Array.from({length:256},(_,i)=>{let n=i;for(let bit=0;bit<8;bit++)n=(n&1)?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
  function crc32(bytes) {let n=0xffffffff;for(const byte of bytes)n=crcTable[(n^byte)&255]^(n>>>8);return (n^0xffffffff)>>>0;}
  function zipFiles(files) {
    const encoder=new TextEncoder(), local=[], central=[];let offset=0, centralSize=0;
    const header=(length)=>{const bytes=new Uint8Array(length);return {bytes,view:new DataView(bytes.buffer)};};
    for(const file of files) {
      const name=encoder.encode(file.name),data=typeof file.data==='string'?encoder.encode(file.data):file.data,crc=crc32(data);
      const h=header(30);h.view.setUint32(0,0x04034b50,true);h.view.setUint16(4,20,true);h.view.setUint16(6,0x800,true);h.view.setUint16(12,0x21,true);h.view.setUint32(14,crc,true);h.view.setUint32(18,data.length,true);h.view.setUint32(22,data.length,true);h.view.setUint16(26,name.length,true);
      local.push(h.bytes,name,data);
      const c=header(46);c.view.setUint32(0,0x02014b50,true);c.view.setUint16(4,20,true);c.view.setUint16(6,20,true);c.view.setUint16(8,0x800,true);c.view.setUint16(14,0x21,true);c.view.setUint32(16,crc,true);c.view.setUint32(20,data.length,true);c.view.setUint32(24,data.length,true);c.view.setUint16(28,name.length,true);c.view.setUint32(42,offset,true);
      central.push(c.bytes,name);centralSize+=46+name.length;offset+=30+name.length+data.length;
    }
    const end=header(22);end.view.setUint32(0,0x06054b50,true);end.view.setUint16(8,files.length,true);end.view.setUint16(10,files.length,true);end.view.setUint32(12,centralSize,true);end.view.setUint32(16,offset,true);
    const result=new Uint8Array(offset+centralSize+22);let cursor=0;
    for(const chunk of [...local,...central,end.bytes]){result.set(chunk,cursor);cursor+=chunk.length;}
    return result;
  }
  function wrapText(ctx,text,width,maxLines=100) {
    // Latin words wrap whole; spaces are separate units so a phrase can break between words.
    const units=String(text).match(/[a-zA-Z0-9._:/+%'-]+|\n|[^\S\n]+|./gu)||[];
    const closing=/^[，。、；：！？）」』”’》〉】,.;:!?)\]%]$/u;
    const lines=[];let line='';
    for(const unit of units){
      if(unit==='\n'){lines.push(line.trimEnd());line='';continue;}
      if(/^\s+$/.test(unit)){if(line)line+=' ';continue;}
      if(ctx.measureText(unit).width>width){for(const char of Array.from(unit)){if(ctx.measureText(line+char).width>width && line){lines.push(line.trimEnd());line='';}line+=char;}continue;}
      // Closing punctuation hangs on the previous line instead of starting a new one.
      if(ctx.measureText(line+unit).width>width && line.trim() && !closing.test(unit)){lines.push(line.trimEnd());line='';}
      line+=unit;
    }
    if(line)lines.push(line.trimEnd());
    if(lines.length>maxLines){lines.length=maxLines;let last=lines[maxLines-1];while(last && ctx.measureText(last+'…').width>width)last=Array.from(last).slice(0,-1).join('');lines[maxLines-1]=last+'…';}
    return lines;
  }
  function drawCard(canvas,pack,pageIndex) {
    canvas.width=1080;canvas.height=1440;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器无法绘制卡片。');
    const p=palettes[pack.theme],font='"Microsoft YaHei", "PingFang SC", sans-serif';
    ctx.fillStyle=p.paper;ctx.fillRect(0,0,1080,1440);
    ctx.strokeStyle=p.line;ctx.lineWidth=1;
    for(let x=90;x<1000;x+=48){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,1440);ctx.stroke();}
    ctx.fillStyle=p.paper;ctx.fillRect(58,160,964,1160);
    const text=(value,x,y,size=30,color=p.ink,weight=400)=>{ctx.fillStyle=color;ctx.font=`${weight} ${size}px ${font}`;ctx.fillText(value,x,y);};
    const rule=y=>{ctx.strokeStyle=p.line;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(90,y);ctx.lineTo(990,y);ctx.stroke();};
    const paragraph=(value,x,y,size,width,maxLines,lineHeight,weight=400)=>{ctx.font=`${weight} ${size}px ${font}`;ctx.fillStyle=p.ink;const lines=wrapText(ctx,value,width,maxLines);lines.forEach((line,i)=>ctx.fillText(line,x,y+i*lineHeight));return lines.length;};
    text('前沿简报',90,103,31,p.ink,700);text('THE FRONTIER',90,141,17,p.muted,500);text(`${String(pageIndex+1).padStart(2,'0')} / ${String(pack.items.length+1).padStart(2,'0')}`,861,103,24,p.muted);
    if(pageIndex===0){
      ctx.strokeStyle=p.accent;ctx.lineWidth=16;ctx.beginPath();ctx.arc(913,345,123,0,Math.PI*2);ctx.stroke();ctx.strokeStyle=p.line;ctx.lineWidth=2;ctx.beginPath();ctx.arc(913,345,172,0,Math.PI*2);ctx.stroke();
      ctx.fillStyle=p.paper;ctx.fillRect(74,213,840,378);
      paragraph(pack.title,90,284,78,880,4,94,700);
      text(`${pack.items.length} 条精选  /  读懂，再分享`,90,619,28,p.muted);
      rule(673);text('这一组，值得知道',90,715,25,p.muted,500);
      pack.items.forEach((row,i)=>{const y=782+i*81;text(String(i+1).padStart(2,'0'),90,y,24,p.muted);paragraph(short(row.title,46),155,y,27,818,2,34,500);});
      rule(1300);text('一点好奇心，一点新见识。',90,1350,25,p.ink,500);
    }else{
      const row=pack.items[pageIndex-1];
      ctx.fillStyle=p.accent;ctx.beginPath();ctx.roundRect(90,204,Math.max(168,row.category.length*27+48),54,15);ctx.fill();text(row.category,114,242,25,'#243e33',600);
      const headlineSize = row.title.length > 65 ? 42 : row.title.length > 45 ? 50 : 60, headlineLine=Math.round(headlineSize*1.28);
      paragraph(row.title,90,340,headlineSize,900,Math.min(5,Math.floor(250/headlineLine)+1),headlineLine,700);
      text(short(row.source,24),90,641,25,p.muted);text(row.date,817,641,25,p.muted);rule(685);
      text('发生了什么',90,752,27,p.muted,600);
      const summarySize = row.summary.length > 240 ? 29 : 34, summaryLine=Math.round(summarySize*1.5);
      paragraph(row.summary || '这条新闻暂无摘要，请查看原文。',90,824,summarySize,900,Math.floor(440/summaryLine)+1,summaryLine);
      rule(1300);text('来源摘要 · 保留原文出处',90,1350,24,p.muted);text('READ · ASK · SHARE',708,1350,19,p.muted);
    }
    return canvas;
  }
  let items=[],page=0,theme='sage',title='今天，值得知道的几件事',captionEdited=false,captionDraft='',onChange=()=>{};
  const edits=new Map();const $=id=>document.getElementById(id);
  const pack=()=>buildPack(items,{title,theme,...(captionEdited?{caption:captionDraft}:{})});
  function render() {
    const value=pack();page=Math.min(Math.max(page,0),items.length);drawCard($('share-canvas'),value,page);
    $('share-page-label').textContent=(page?'新闻 '+page:'封面')+' '+(page+1)+' / '+(items.length+1);
    $('share-prev').disabled=page===0;$('share-next').disabled=page===items.length;
    document.querySelectorAll('[data-share-theme]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.shareTheme===theme)));
    $('share-selected').replaceChildren();
    items.forEach((row,i)=>{
      const li=document.createElement('li'),label=document.createElement('button');label.type='button';label.className='share-selected-title';label.textContent=(i+1)+'. '+(row.cardTitle || row.titleZh || row.title);label.setAttribute('aria-pressed',String(page===i+1));label.onclick=()=>{page=i+1;render();};li.append(label);
      for(const [action,symbol,name,disabled] of [['up','↑','上移',i===0],['down','↓','下移',i===items.length-1],['remove','×','移除',items.length===1]]){
        const button=document.createElement('button');button.type='button';button.textContent=symbol;button.setAttribute('aria-label',name+'第'+(i+1)+'条新闻');button.disabled=disabled;
        button.onclick=()=>{if(action==='remove'){items.splice(i,1);page=Math.min(page,items.length);}else{const next=action==='up'?i-1:i+1;[items[i],items[next]]=[items[next],items[i]];page=next+1;}onChange(items.map(row=>row.id));render();};li.append(button);
      }
      $('share-selected').append(li);
    });
    const current=page?value.items[page-1]:null;
    $('share-edit-hint').textContent=current?'修改只影响分享卡片，新闻原始材料仍在资料包中保留。':'切换到新闻卡片后，可调整标题和摘要。';
    $('share-item-title').disabled=!current;$('share-item-summary').disabled=!current;
    $('share-item-title').value=current?.title || '';$('share-item-summary').value=current?.summary || '';
    $('share-caption').value=value.caption;$('share-video').value=videoPrompt(value);
  }
  function download(blob,name) {const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  const png=canvas=>new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('没有生成图片，请重试。')),'image/png'));
  async function exportCards(all) {
    const button=$('share-download-all');button.disabled=true;$('share-download-current').disabled=true;
    $('share-status').textContent=all?'正在生成整组图片和视频资料…':'正在生成当前图片…';
    try{
      await document.fonts.ready;const value=pack(),canvas=document.createElement('canvas');
      if(!all){const blob=await png(drawCard(canvas,value,page));download(blob,'frontier-'+(page?'news-'+page:'cover')+'.png');}
      else{
        const files=[];
        for(let i=0;i<=value.items.length;i++){const blob=await png(drawCard(canvas,value,i));files.push({name:'cards/'+String(i).padStart(2,'0')+(i?'-news.png':'-cover.png'),data:new Uint8Array(await blob.arrayBuffer())});}
        files.push({name:'caption.txt',data:value.caption},{name:'claude-video.md',data:videoPrompt(value)},{name:'news.json',data:JSON.stringify(value,null,2)}, {name:'README.txt',data:'先查看 cards 文件夹里的图卡；caption.txt 是分享配文。需要制作视频时，把 claude-video.md 交给 Claude Code，并让它在此目录工作。news.json 保留原始新闻材料和卡片文字。图片为 1080×1440 PNG。卡片中未显示的长标题或摘要，请以 news.json 和原文为准。内容请自行核对后发布。'});
        download(new Blob([zipFiles(files)],{type:'application/zip'}),'前沿简报-'+new Date(Date.now()+8*3600_000).toISOString().slice(0,10)+'.zip');
      }
      $('share-status').textContent=all?'已下载资料包：图卡、配文、新闻出处和 Claude Code 视频提示词。':'已下载当前 PNG 图片。';
    }catch(error){$('share-status').textContent='导出失败：'+error.message;}
    finally{button.disabled=false;$('share-download-current').disabled=false;}
  }
  async function copy(id) {const field=$(id);try{await navigator.clipboard.writeText(field.value);$('share-status').textContent='已复制。';}catch{field.closest('details').open=true;field.focus();field.select();$('share-status').textContent='已选中文本，请按 Ctrl+C 或长按复制。';}}
  function init(options={}) {
    onChange=options.onChange || (()=>{});
    $('share-close').onclick=()=>$('share-dialog').close();
    $('share-prev').onclick=()=>{page--;render();};$('share-next').onclick=()=>{page++;render();};
    $('share-title').addEventListener('input',()=>{title=$('share-title').value;render();});
    document.querySelectorAll('[data-share-theme]').forEach(button=>button.onclick=()=>{theme=button.dataset.shareTheme;render();});
    for(const [id,key] of [['share-item-title','cardTitle'],['share-item-summary','cardSummary']])$(id).addEventListener('input',()=>{
      if(!page)return;const field=$(id),cursor=field.selectionStart,raw=field.value;items[page-1][key]=field.value;edits.set(items[page-1].id,{cardTitle:items[page-1].cardTitle,cardSummary:items[page-1].cardSummary});render();field.value=raw;field.focus();field.setSelectionRange(cursor,cursor);
    });
    $('share-caption').addEventListener('input',()=>{captionEdited=true;captionDraft=$('share-caption').value;});
    $('share-copy-caption').onclick=()=>copy('share-caption');$('share-copy-video').onclick=()=>copy('share-video');
    $('share-download-current').onclick=()=>exportCards(false);$('share-download-all').onclick=()=>exportCards(true);
  }
  function open(rows) {
    items=rows.map(row=>({...row,...edits.get(row.id)}));page=0;captionEdited=false;captionDraft='';
    $('share-title').value=title;$('share-status').textContent='先预览，满意后下载。图卡不会自动发布。';
    render();$('share-dialog').showModal();
  }
  return {init,open,buildPack,videoPrompt,zipFiles,crc32,wrapText,drawCard};
})();
