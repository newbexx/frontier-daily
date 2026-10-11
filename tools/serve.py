"""Local digest server and explicit, on-demand AI reading proxy."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import json
import re
import os
import socket
import ipaddress
import subprocess
import threading
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit, parse_qs, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

# Keep importable both as a script and in the existing unittest loader.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_text import fetch_article, ArticleInputError, ArticleFetchError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home()/'.codex'/'config.toml'
# Project connection settings; credentials remain in environment variables.
SETTINGS = ROOT/'ai-settings.json'
SLOTS = threading.BoundedSemaphore(2)
REFRESH = {'process': None}
REFRESH_LOCK = threading.Lock()

class InputError(ValueError):
    pass

class ProviderError(RuntimeError):
    pass

def reader_model(path=None):
    try:
        model = json.loads(Path(path or SETTINGS).read_text(encoding='utf-8-sig')).get('model', '')
    except (OSError, ValueError, AttributeError):
        return ''
    return model.strip() if isinstance(model, str) and 0 < len(model.strip()) <= 120 else ''

def validate_connection(endpoint, model, key, wire):
    endpoint = str(endpoint).strip().rstrip('/')
    model = str(model).strip()
    key = str(key).strip()
    wire = str(wire).strip()
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise InputError('API 地址格式无效，请检查 ai-settings.json 的 endpoint。') from None
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise InputError('API 地址格式无效，请填写不含密钥、查询参数和账号的服务地址。')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise InputError('非本机 API 必须使用 HTTPS。')
    if wire not in ('responses', 'chat'):
        raise InputError('wireApi 必须是 chat 或 responses，请按服务商接口填写。')
    if not model or len(model) > 120 or '\n' in model or '\r' in model:
        raise InputError('请在 ai-settings.json 或 FRONTIER_MODEL 中填写有效的模型 ID。')
    if not key or len(key) > 4096 or '\n' in key or '\r' in key:
        raise InputError('API Key 为空或格式无效，请设置密钥环境变量。')
    return {'endpoint': endpoint, 'model': model, 'key': key, 'wire': wire}


def read_current_config(path=None, settings=None):
    """Project/env setup takes priority; legacy Codex setup remains optional."""
    try:
        project = json.loads(Path(settings or SETTINGS).read_text(encoding='utf-8-sig'))
        if not isinstance(project, dict): project = {}
    except (OSError, ValueError):
        project = {}
    endpoint = os.environ.get('FRONTIER_API_BASE', project.get('endpoint', ''))
    explicit = 'endpoint' in project or bool(os.environ.get('FRONTIER_API_BASE')) or 'wireApi' in project or 'apiKeyEnv' in project
    if explicit:
        key_env = project.get('apiKeyEnv', 'FRONTIER_API_KEY')
        if not isinstance(key_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', key_env):
            raise InputError('apiKeyEnv 必须是有效的环境变量名称。')
        key = os.environ.get(key_env, '')
        if not key:
            raise InputError('未设置 ' + key_env + '；请按 AI 接入指南设置密钥，再启动本机服务。')
        model = os.environ.get('FRONTIER_MODEL', project.get('model', ''))
        wire = os.environ.get('FRONTIER_WIRE_API', project.get('wireApi', 'chat'))
        return validate_connection(endpoint, model, key, wire)
    try:
        source = Path(path or CONFIG).read_text(encoding='utf-8-sig')
    except OSError:
        raise InputError('尚未配置 AI。请复制 ai-settings.example.json 为 ai-settings.json，并按 AI 接入指南设置密钥；无需安装 Codex。') from None
    sections = {'': {}}
    section = ''
    for line in source.splitlines():
        header = re.match(r'^\s*\[([^\[\]]+)\]\s*$', line)
        if header:
            section = header.group(1)
            sections.setdefault(section, {})
            continue
        pair = re.match(r'^\s*([\w-]+)\s*=\s*("(?:[^"\\]|\\.)*")\s*(?:#.*)?$', line)
        if pair:
            sections[section][pair.group(1)] = json.loads(pair.group(2))
    root = sections['']
    provider = sections.get('model_providers.' + root.get('model_provider', ''), {})
    model = os.environ.get('FRONTIER_MODEL') or reader_model(settings) or root.get('model', '')
    key = provider.get('experimental_bearer_token') or os.environ.get(provider.get('env_key', ''))
    if not key:
        raise InputError('当前 Codex 配置没有可用的 API Key。可按 AI 接入指南使用独立 API 配置。')
    return validate_connection(provider.get('base_url', ''), model, key, provider.get('wire_api', 'responses'))

def validate_custom(payload):
    endpoint = str(payload.get('endpoint', '')).strip().rstrip('/')
    model = str(payload.get('model','')).strip()
    key = str(payload.get('apiKey','')).strip()
    parts = urlsplit(endpoint)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.port not in (None,443):
        raise InputError('其他 API 请使用公开的 HTTPS 服务地址（443 端口）。')
    if not model or len(model)>120 or not key or len(key)>4096 or '\n' in key or '\r' in key:
        raise InputError('请检查模型名称和 API Key。')
    try:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise InputError('其他 API 地址必须指向公开互联网服务。')
    except socket.gaierror:
        raise InputError('无法解析 API 服务地址。') from None
    return {'endpoint': endpoint, 'model': model, 'key': key, 'wire': 'chat'}

def start_refresh():
    """Run the collector in the background; refresh.py skips work when already up to date."""
    with REFRESH_LOCK:
        process = REFRESH['process']
        if not process or process.poll() is not None:
            REFRESH['process'] = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT/'tools'/'refresh.py'), '--if-due'], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return refresh_status()

def refresh_status():
    process = REFRESH['process']
    code = process.poll() if process else None
    return {'running': bool(process) and code is None, 'exitCode': code}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def extract_answer(data, wire):
    if wire == 'responses':
        output = data.get('output', [])
        text = '\n'.join(part.get('text','') for item in output if isinstance(item,dict) and item.get('type')=='message' for part in item.get('content',[]) if isinstance(part,dict) and part.get('type')=='output_text' and isinstance(part.get('text'),str))
        if not text and isinstance(data.get('output_text'),str):
            text = data['output_text']
    else:
        try:
            text = data['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError):
            text = ''
    if not isinstance(text,str) or not text.strip():
        raise ProviderError('API 没有返回可显示的文字，请检查模型及接口类型。')
    if data.get('status') == 'incomplete':
        text += '\n\n（本次回答达到生成上限，可缩小问题后继续追问。）'
    return text.strip()

def explain(payload):
    prompt = payload.get('prompt')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>26000:
        raise InputError('新闻材料为空或过长，请缩短补充正文。')
    if payload.get('mode','current') not in ('current','custom'):
        raise InputError('不支持的 API 模式。')
    config = read_current_config() if payload.get('mode','current')=='current' else validate_custom(payload)
    return {'answer':call_model(config,prompt), 'model':config['model']}

def call_model(config, prompt, max_tokens=3500):
    """One non-streaming request; also used by the daily editor in refresh.py."""
    wire = config['wire']
    if wire == 'responses':
        suffix = '/responses'
        body = {'model':config['model'], 'input':prompt, 'stream':False, 'max_output_tokens':max_tokens, 'store':False}
    else:
        suffix = '/chat/completions'
        body = {'model':config['model'], 'messages':[{'role':'user','content':prompt}], 'stream':False, 'max_tokens':max_tokens}
    endpoint = config['endpoint']
    if not endpoint.endswith(suffix): endpoint += suffix
    request = Request(endpoint, data=json.dumps(body,ensure_ascii=False).encode('utf-8'), headers={'Content-Type':'application/json','Authorization':'Bearer '+config['key'], 'User-Agent':'FrontierDaily/1.0'}, method='POST')
    try:
        with build_opener(NoRedirect).open(request, timeout=150) as response:
            raw = response.read(2_000_001)
        if len(raw)>2_000_000: raise ProviderError('API 返回内容过大，请缩短问题。')
        data = json.loads(raw)
        if not isinstance(data,dict): raise ProviderError('API 返回格式不受支持。')
        return extract_answer(data,wire)
    except HTTPError as error:
        messages = {400:'API 参数不被接受，请核对模型 ID、wireApi 协议及服务商支持的参数。',401:'API 身份验证失败，请检查当前转发服务或密钥。',403:'API 拒绝调用，请检查模型权限。',429:'API 调用过于频繁或余额不足，请稍后重试或检查账户。',404:'API 路径或模型不存在，请核对服务配置。'}
        raise ProviderError(messages.get(error.code,'API 服务暂时不可用（HTTP '+str(error.code)+'），请稍后重试。')) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError('连接 API 失败或超时，请检查服务地址、网络与代理设置，再重试。') from None
    except (json.JSONDecodeError,UnicodeDecodeError,TypeError,AttributeError):
        raise ProviderError('API 返回格式不受支持，请检查接口设置。') from None

# Learning records contain only an explicit allowlist, never API connection settings.
NOTES_LIMIT = 200 * 1024
NOTES_LOCK = threading.Lock()
ARTICLE_FIELDS = ('id', 'title', 'titleZh', 'source', 'date', 'publishedAt', 'url',
                  'category', 'brief', 'why', 'summary', 'summaryZh', 'language', 'evidence')

def note_path(article_id):
    if not isinstance(article_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', article_id):
        raise InputError('新闻编号无效。')
    if article_id.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        raise InputError('新闻编号无效。')
    folder = ROOT/'data'/'notes'
    path = folder/(article_id+'.json')
    if folder.resolve() != ROOT.resolve()/'data'/'notes' or path.is_symlink():
        raise InputError('记录路径无效。')
    return path

def note_text(value, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise InputError('记录格式错误或内容过长。')
    return value

def note_time(value):
    value = note_text(value, 40)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise InputError('记录时间须包含时区。')
    return parsed.astimezone(timezone.utc).isoformat()

def clean_conversation(payload):
    article = payload.get('article')
    if not isinstance(article, dict): raise InputError('缺少新闻信息。')
    note_path(article.get('id'))
    article = {key: note_text(article[key], 12000 if key in ('summary', 'summaryZh') else 3000)
               for key in ARTICLE_FIELDS if key in article}
    messages = payload.get('messages')
    if not isinstance(messages, list) or len(messages) > 1000: raise InputError('消息格式错误。')
    cleaned = []
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('user', 'assistant'):
            raise InputError('消息角色无效。')
        content = note_text(message.get('content'), 100000)
        if not content.strip(): raise InputError('消息内容为空。')
        cleaned.append({'role': message['role'], 'content': content,
                        'model': note_text(message.get('model', ''), 120), 'time': note_time(message.get('time'))})
    source = payload.get('bodySource')
    if source is not None:
        if not isinstance(source, dict): raise InputError('正文出处无效。')
        source = {'url': note_text(source.get('url', ''), 3000), 'title': note_text(source.get('title', ''), 3000),
                  'truncated': source.get('truncated') is True}
    asked = [m['time'] for m in cleaned if m['role'] == 'user']
    return {'version': 1, 'article': article, 'messages': cleaned,
            'body': note_text(payload.get('body', ''), 10000),
            'url': note_text(payload.get('url', ''), 3000), 'bodySource': source,
            'lastAskedAt': max(asked, default='')}

def read_note(article_id):
    path = note_path(article_id)
    if not path.exists(): return None
    if path.stat().st_size > NOTES_LIMIT: raise InputError('记录超过大小上限。')
    value = json.loads(path.read_text(encoding='utf-8'))
    record = clean_conversation(value)
    if record['article']['id'] != article_id: raise InputError('记录编号不一致。')
    record['notes'] = []
    for note in value.get('notes', []):
        if not isinstance(note, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(note.get('id', ''))):
            raise InputError('笔记格式错误。')
        record['notes'].append({'id': note['id'], 'content': note_text(note.get('content'), 100000),
                                'time': note_time(note.get('time'))})
    return record

def write_note(record):
    path = note_path(record['article']['id'])
    raw = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > NOTES_LIMIT: raise InputError('这篇记录超过 200KB，请复制备份后再整理。')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists(): temporary.unlink()

def save_conversation(payload):
    record = clean_conversation(payload)
    with NOTES_LOCK:
        previous = read_note(record['article']['id'])
        record['notes'] = previous['notes'] if previous else []
        write_note(record)
    return {'saved': True}

def update_note(payload):
    article_id = payload.get('articleId')
    with NOTES_LOCK:
        record = read_note(article_id)
        if record is None: raise InputError('请先保存这篇对话，再收进笔记。')
        if payload.get('action') == 'add':
            content = note_text(payload.get('content'), 100000).strip()
            if not content: raise InputError('笔记不能为空。')
            record['notes'].append({'id': uuid4().hex, 'content': content,
                                    'time': datetime.now(timezone.utc).isoformat()})
        elif payload.get('action') == 'delete':
            record['notes'] = [note for note in record['notes'] if note['id'] != payload.get('noteId')]
        else: raise InputError('笔记操作无效。')
        write_note(record)
    return {'notes': record['notes']}

def list_notes():
    records, unreadable = [], 0
    folder = ROOT/'data'/'notes'
    if folder.resolve() != ROOT.resolve()/'data'/'notes': raise InputError('记录路径无效。')
    with NOTES_LOCK:
        for path in folder.glob('*.json'):
            try:
                record = read_note(path.stem)
                if record and any(m['role'] == 'user' for m in record['messages']): records.append(record)
            except (OSError, ValueError, TypeError): unreadable += 1
    records.sort(key=lambda row: row['lastAskedAt'], reverse=True)
    return {'records': records, 'unreadable': unreadable}

class Handler(SimpleHTTPRequestHandler):
    def allowed(self):
        port = self.server.server_address[1]
        hosts = (f'127.0.0.1:{port}', f'localhost:{port}')
        if self.headers.get('Host') not in hosts: return False
        origin = self.headers.get('Origin')
        return origin is None or origin == 'null' or origin in ('http://'+host for host in hosts)
    def reply(self, status, data):
        raw = json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        origin = self.headers.get('Origin')
        if origin and self.allowed():
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
    def do_OPTIONS(self):
        if self.path not in ('/api/explain','/api/article','/api/notes','/api/note') or not self.allowed(): self.reply(403,{'error':'请求来源不允许。'}); return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin','null'))
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Vary','Origin')
        self.end_headers()
    def do_GET(self):
        if not self.allowed(): self.reply(403,{'error':'请求来源不允许。'}); return
        parsed = urlsplit(self.path)
        if parsed.path == '/api/notes':
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if 'id' in query:
                    with NOTES_LOCK: record = read_note(query['id'][0])
                    self.reply(200, {'record': record})
                else: self.reply(200, list_notes())
            except (InputError, ValueError, TypeError): self.reply(400, {'error': '学习记录格式或编号无效。'})
            except OSError: self.reply(500, {'error': '读取学习记录失败，请检查本机文件。'})
            return
        # Keep private learning data behind the checked JSON interface.
        static_path = (ROOT/unquote(parsed.path).lstrip('/')).resolve()
        if not static_path.is_relative_to(ROOT.resolve()):
            self.reply(403, {'error': '请求路径不允许。'}); return
        relative = static_path.relative_to(ROOT.resolve())
        private = any(part.startswith('.') for part in relative.parts) or (relative.parts and relative.parts[0].casefold() == 'logs') or relative.name.casefold() == 'ai-settings.json'
        if private:
            self.reply(403, {'error': '本机配置和内部文件不提供网页访问。'}); return
        if static_path.is_relative_to((ROOT/'data'/'notes').resolve()):
            self.reply(403, {'error': '请通过学习记录接口读取。'}); return
        if self.path == '/api/health':
            try:
                config = read_current_config()
                self.reply(200,{'service':'frontier-personal','version':5,'features':['explain','article','refresh','notes'],'currentAvailable':True,'model':config['model']})
            except (InputError,OSError,ValueError):
                self.reply(200,{'service':'frontier-personal','version':5,'features':['explain','article','refresh','notes'],'currentAvailable':False})
            return
        if self.path == '/api/refresh': self.reply(200,refresh_status()); return
        if self.path.startswith('/api/'): self.reply(404,{'error':'接口不存在。'}); return
        super().do_GET()
    def do_POST(self):
        if not self.allowed(): self.reply(403,{'error':'请求来源不允许。'}); return
        # A body-less POST needs no CORS preflight, so the desktop file:// page can trigger it.
        if self.path == '/api/refresh': self.reply(200,start_refresh()); return
        if self.path not in ('/api/explain','/api/article','/api/notes','/api/note'): self.reply(404,{'error':'接口不存在。'}); return
        if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json': self.reply(415,{'error':'仅接受 JSON 请求。'}); return
        try:
            length = int(self.headers.get('Content-Length','0'))
            maximum = NOTES_LIMIT if self.path in ('/api/notes','/api/note') else 120000
            if length > maximum: self.reply(413, {'error': '请求超过大小上限。'}); return
            if length <= 0: raise InputError('请求为空。')
            self.connection.settimeout(15)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise InputError('请求格式错误。')
        except (ValueError,UnicodeDecodeError,TimeoutError): self.reply(400,{'error':'请求格式错误或内容过长。'}); return
        if self.path in ('/api/notes', '/api/note'):
            try: self.reply(200, save_conversation(payload) if self.path == '/api/notes' else update_note(payload))
            except InputError as error: self.reply(400, {'error': str(error)})
            except (ValueError, TypeError): self.reply(400, {'error': '记录格式无效，请复制备份后重试。'})
            except OSError: self.reply(500, {'error': '保存学习记录失败，请检查本机目录是否可写。'})
            return
        if not SLOTS.acquire(blocking=False): self.reply(429,{'error':'已有任务正在处理，请稍后重试。'}); return
        try: self.reply(200,fetch_article(payload) if self.path == '/api/article' else explain(payload))
        except ArticleInputError as error: self.reply(400,{'error':str(error)})
        except ArticleFetchError as error: self.reply(502,{'error':str(error)})
        except (InputError,ValueError): self.reply(400,{'error':'请求或 API 配置无效，请检查地址、模型、密钥与正文长度。'})
        except ProviderError as error: self.reply(502,{'error':str(error)})
        except Exception: self.reply(500,{'error':'本机解读服务暂时不可用，请重试。'})
        finally: SLOTS.release()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8768)
    args = parser.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    with (ROOT/'logs'/'server.log').open('a',encoding='utf-8',buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        with ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT))) as server:
            try: server.serve_forever()
            except KeyboardInterrupt: pass
