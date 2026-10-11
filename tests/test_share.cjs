const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({TextEncoder,Uint8Array,Uint32Array,DataView,Date,console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'..','share.js'),'utf8'),context);
const share=context.FrontierShare;
const news={id:'news-1',category:'AI',title:'Original title',summary:'Original summary',titleZh:'中文标题',summaryZh:'中文摘要',source:'研究机构',date:'2026-10-10',url:'https://example.com/1',language:'en'};
test('card edits keep original source materials and generate a usable video handoff',()=>{
  const pack=share.buildPack([{...news,cardTitle:'新的卡片标题',cardSummary:'编辑后的摘要'}],{title:'前沿新知',theme:'night',caption:'我的配文'});
  assert.equal(pack.items[0].title,'新的卡片标题');
  assert.equal(pack.items[0].originalTitle,news.title);
  assert.equal(pack.items[0].originalSummary,news.summary);
  assert.equal(pack.items[0].url,news.url);
  assert.equal(pack.caption,'我的配文');
  assert.ok(pack.narration.join('').includes('编辑后的摘要'));
  assert.match(share.videoPrompt(pack),/cards\/01-news\.png/);
  assert.match(share.videoPrompt(pack),/https:\/\/example.com\/1/);
  assert.ok(pack.estimatedSeconds>=30);
  assert.throws(()=>share.buildPack([]));
  assert.throws(()=>share.buildPack(Array(7).fill(news)));
});
test('ZIP stores Unicode names and binary files with valid sizes, offsets and CRC',()=>{
  const files=[{name:'中文.txt',data:'hello 世界'},{name:'cards/00-cover.png',data:new Uint8Array([0,255,10,13,128])}];
  const zip=share.zipFiles(files); const view=new DataView(zip.buffer,zip.byteOffset,zip.byteLength);
  let offset=0;
  for(const file of files){
    assert.equal(view.getUint32(offset,true),0x04034b50);
    assert.equal(view.getUint16(offset+6,true),0x800);
    const nameLength=view.getUint16(offset+26,true),size=view.getUint32(offset+18,true);
    const payload=zip.slice(offset+30+nameLength,offset+30+nameLength+size);
    assert.equal(view.getUint32(offset+14,true),share.crc32(payload));
    assert.equal(new TextDecoder().decode(zip.slice(offset+30,offset+30+nameLength)),file.name);
    offset+=30+nameLength+size;
  }
  assert.equal(view.getUint32(offset,true),0x02014b50);
  const end=zip.length-22;
  assert.equal(view.getUint32(end,true),0x06054b50);
  assert.equal(view.getUint32(end+16,true),offset);
  assert.equal(view.getUint16(end+10,true),2);
  assert.equal(share.crc32(new TextEncoder().encode('123456789')),0xcbf43926);
});
test('wrapping bounds each line and truncates without breaking emoji codepoints',()=>{
  const ctx={measureText:text=>({width:Array.from(text).length*10})};
  const lines=share.wrapText(ctx,'研究😀原理以及 this_is_a_long_word 的创新',60,3);
  assert.equal(lines.length,3);
  assert.ok(lines.every(line=>Array.from(line).length<=6));
  assert.match(lines.at(-1),/…$/);
  assert.ok(!lines.join('').includes('\uFFFD'));
});
test('wrapping keeps Latin words whole and never starts a line with closing punctuation',()=>{
  const ctx={measureText:text=>({width:Array.from(text).length*10})};
  const lines=share.wrapText(ctx,'据报道，Linux Plumbers Conference 大会举行，工程师质疑',100);
  assert.ok(lines.every(line=>!/^[，。]/.test(line)));
  assert.ok(lines.some(line=>/(^| )Plumbers( |$)/.test(line)));
  assert.ok(!lines.join('|').includes('Plum|'));
});
