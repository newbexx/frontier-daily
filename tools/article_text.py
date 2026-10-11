"""Read public news pages without sending API credentials or executing page scripts."""
import gzip
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_BYTES = 2_000_000
MAX_TEXT = 10000

class ArticleInputError(ValueError):
    pass

class ArticleFetchError(RuntimeError):
    pass

class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

class PageParser(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID and len(self.stack) < 160:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID: self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

SKIP = {'script','style','noscript','svg','canvas','iframe','nav','footer','header','aside','form','button','select','head'}
BLOCK = {'p','div','article','main','section','h1','h2','h3','h4','li','blockquote','pre','br','tr'}
NOISE = re.compile(r'(?:^|[-_\s])(nav|footer|header|sidebar|share|social|comment|comments|related|recommend|advert|ads|cookie|newsletter|menu)(?:$|[-_\s])', re.I)
CONTENT = re.compile(r'(story[-_]?(text|body|content)|article[-_]?(body|content|text)|entry[-_]?(content|body)|post[-_]?(content|body)|content[-_]?(body|article)|rich_media_content|editor-content)', re.I)

def walk(node):
    yield node
    for child in node.children:
        if isinstance(child, Node): yield from walk(child)

def raw_text(node):
    return ''.join(child if isinstance(child,str) else raw_text(child) for child in node.children)

def visible_text(node):
    identity = (node.attrs.get('id') or '')+' '+(node.attrs.get('class') or '')
    if node.tag in SKIP or NOISE.search(identity) or 'hidden' in node.attrs or node.attrs.get('aria-hidden') == 'true': return ''
    text = ''.join(child if isinstance(child,str) else visible_text(child) for child in node.children)
    return '\n'+text+'\n' if node.tag in BLOCK else text

def clean_text(text):
    return '\n\n'.join(line for line in (re.sub(r'\s+',' ',line).strip() for line in text.splitlines()) if line)

def json_articles(value):
    if isinstance(value,dict):
        if isinstance(value.get('articleBody'),str): yield value
        for child in value.values():
            if isinstance(child,(dict,list)): yield from json_articles(child)
    elif isinstance(value,list):
        for child in value: yield from json_articles(child)

def extract_html(html):
    parser=PageParser()
    parser.feed(html)
    nodes=list(walk(parser.root))
    title=next((clean_text(raw_text(n)) for n in nodes if n.tag=='h1' and clean_text(raw_text(n))), '')
    if not title: title=next((clean_text(raw_text(n)) for n in nodes if n.tag=='title'), '')
    for node in nodes:
        if node.tag=='script' and (node.attrs.get('type') or '').lower()=='application/ld+json':
            try:
                for item in json_articles(json.loads(raw_text(node))):
                    body=clean_text(item['articleBody'])
                    if len(body)>=120:
                        return body, str(item.get('headline') or title)[:500]
            except (ValueError,RecursionError): pass
    candidates=[]
    for node in nodes:
        identity=(node.attrs.get('id') or '')+' '+(node.attrs.get('class') or '')
        marked=bool(CONTENT.search(identity)) or node.attrs.get('itemprop')=='articleBody'
        if marked or node.tag in ('article','main'):
            text=clean_text(visible_text(node))
            if len(text)>=120:
                score=(160 if marked else 70)+min(len(text),12000)/150+min(text.count('\n\n'),30)
                candidates.append((score,text))
    if candidates: return max(candidates,key=lambda item:item[0])[1], title[:500]
    paragraphs=[clean_text(visible_text(n)) for n in nodes if n.tag=='p']
    paragraphs=[text for text in paragraphs if len(text)>=45]
    if len(paragraphs)>=3: return '\n\n'.join(paragraphs), title[:500]
    raise ArticleFetchError('未能从网页提取新闻正文。页面可能需要登录或依赖脚本，请复制正文粘贴到下方。')

def public_target(url):
    if not isinstance(url,str) or len(url)>4096 or re.search(r'[\x00-\x20\x7f]',url):
        raise ArticleInputError('请填写完整的公开新闻网址。')
    try:
        parts=urlsplit(url)
        port=parts.port
        if parts.scheme not in ('http','https') or not parts.hostname or parts.username is not None or parts.password is not None or port not in (None,80 if parts.scheme=='http' else 443):
            raise ValueError()
        host=parts.hostname.encode('idna').decode('ascii')
        port=port or (443 if parts.scheme=='https' else 80)
    except (ValueError,UnicodeError):
        raise ArticleInputError('只支持公开的 HTTP 或 HTTPS 新闻网址。') from None
    try: addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    except OSError: raise ArticleFetchError('无法解析新闻网址，请检查链接是否正确。') from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ArticleInputError('请使用公开新闻网址，不能读取本机或内网地址。')
    netloc=('['+host+']') if ':' in host else host
    target=quote(parts.path or '/',safe="/%:@!$&'()*+,;=-._~")
    if parts.query: target+='?'+quote(parts.query,safe="%/:?@!$&'()*+,;=-._~")
    return parts.scheme,host,port,addresses[0][4][0],target,urlunsplit((parts.scheme,netloc,parts.path or '/',parts.query,''))

def fetch_page(url):
    deadline=time.monotonic()+25
    for hop in range(5):
        scheme,host,port,address,target,normalized=public_target(url)
        timeout=max(1,min(12,deadline-time.monotonic()))
        connection=(http.client.HTTPSConnection(host,port,timeout=timeout,context=ssl.create_default_context()) if scheme=='https' else http.client.HTTPConnection(host,port,timeout=timeout))
        # Pin the validated public IP, while HTTPS still verifies the original hostname.
        connection._create_connection=lambda _target,timeout=timeout,source_address=None: socket.create_connection((address,port),timeout,source_address)
        try:
            connection.request('GET',target,headers={'User-Agent':'FrontierDaily/1.0','Accept':'text/html,application/xhtml+xml,text/plain;q=0.8','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                destination=response.getheader('Location')
                if not destination or hop==4: raise ArticleFetchError('网页重定向过多或链接无效，请手动粘贴正文。')
                url=urljoin(normalized,destination)
                continue
            if response.status!=200:
                raise ArticleFetchError('网站暂时不允许读取（HTTP '+str(response.status)+'）。可打开原文，复制正文粘贴到下方。')
            media=response.headers.get_content_type()
            if media not in ('text/html','application/xhtml+xml','text/plain'):
                raise ArticleFetchError('这个链接不是可读取的新闻网页，请粘贴文章网页地址或正文。')
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES: raise ArticleFetchError('网页内容过大，请手动粘贴需要解读的正文片段。')
            encoding=response.getheader('Content-Encoding','identity').lower()
            if encoding=='gzip':
                with gzip.GzipFile(fileobj=BytesIO(raw)) as compressed: raw=compressed.read(MAX_BYTES+1)
            elif encoding!='identity': raise ArticleFetchError('网页使用了暂不支持的压缩方式，请手动粘贴正文。')
            if len(raw)>MAX_BYTES: raise ArticleFetchError('网页内容过大，请手动粘贴需要解读的正文片段。')
            charset=response.headers.get_content_charset()
            if not charset:
                match=re.search(br'<meta\b[^>]*charset\s*=\s*["\']?([a-zA-Z0-9_-]+)',raw[:12000],re.I)
                charset=match.group(1).decode('ascii') if match else 'utf-8'
            if charset.lower() in ('gb2312','gbk'): charset='gb18030'
            try: text=raw.decode(charset)
            except (UnicodeError,LookupError): text=raw.decode('utf-8',errors='replace')
            return text,normalized,media
        except ArticleFetchError: raise
        except (OSError,http.client.HTTPException,EOFError):
            raise ArticleFetchError('读取网页失败或超时。可重试，或打开原文复制正文粘贴到下方。') from None
        finally: connection.close()
    raise ArticleFetchError('无法读取原文，请手动粘贴正文。')

def fetch_article(payload):
    url=payload.get('url')
    html,final_url,media=fetch_page(url)
    if media=='text/plain': text,title=clean_text(html),''
    else: text,title=extract_html(html)
    if len(text)<120: raise ArticleFetchError('网页可提取的正文太少，请手动粘贴完整正文。')
    return {'text':text[:MAX_TEXT],'title':title,'url':final_url,'characters':min(len(text),MAX_TEXT),'truncated':len(text)>MAX_TEXT}
