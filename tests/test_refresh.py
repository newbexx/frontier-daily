import copy
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

spec = importlib.util.spec_from_file_location('refresh',Path(__file__).resolve().parents[1]/'tools'/'refresh.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,10,12,tzinfo=r.CST)
        self.source = {'name':'Test','url':'https://example.com/feed','language':'zh','category':None}
    def article(self, title='AI 模型发布', url='https://example.com/1', category='AI'):
        return {'id':url,'title':title,'url':url,'category':category,'language':'zh','source':'Test','publishedAt':self.now.isoformat()}
    def test_timezone_and_missing_timezone(self):
        self.assertEqual(r.parse_date('Fri, 09 Oct 2026 18:00:00 +0000').date().isoformat(),'2026-10-10')
        self.assertIsNone(r.parse_date('2026-10-10T08:00:00'))
    def test_source_timezone_is_explicit_and_preserves_aware_dates(self):
        self.assertEqual(r.parse_date('2026-10-10 00:05', assume='Asia/Shanghai').isoformat(), '2026-10-10T00:05:00+08:00')
        self.assertEqual(r.parse_date('2026-10-09 16:05', assume=r.timezone.utc).isoformat(), '2026-10-10T00:05:00+08:00')
        self.assertEqual(r.parse_date('2026-10-09T16:05:00Z', assume='Asia/Shanghai').isoformat(), '2026-10-10T00:05:00+08:00')
        self.assertIsNone(r.parse_date('2026-10-10 00:05'))
        self.assertIsNone(r.parse_date('2026-10-10 00:05', assume='Unknown/Zone'))
        self.assertIsNone(r.parse_date('not a date', assume='Asia/Shanghai'))
    def test_configured_source_timezone_keeps_midnight_and_time_window_boundaries(self):
        now = self.now.replace(hour=0, minute=5)
        dates = [now-timedelta(minutes=5), now+timedelta(minutes=10), now+timedelta(minutes=11),
                 now-timedelta(hours=72), now-timedelta(hours=72, minutes=1)]
        entries = ''.join('<item><title>研究进展</title><link>/article/'+str(index)+'?utm_source=rss</link>'
                          '<pubDate>'+date.strftime('%Y-%m-%d %H:%M')+'</pubDate><description>团队完成了测量，并报告研究结果。</description></item>'
                          for index,date in enumerate(dates))
        payload = ('<?xml version="1.0" encoding="utf-8"?><rss><channel>'+entries+'</channel></rss>').encode('utf-8')
        rows,total = r.parse_feed(payload,{**self.source,'timezone':'Asia/Shanghai'},now)
        self.assertEqual(total,5)
        self.assertEqual([row['url'] for row in rows],['https://example.com/article/0','https://example.com/article/1','https://example.com/article/3'])
        self.assertEqual(rows[0]['publishedAt'],'2026-10-10T00:00:00+08:00')
        self.assertEqual(rows[2]['publishedAt'],'2026-10-07T00:05:00+08:00')
        self.assertEqual(rows[0]['context'],'团队完成了测量，并报告研究结果。')
        unconfigured,_ = r.parse_feed(payload,self.source,now)
        self.assertEqual(unconfigured,[])
    def test_tracking_removed_and_unsafe_link_rejected(self):
        self.assertEqual(r.canonical_url('https://example.com/a?utm_source=rss&id=1#part'),'https://example.com/a?id=1')
        self.assertIsNone(r.canonical_url('javascript:alert(1)'))
    def test_feed_drops_stale_future_unsafe_and_undated(self):
        entries = ''.join('<item><title>AI 模型发布</title><link>'+link+'</link><pubDate>'+date+'</pubDate><description>模型能力获得提升。</description></item>' for link,date in [
            ('https://example.com/good','Sat, 10 Oct 2026 03:00:00 +0000'),
            ('https://example.com/old','Mon, 05 Oct 2026 03:00:00 +0000'),
            ('https://example.com/future','Sun, 11 Oct 2026 03:00:00 +0000'),
            ('javascript:alert(1)','Sat, 10 Oct 2026 03:00:00 +0000'),
            ('https://example.com/undated','')])
        rows,_ = r.parse_feed(('<rss><channel>'+entries+'</channel></rss>').encode(),self.source,self.now)
        self.assertEqual([row['url'] for row in rows],['https://example.com/good'])
    def test_atom_is_supported(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New AI model</title><link href="https://example.com/atom"/><updated>2026-10-10T03:00:00Z</updated><summary>Model update.</summary></entry></feed>'
        rows,_=r.parse_feed(xml,self.source,self.now)
        self.assertEqual(len(rows),1)
    def test_rss1_science_news_keeps_namespaced_title_link_excerpt_and_date(self):
        xml = b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Researchers test a new material</title><link>https://example.com/science?utm_source=rss</link><description>A research team tested a flexible material using independent measurements.</description><dc:date>2026-10-10T03:00:00Z</dc:date></item></rdf:RDF>'
        rows,total=r.parse_feed(xml,{**self.source,'language':'en'},self.now)
        self.assertEqual(total,1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['title'],'Researchers test a new material')
        self.assertEqual(rows[0]['url'],'https://example.com/science')
        self.assertEqual(rows[0]['publishedAt'],'2026-10-10T11:00:00+08:00')
        self.assertTrue(rows[0]['context'].startswith('A research team'))
        self.assertEqual(rows[0]['language'],'en')
        self.assertIsNone(rows[0]['category'])  # The editor still decides the topic.
    def test_rss1_does_not_bypass_window_timezone_link_or_sales_filters(self):
        entries=''.join('<item><title>'+title+'</title><link>'+url+'</link><dc:date>'+date+'</dc:date></item>' for title,url,date in [
            ('New quantum experiment','https://example.com/good','2026-10-10T03:00:00Z'),
            ('Old experiment','https://example.com/old','2026-10-05T03:00:00Z'),
            ('Future experiment','https://example.com/future','2026-10-11T03:00:00Z'),
            ('Unknown timezone','https://example.com/naive','2026-10-10'),
            ('Unsafe article','javascript:alert(1)','2026-10-10T03:00:00Z'),
            ('Image of the Day','https://example.com/picture','2026-10-10T03:00:00Z')])
        xml=('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">'+entries+'</rdf:RDF>').encode()
        rows,total=r.parse_feed(xml,self.source,self.now)
        self.assertEqual(total,6)
        self.assertEqual([row['url'] for row in rows],['https://example.com/good'])
    def test_url_and_title_deduplication(self):
        candidates=[self.article(),self.article(url='https://example.com/2'),self.article(title='AI模型发布！',url='https://example.com/3')]
        self.assertEqual(len(r.unique_articles(candidates)),1)
    def test_failure_keeps_last_good_data_and_timestamp(self):
        previous={'articles':[self.article()],'generatedAt':'2026-10-09T08:00:00+08:00','lastSuccessAt':'2026-10-09T08:00:00+08:00','editionDate':'2026-10-09'}
        digest=r.build_digest(self.now,[],[{'status':'error'}],previous)
        self.assertEqual(digest['articles'],previous['articles'])
        self.assertEqual(digest['lastSuccessAt'],previous['lastSuccessAt'])
        self.assertEqual(digest['status'],'failed')
    def test_digest_records_successful_settings_but_retains_previous_settings_on_failure(self):
        previous={'articles':[self.article()],'articleLimit':10,'minScore':4}
        digest=r.build_digest(self.now,[self.article()],[{'status':'ok'}],previous,limit=2,min_score=5)
        self.assertEqual((digest['articleLimit'],digest['minScore']),(2,5))
        failed=r.build_digest(self.now,[],[{'status':'error'}],previous,limit=2,min_score=5)
        self.assertEqual((failed['articleLimit'],failed['minScore']),(10,4))
        self.assertEqual(failed['articles'],previous['articles'])
        legacy=r.build_digest(self.now,[],[{'status':'error'}],{'articles':[self.article()]},limit=2,min_score=5)
        self.assertEqual((legacy['articleLimit'],legacy['minScore']),(15,3))
    def test_daily_due_before_and_after_0800(self):
        previous={'lastSuccessAt':'2026-10-09T09:00:00+08:00'}
        self.assertFalse(r.is_due(self.now.replace(hour=7),previous))
        self.assertTrue(r.is_due(self.now,previous))
        self.assertFalse(r.is_due(self.now,{'lastSuccessAt':'2026-10-10T08:01:00+08:00'}))
    def test_html_excerpt_and_english_word_limit(self):
        self.assertEqual(r.summarize('<script>bad()</script><p>这是一条摘要。</p>后续段落'),'这是一条摘要。')
        self.assertLessEqual(len(r.summarize(' '.join(['word']*40),'en').split()),24)
    def test_feed_summary_prefers_description_over_photo_credit(self):
        xml=('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>NASA rocket test</title><link>https://example.com/n</link>'
             '<pubDate>Sat, 10 Oct 2026 03:00:00 +0000</pubDate><description>The agency released a request for proposals for new commercial stations in orbit.</description>'
             '<content:encoded>Credit: NASA/Jordan Cochran A photo caption that is not the story.</content:encoded></item></channel></rss>').encode()
        rows,_=r.parse_feed(xml,{**self.source,'language':'en'},self.now)
        self.assertTrue(rows[0]['summary'].startswith('The agency released'))
    def test_navigation_boilerplate_is_not_an_excerpt(self):
        self.assertEqual(r.excerpt_text('Earth Observatory Image of the Day EO Explorer Topics All Topics Atmosphere'),'')
        self.assertEqual(r.excerpt_text('4 min read Heat shields keep crews safe.'),'Heat shields keep crews safe.')
    def test_one_line_hooks_are_marked_as_teasers(self):
        self.assertTrue(r.is_teaser('大写的方便'))
        self.assertFalse(r.is_teaser('联想天禧AI自主研发的专业代码智能体框架以71%的问题解决率登顶'))
        self.assertFalse(r.is_teaser('Short.','en'))
    def test_atomic_output_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'latest.json'
            r.atomic_text(target,'{"ok":true}')
            self.assertEqual(target.read_text(encoding='utf-8'),'{"ok":true}')
            self.assertEqual(len(list(Path(directory).iterdir())),1)



class SelectionSettingsTests(unittest.TestCase):
    def test_missing_or_unreadable_settings_use_defaults(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)):
            self.assertEqual(r.read_selection_settings(),{'min_score':3,'limit':15})
            (Path(folder)/'ai-settings.json').mkdir()
            self.assertEqual(r.read_selection_settings(),{'min_score':3,'limit':15})
    def test_valid_settings_include_score_bounds_and_limits_above_default(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)):
            target=Path(folder)/'ai-settings.json'
            for score,limit in [(0,1),(4,10),(5,100)]:
                with self.subTest(score=score,limit=limit):
                    target.write_text(json.dumps({'model':'test','minScore':score,'limit':limit}),encoding='utf-8-sig')
                    self.assertEqual(r.read_selection_settings(),{'min_score':score,'limit':limit})
    def test_invalid_fields_fall_back_independently(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)):
            target=Path(folder)/'ai-settings.json'
            for value in [None,True,False,'4',4.0,-1,6,[],{}]:
                with self.subTest(field='minScore',value=value):
                    target.write_text(json.dumps({'minScore':value,'limit':7}),encoding='utf-8')
                    self.assertEqual(r.read_selection_settings(),{'min_score':3,'limit':7})
            for value in [None,True,False,'10',10.0,0,-1,[],{}]:
                with self.subTest(field='limit',value=value):
                    target.write_text(json.dumps({'minScore':4,'limit':value}),encoding='utf-8')
                    self.assertEqual(r.read_selection_settings(),{'min_score':4,'limit':15})
            for value,expected in [({'limit':7},{'min_score':3,'limit':7}),({'minScore':4},{'min_score':4,'limit':15})]:
                target.write_text(json.dumps(value),encoding='utf-8')
                self.assertEqual(r.read_selection_settings(),expected)
    def test_corrupt_or_non_object_settings_use_defaults(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)):
            target=Path(folder)/'ai-settings.json'
            for payload in [b'',b'{broken',b'[]',b'null',b'4',b'true',b'"text"',b'\xff',b'{"model":"test"}']:
                with self.subTest(payload=payload):
                    target.write_bytes(payload)
                    self.assertEqual(r.read_selection_settings(),{'min_score':3,'limit':15})


class HistoryTests(unittest.TestCase):
    def test_archive_merges_editions_preserves_translations_and_expires_by_publication(self):
        now='2026-10-11T08:00:00+08:00'
        row=lambda id,time: {'id':id,'date':time[:10],'publishedAt':time,'title':'AI model','titleZh':'中文标题','summaryZh':'中文摘要'}
        boundary=row('boundary','2026-10-08T08:00:00+08:00')
        stale=row('stale','2026-10-08T07:59:59+08:00')
        future=row('future','2026-10-11T08:00:01+08:00')
        translated=row('repeated','2026-10-10T10:00:00+08:00')
        new={**translated,'title':'updated','titleZh':'','summaryZh':''}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'DATA',Path(folder)), patch.object(r,'read_previous',return_value={'articles':[boundary,stale,future,translated]}):
            result=r.recent_history({'lastSuccessAt':now,'articles':[new]})
            self.assertEqual({row['id'] for row in result},{'boundary','repeated'})
            self.assertEqual(result[0]['title'],'updated')
            self.assertEqual(result[0]['titleZh'],'中文标题')
            self.assertEqual(result[0]['summaryZh'],'中文摘要')
    def test_failed_edition_keeps_archive_at_last_success_and_malformed_archive_is_ignored(self):
        row={'id':'old','date':'2026-10-08','publishedAt':'2026-10-08T09:00:00+08:00'}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'DATA',Path(folder)), patch.object(r,'read_previous',return_value={'historyArticles':None,'articles':[row]}):
            (Path(folder)/'history.json').write_text('{"articles":null}',encoding='utf-8')
            result=r.recent_history({'status':'failed','lastSuccessAt':'2026-10-10T08:00:00+08:00','lastAttemptAt':'2026-10-13T08:00:00+08:00','articles':[row]})
            self.assertEqual([row['id'] for row in result],['old'])


def reply(items):
    return json.dumps({'items': items}, ensure_ascii=False)

class EditorTests(unittest.TestCase):
    now = datetime(2026,10,12,9,tzinfo=r.CST)
    config = {'endpoint':'http://127.0.0.1:1/v1','model':'cheap','key':'k','wire':'responses'}
    def row(self, id, language='zh', source='国内', hours=1, category=None):
        return {'id':id,'title':'标题'+id if language=='zh' else 'Title '+id,'summary':'摘录'+id if language=='zh' else 'Excerpt '+id,
                'context':'更多内容','source':source,'language':language,'url':'https://example.com/'+id,'category':category,
                'date':'2026-10-12','publishedAt':(self.now-timedelta(hours=hours)).isoformat(),'summaryType':'source-excerpt'}
    def test_sales_rumours_and_picture_posts_are_dropped_before_the_editor(self):
        self.assertTrue(r.excluded('399 元，小米超薄磁吸充电宝上架'))
        self.assertTrue(r.excluded('APOD: 2026 October 10 – Lunar Farside'))
        self.assertTrue(r.excluded('曝某厂新芯片下月发布'))
        self.assertFalse(r.excluded('国产芯片实现新突破'))
    def test_choice_prefers_scores_skips_old_editions_and_keeps_both_regions(self):
        rows=[self.row(f'zh{i}',hours=i) for i in range(6)]+[self.row(f'en{i}','en','海外',hours=i) for i in range(3)]+[self.row('old')]
        scores={row['id']:{'score':4,'category':'AI'} for row in rows}
        scores.update({'zh0':{'score':5,'category':'芯片'},'zh5':{'score':2,'category':'AI'},'en2':{'score':4,'category':'无'}})
        chosen=r.choose(rows,scores,{'old':'2026-10-11','zh1':'2026-10-12'},'2026-10-12',limit=6)
        ids=[row['id'] for row in chosen]
        self.assertEqual(ids[0],'zh0')
        self.assertTrue(chosen[0]['featured'])
        self.assertNotIn('old',ids)         # shown in yesterday's edition
        self.assertIn('zh1',ids)            # shown earlier today: a manual re-run keeps it
        self.assertNotIn('zh5',ids)         # below the bar
        self.assertNotIn('en2',ids)         # outside every topic
        self.assertEqual(sum(row['language']=='en' for row in chosen),2)
        self.assertLessEqual(sum(row['category']=='AI' for row in chosen),4)
    def test_configured_threshold_is_inclusive_and_default_still_allows_three(self):
        rows=[self.row('low'),self.row('middle'),self.row('high')]
        scores={row['id']:{'score':score,'category':'AI'} for row,score in zip(rows,[3,4,5])}
        self.assertEqual([row['id'] for row in r.choose(rows,scores,{},'2026-10-12',min_score=4)],['high','middle'])
        self.assertEqual(len(r.choose(rows,scores,{},'2026-10-12')),3)
        self.assertEqual([row['id'] for row in r.choose(rows,scores,{},'2026-10-12',limit=1)],['high'])
    def test_zero_threshold_still_rejects_unscored_and_unknown_topics(self):
        rows=[self.row('zero'),self.row('missing'),self.row('unscored'),self.row('outside')]
        scores={'zero':{'score':0,'category':'AI'},'unscored':{'category':'AI'},'outside':{'score':5,'category':'无'}}
        self.assertEqual([row['id'] for row in r.choose(rows,scores,{},'2026-10-12',min_score=0)],['zero'])
    def test_refresh_applies_changed_settings_to_cached_scores_and_digest(self):
        rows=[self.row('low'),self.row('middle'),self.row('high')]
        cache={'triage':{row['id']:{'score':score,'category':'AI','evidence':'实测或观测','triageVersion':r.TRIAGE_VERSION} for row,score in zip(rows,[3,4,5])},
               'edit':{row['id']:{'brief':'一句话说明。','why':'研究数据。'} for row in rows}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); data=root/'data'; data.mkdir()
            (data/'editor-cache.json').write_text(json.dumps(cache),encoding='utf-8')
            with patch.object(r,'ROOT',root), patch.object(r,'DATA',data), patch.object(r,'SOURCES',[{'name':'Test'}]), \
                 patch.object(r,'read_previous',return_value={}), patch.object(r,'fetch_source',return_value=(rows,{'name':'Test','status':'ok'})), \
                 patch.object(r,'write_digest') as written, patch.object(r,'RotatingFileHandler',lambda *args,**kwargs:r.logging.NullHandler()), \
                 patch.object(r.serve,'read_current_config',return_value=self.config), patch.object(r.serve,'call_model',return_value=json.dumps({'order':['n1','n2','n3']})) as model, \
                 patch.object(r,'datetime') as clock, patch('builtins.print'):
                clock.now.return_value=self.now; clock.fromisoformat=datetime.fromisoformat
                for settings,expected in [({'minScore':4,'limit':1},['high']),({'minScore':3,'limit':3},['high','middle','low'])]:
                    with self.subTest(settings=settings):
                        (root/'ai-settings.json').write_text(json.dumps(settings),encoding='utf-8')
                        self.assertEqual(r.refresh(),0)
                        digest=written.call_args.args[0]
                        self.assertEqual([row['id'] for row in digest['articles']],expected)
                        self.assertEqual(digest['articleLimit'],settings['limit'])
                        self.assertEqual(digest['minScore'],settings['minScore'])
                self.assertEqual(model.call_count,2)  # Final review runs for each edition; cached scores are reused.
    def test_edition_is_edited_once_and_cached(self):
        rows=[self.row('cn'),self.row('en','en','海外')]
        answers=[reply([{'n':'n1','score':4,'category':'AI','evidence':'动物或细胞'},{'n':'n2','score':5,'category':'航天','evidence':'实测或观测'}]),
                 json.dumps({'order':['n1','n2']}),
                 reply([{'n':'n2','brief':'一句话讲清国内新闻。','why':'新方法，有数据。'},
                        {'n':'n1','brief':'一句话讲清海外新闻。','why':'新发现，有论文。','titleZh':'海外标题','summaryZh':'海外摘录。'}]), json.dumps({'order':['n1','n2']})]
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'DATA',Path(folder)), \
             patch.object(r.serve,'read_current_config',return_value=self.config), patch.object(r.serve,'call_model',side_effect=answers) as model:
            result=r.edit_edition(rows,{},self.now)
            self.assertEqual(model.call_count,3)
            by_id={row['id']:row for row in result}
            self.assertEqual(by_id['en']['titleZh'],'海外标题')
            self.assertEqual(by_id['cn']['brief'],'一句话讲清国内新闻。')
            self.assertNotIn('titleZh',by_id['cn'])
            self.assertNotIn('context',by_id['cn'])
            self.assertEqual(by_id['cn']['firstShown'],'2026-10-12')
            self.assertEqual(result[0]['id'],'en')
            again=r.edit_edition(rows,{},self.now)
            self.assertEqual(model.call_count,4)
            self.assertEqual([row['id'] for row in again],[row['id'] for row in result])
    def test_malformed_reply_is_retried_once_then_given_up(self):
        rows=[self.row('one')]
        with patch.object(r.serve,'call_model',side_effect=['不是 JSON',reply([{'n':'n1','score':3,'category':'AI','evidence':'方法提出'}])]) as model:
            self.assertEqual(r.triage(self.config,rows),{'one':{'score':3,'category':'AI','evidence':'方法提出','triageVersion':r.TRIAGE_VERSION}})
            self.assertEqual(model.call_count,2)
        with patch.object(r.serve,'call_model',return_value=reply([{'n':'n1','score':9,'category':'AI','evidence':'其他'}])) as model:
            self.assertEqual(r.triage(self.config,rows),{})
            self.assertEqual(model.call_count,2)
    def test_english_news_needs_a_chinese_translation(self):
        row=self.row('en','en','海外')
        with patch.object(r.serve,'call_model',return_value=reply([{'n':'n1','brief':'一句话。','why':'原因。','titleZh':'Untranslated','summaryZh':'摘录。'}])):
            self.assertEqual(r.edit(self.config,[row]),{})
    def test_unreachable_editor_postpones_the_edition_and_keeps_the_last_one(self):
        previous={'version':2,'status':'ok','articles':[self.row('kept')],'lastSuccessAt':'2026-10-11T08:00:00+08:00','editionDate':'2026-10-11','lastAttemptAt':'2026-10-11T08:00:00+08:00'}
        source_status={'name':'Test','status':'ok'}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)), patch.object(r,'DATA',Path(folder)/'data'), patch.object(r,'read_previous',return_value=previous), \
             patch.object(r,'fetch_source',return_value=([self.row('new')],source_status)), patch.object(r,'write_digest') as written, patch.object(r,'RotatingFileHandler',lambda *args,**kwargs: r.logging.NullHandler()), \
             patch.object(r.serve,'read_current_config',return_value=self.config), \
             patch.object(r.serve,'call_model',side_effect=r.serve.ProviderError('连接 API 失败')), patch.object(r,'datetime') as clock:
            clock.now.return_value=self.now; clock.fromisoformat=datetime.fromisoformat
            self.assertEqual(r.refresh(),3)
            digest=written.call_args.args[0]
            self.assertEqual(digest['articles'],previous['articles'])
            self.assertEqual(digest['lastSuccessAt'],previous['lastSuccessAt'])
            self.assertEqual(digest['pendingReason'],'editor-unavailable')


class EvidenceAndReviewTests(unittest.TestCase):
    now = EditorTests.now
    config = EditorTests.config
    row = EditorTests.row
    def scores(self, rows, score=4):
        return {row['id']:{'score':score, 'category':row.get('category') or 'AI',
                           'evidence':'实测或观测', 'triageVersion':r.TRIAGE_VERSION} for row in rows}
    def review(self, rows, order, **kwargs):
        with patch.object(r.serve,'call_model',return_value=json.dumps({'order':order})):
            return r.final_review(self.config,rows,self.scores(rows),{},'2026-10-12',**kwargs)
    def test_evidence_caps_are_enforced_for_every_evidence_type(self):
        for evidence,cap in r.EVIDENCE_CAPS.items():
            with self.subTest(evidence=evidence), patch.object(r.serve,'call_model',return_value=reply([
                    {'n':'n1','score':5,'category':'AI','evidence':evidence}])):
                result=r.triage(self.config,[self.row('one')])['one']
                self.assertEqual(result['score'],cap)
                self.assertEqual(result['evidence'],evidence)
                self.assertEqual(result['triageVersion'],r.TRIAGE_VERSION)
    def test_unknown_missing_or_wrong_evidence_retries_once(self):
        good={'n':'n1','score':5,'category':'AI','evidence':'计算或模拟'}
        for bad in ['不存在',None,['计算或模拟']]:
            with self.subTest(evidence=bad), patch.object(r.serve,'call_model',side_effect=[
                    reply([{**good,'evidence':bad}]),reply([good])]) as model:
                self.assertEqual(r.triage(self.config,[self.row('one')])['one']['score'],4)
                self.assertEqual(model.call_count,2)
        for score in [True,4.0]:
            with self.subTest(score=score), patch.object(r.serve,'call_model',return_value=reply([{**good,'score':score}])) as model:
                self.assertEqual(r.triage(self.config,[self.row('one')]),{})
                self.assertEqual(model.call_count,2)
    def test_old_version_is_rescored_once_and_existing_edit_is_preserved(self):
        rows=[self.row('one')]
        notes={'brief':'已有的一句话。','why':'只是计算模拟，还未实际验证。'}
        cache={'triage':{'one':{'score':5,'category':'AI','triageVersion':1}},'edit':{'one':notes}}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'DATA',Path(folder)), \
             patch.object(r.serve,'read_current_config',return_value=self.config), \
             patch.object(r.serve,'call_model',side_effect=[reply([{'n':'n1','score':5,'category':'AI','evidence':'计算或模拟'}]),
                 json.dumps({'order':['n1']}),json.dumps({'order':['n1']})]) as model:
            target=Path(folder)/'editor-cache.json'
            target.write_text(json.dumps(cache),encoding='utf-8')
            result=r.edit_edition(rows,{},self.now)
            stored=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(stored['triage']['one']['score'],4)
            self.assertEqual(stored['triage']['one']['triageVersion'],r.TRIAGE_VERSION)
            self.assertEqual(stored['edit']['one'],notes)
            self.assertEqual(result[0]['evidence'],'计算或模拟')
            self.assertEqual(model.call_count,2)
            r.edit_edition(rows,{},self.now)
            self.assertEqual(model.call_count,3)  # Only final review repeats.
    def test_partial_rescore_never_selects_an_old_judgement(self):
        rows=[self.row('old'),self.row('new')]
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'DATA',Path(folder)), \
             patch.object(r.serve,'read_current_config',return_value=self.config), \
             patch.object(r,'triage',return_value=self.scores([rows[1]])), \
             patch.object(r.serve,'call_model',return_value=json.dumps({'order':['n1']})):
            target=Path(folder)/'editor-cache.json'
            target.write_text(json.dumps({'triage':{'old':{'score':5,'category':'AI'}},
                                         'edit':{'new':{'brief':'已有说明。','why':'研究数据。'}}}),encoding='utf-8')
            self.assertEqual([row['id'] for row in r.edit_edition(rows,{},self.now)],['new'])
    def test_review_order_wins_over_score_and_duplicate_unknown_keys_are_ignored(self):
        rows=[self.row('high',category='芯片'),self.row('middle',category='航天'),self.row('low',category='AI')]
        scores=self.scores(rows)
        scores['high']['score']=5; scores['low']['score']=3
        with patch.object(r.serve,'call_model',return_value=json.dumps({'order':['n3','n3','missing','n1','n2']})):
            chosen=r.final_review(self.config,rows,scores,{},'2026-10-12')
        self.assertEqual([row['id'] for row in chosen],['low','high','middle'])
        self.assertEqual([row['featured'] for row in chosen],[True,False,False])
    def test_review_skips_topic_and_source_overflow_and_supplements_by_score(self):
        rows=[self.row('a'+str(i),source='s'+str(i),category='AI',hours=i) for i in range(5)]
        rows += [self.row('b'+str(i),source='shared',category=r.TOPICS[i+1],hours=10+i) for i in range(6)]
        chosen=self.review(rows,['n'+str(i+1) for i in range(len(rows))],limit=12)
        self.assertEqual(len(chosen),9)
        self.assertNotIn('a4',[row['id'] for row in chosen])
        self.assertEqual(sum(row['source']=='shared' for row in chosen),5)
        sparse=self.review(rows,['n3'],limit=3)
        self.assertEqual([row['id'] for row in sparse],['a2','a0','a1'])
        empty=self.review(rows,[],limit=3)
        self.assertEqual([row['id'] for row in empty],['a0','a1','a2'])
    def test_review_keeps_both_region_minimums_and_can_fill_from_beyond_top_40(self):
        rows=[self.row('en'+str(i),'en','source'+str(i),category=r.TOPICS[i%10],hours=i) for i in range(41)]
        rows += [self.row('cn'+str(i),source='国内'+str(i),category=r.TOPICS[i+5],hours=50+i) for i in range(3)]
        with patch.object(r.serve,'call_model',return_value=json.dumps({'order':['n'+str(i) for i in range(1,16)]})) as model:
            chosen=r.final_review(self.config,rows,self.scores(rows),{},'2026-10-12')
            material=model.call_args.args[1].split('---候选---\n')[1].splitlines()
        self.assertEqual(len(material),40)
        self.assertEqual(len(chosen),15)
        self.assertEqual(sum(row['language']=='zh' for row in chosen),3)
        self.assertGreaterEqual(sum(row['language']=='en' for row in chosen),3)
        self.assertTrue(all('evidence' in json.loads(line) and 'region' in json.loads(line) for line in material))
    def test_region_minimum_recovers_when_initial_topic_choices_block_other_region(self):
        rows=[self.row('cn'+str(i),source='国内'+str(i),category='AI',hours=i) for i in range(3)]
        rows += [self.row('alt'+str(i),source='国内替代'+str(i),category='芯片',hours=3+i) for i in range(2)]
        rows += [self.row('en'+str(i),'en','海外'+str(i),category='AI',hours=5+i) for i in range(3)]
        chosen=self.review(rows,['n'+str(i) for i in range(1,9)],limit=6)
        self.assertEqual(len(chosen),6)
        self.assertEqual(sum(row['language']=='zh' for row in chosen),3)
        self.assertEqual(sum(row['language']=='en' for row in chosen),3)
        self.assertLessEqual(sum(row['category']=='AI' for row in chosen),4)
        impossible=self.review(rows[:3]+rows[5:],['n1','n2','n3'],limit=6)
        self.assertEqual(len(impossible),4)  # One topic cannot hold six quota rows.
    def test_review_respects_threshold_previous_days_and_small_limits(self):
        rows=[self.row('today',category='AI'),self.row('old',category='芯片'),self.row('low',category='航天')]
        scores=self.scores(rows); scores['low']['score']=3
        with patch.object(r.serve,'call_model',return_value=json.dumps({'order':['n1']})) as model:
            chosen=r.final_review(self.config,rows,scores,{'old':'2026-10-11'},'2026-10-12',limit=1,min_score=4)
            material=model.call_args.args[1].split('---候选---\n')[1]
        self.assertEqual([row['id'] for row in chosen],['today'])
        self.assertNotIn('标题old',material)
        self.assertNotIn('标题low',material)
    def test_review_invalid_formats_retry_once_then_warn_and_use_choose(self):
        rows=[self.row('one')]
        for answer in ['不是 JSON','{}','{"order":"n1"}','{"order":[1]}']:
            with self.subTest(answer=answer), patch.object(r.serve,'call_model',return_value=answer) as model, \
                 self.assertLogs(level='WARNING') as logs:
                chosen=r.final_review(self.config,rows,self.scores(rows),{},'2026-10-12')
                self.assertEqual([row['id'] for row in chosen],['one'])
                self.assertEqual(model.call_count,2)
                self.assertIn('falling back',logs.output[0])
        with patch.object(r.serve,'call_model',side_effect=['{}',json.dumps({'order':['n1']})]) as model:
            self.assertEqual(len(r.final_review(self.config,rows,self.scores(rows),{},'2026-10-12')),1)
            self.assertEqual(model.call_count,2)
    def test_review_empty_pool_makes_no_model_call(self):
        with patch.object(r.serve,'call_model') as model:
            self.assertEqual(r.final_review(self.config,[self.row('one')],{}, {},'2026-10-12'),[])
            model.assert_not_called()
    def test_review_connection_failure_keeps_previous_edition_and_cache(self):
        rows=[self.row('one')]
        previous={'articles':[self.row('kept')],'lastSuccessAt':'2026-10-11T08:00:00+08:00','editionDate':'2026-10-11'}
        cache={'triage':self.scores(rows),'edit':{'one':{'brief':'已有说明。','why':'研究数据。'}}}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'ROOT',Path(folder)), patch.object(r,'DATA',Path(folder)/'data'), \
             patch.object(r,'SOURCES',[{'name':'Test'}]), patch.object(r,'read_previous',return_value=previous), \
             patch.object(r,'fetch_source',return_value=(rows,{'name':'Test','status':'ok'})), patch.object(r,'write_digest') as written, \
             patch.object(r,'RotatingFileHandler',lambda *args,**kwargs:r.logging.NullHandler()), \
             patch.object(r.serve,'read_current_config',return_value=self.config), \
             patch.object(r.serve,'call_model',side_effect=r.serve.ProviderError('连接失败')) as model, \
             patch.object(r,'datetime') as clock, patch('builtins.print'):
            data=Path(folder)/'data'; data.mkdir()
            target=data/'editor-cache.json'; target.write_text(json.dumps(cache),encoding='utf-8')
            original=target.read_bytes()
            clock.now.return_value=self.now; clock.fromisoformat=datetime.fromisoformat
            with self.assertRaises(r.EditorUnavailable):
                r.final_review(self.config,rows,self.scores(rows),{},'2026-10-12')
            self.assertEqual(r.refresh(),3)
            self.assertEqual(model.call_count,2)  # One attempt per independently tested invocation.
            self.assertEqual(written.call_args.args[0]['articles'],previous['articles'])
            self.assertEqual(written.call_args.args[0]['lastSuccessAt'],previous['lastSuccessAt'])
            self.assertEqual(target.read_bytes(),original)

if __name__=='__main__':
    unittest.main()
