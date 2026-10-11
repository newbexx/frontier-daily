import importlib.util
import json
import socket
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('article_text',Path(__file__).resolve().parents[1]/'tools'/'article_text.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
PUBLIC=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
BODY='这是实验的正文，介绍实验方法、对照条件、观察结果和仍然存在的局限。'*10

class FakeResponse:
    def __init__(self,status=200,body=b'',location=None,media='text/html; charset=utf-8'):
        self.status,self.body=status,body
        self.headers=Message();self.headers['Content-Type']=media
        if location: self.headers['Location']=location
    def getheader(self,name,default=None): return self.headers.get(name,default)
    def read(self,limit): return self.body[:limit]

class ArticleTests(unittest.TestCase):
    def test_extracts_article_body_ignoring_scripts_navigation_and_related_content(self):
        text,title=a.extract_html('<html><head><title>网页标题</title></head><body><nav>导航</nav><h1>实验新闻</h1><div class="post_content"><p>'+BODY+'</p><script>秘密脚本</script><div class="related">推荐文章</div></div><footer>页脚</footer></body></html>')
        self.assertEqual(title,'实验新闻');self.assertEqual(text,BODY)
    def test_english_paragraphs_preserve_inline_spaces_and_subheads(self):
        sentence='Researchers created a <strong>new quantum state</strong> and measured its behavior. '
        text,title=a.extract_html('<article><h1>Quantum study</h1><p>'+sentence*5+'</p><h2>Limitations</h2><p>More work is needed.</p></article>')
        self.assertIn('a new quantum state and',text);self.assertIn('Limitations',text)
    def test_jsonld_graph_and_html_entities(self):
        value={'@graph':[{'@type':'NewsArticle','headline':'新闻标题','articleBody':BODY}]}
        text,title=a.extract_html('<script type="application/ld+json">'+json.dumps(value)+'</script><nav>导航</nav>')
        self.assertEqual(text,BODY);self.assertEqual(title,'新闻标题')
        text,_=a.extract_html('<article><p>'+BODY+'&amp; X &lt; Y</p></article>')
        self.assertIn('& X < Y',text)
    def test_short_login_page_is_not_claimed_as_article(self):
        with self.assertRaises(a.ArticleFetchError):a.extract_html('<h1>登录</h1><p>请先登录查看全文</p>')
    def test_invalid_urls_do_not_resolve_or_fetch(self):
        for url in [None,'','file:///C:/secret','http://user:pass@example.com','https://example.com:8888','https://example.com\r\nSecret: x']:
            with self.subTest(url=url),patch.object(a.socket,'getaddrinfo') as dns,self.assertRaises(a.ArticleInputError):a.public_target(url)
            dns.assert_not_called()
    def test_private_loopback_linklocal_and_mixed_dns_are_blocked(self):
        for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1']:
            rows=[(2,1,6,'',(ip,443))]
            with self.subTest(ip=ip),patch.object(a.socket,'getaddrinfo',return_value=rows),self.assertRaises(a.ArticleInputError):a.public_target('https://example.com')
        with patch.object(a.socket,'getaddrinfo',return_value=PUBLIC+[(2,1,6,'',('10.0.0.1',443))]),self.assertRaises(a.ArticleInputError):a.public_target('https://example.com')
    def test_https_connection_pins_public_ip_and_keeps_hostname(self):
        response=FakeResponse(body=('<article><p>'+BODY+'</p></article>').encode())
        with patch.object(a.socket,'getaddrinfo',return_value=PUBLIC),patch.object(a.http.client,'HTTPSConnection') as connection,patch.object(a.socket,'create_connection') as connect:
            instance=connection.return_value;instance.getresponse.return_value=response
            text,url,media=a.fetch_page('https://example.com/news#section')
            self.assertEqual(connection.call_args.args[:2],('example.com',443))
            instance._create_connection(('evil.example',443),4,None)
            self.assertEqual(connect.call_args.args[0],('93.184.216.34',443))
            self.assertEqual(url,'https://example.com/news');self.assertEqual(media,'text/html')
            self.assertNotIn('Authorization',instance.request.call_args.kwargs['headers'])
    def test_redirect_to_private_address_blocked_before_second_connection(self):
        rows=[PUBLIC,[(2,1,6,'',('127.0.0.1',443))]]
        with patch.object(a.socket,'getaddrinfo',side_effect=rows),patch.object(a.http.client,'HTTPSConnection') as connection,self.assertRaises(a.ArticleInputError):
            connection.return_value.getresponse.return_value=FakeResponse(status=302,location='https://localhost/private')
            a.fetch_page('https://example.com')
        self.assertEqual(connection.call_count,1)
    def test_non_html_and_oversized_pages_are_rejected(self):
        for response in [FakeResponse(media='application/pdf'),FakeResponse(body=b'x'*(a.MAX_BYTES+1))]:
            with patch.object(a.socket,'getaddrinfo',return_value=PUBLIC),patch.object(a.http.client,'HTTPSConnection') as connection,self.assertRaises(a.ArticleFetchError):
                connection.return_value.getresponse.return_value=response;a.fetch_page('https://example.com')
    def test_long_article_is_limited_and_records_provenance(self):
        with patch.object(a,'fetch_page',return_value=('<article><h1>长文</h1><p>'+BODY*50+'</p></article>','https://example.com/final','text/html')):
            result=a.fetch_article({'url':'https://example.com/start'})
        self.assertEqual(len(result['text']),10000);self.assertTrue(result['truncated'])
        self.assertEqual(result['url'],'https://example.com/final');self.assertEqual(result['title'],'长文')

if __name__=='__main__':unittest.main()
