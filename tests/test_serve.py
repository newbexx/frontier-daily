import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO
from functools import partial
from http.client import HTTPConnection
import threading

spec=importlib.util.spec_from_file_location('serve',Path(__file__).resolve().parents[1]/'tools'/'serve.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class ServeTests(unittest.TestCase):
    def test_selected_provider_only_and_credentials_remain_server_side(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.toml'
            p.write_text('model_provider="active"\nmodel="test-model"\n[model_providers.other]\nbase_url="https://unused.example"\nexperimental_bearer_token="wrong"\n[model_providers.active]\nbase_url="http://127.0.0.1:1234/v1"\nwire_api="responses"\nexperimental_bearer_token="test-secret"\n',encoding='utf-8')
            config=s.read_current_config(p)
            self.assertEqual(config['key'],'test-secret')
            self.assertEqual(config['endpoint'],'http://127.0.0.1:1234/v1')
    def test_project_setting_overrides_only_the_reader_model(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.toml'; settings=Path(directory)/'ai-settings.json'
            p.write_text('model_provider="active"\nmodel="codex-model"\n[model_providers.active]\nbase_url="http://127.0.0.1:1234/v1"\nexperimental_bearer_token="k"\n',encoding='utf-8')
            settings.write_text('{"model":"reader-model"}',encoding='utf-8')
            self.assertEqual(s.read_current_config(p,settings)['model'],'reader-model')
            settings.write_text('not json',encoding='utf-8')
            self.assertEqual(s.read_current_config(p,settings)['model'],'codex-model')
    def test_current_call_preserves_responses_protocol_and_client_identity(self):
        response=BytesIO(json.dumps({'output':[{'type':'message','content':[{'type':'output_text','text':'中文解读'}]}]}).encode())
        config={'endpoint':'http://127.0.0.1:1234/v1','model':'test-model','key':'test-secret','wire':'responses'}
        with patch.object(s,'read_current_config',return_value=config), patch.object(s,'build_opener') as opener:
            opener.return_value.open.return_value=response
            result=s.explain({'mode':'current','prompt':'请解读'})
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:1234/v1/responses')
            self.assertEqual(request.get_header('User-agent'),'FrontierDaily/1.0')
            self.assertFalse(json.loads(request.data)['store'])
            self.assertEqual(result,{'answer':'中文解读','model':'test-model'})
            self.assertNotIn('test-secret',json.dumps(result))
    def test_extraction_ignores_reasoning_and_supports_chat(self):
        self.assertEqual(s.extract_answer({'output':[{'type':'reasoning','summary':[]},{'type':'message','content':[{'type':'output_text','text':'answer'}]}]},'responses'),'answer')
        self.assertEqual(s.extract_answer({'choices':[{'message':{'content':'answer'}}]},'chat'),'answer')
        with self.assertRaises(s.ProviderError): s.extract_answer({'output':[]},'responses')
    def test_untrusted_custom_endpoints_rejected(self):
        for url in ['http://example.com','https://user:pass@example.com','https://example.com?key=secret','https://example.com:444']:
            with self.subTest(url=url),self.assertRaises(s.InputError): s.validate_custom({'endpoint':url,'model':'m','apiKey':'k'})
        with patch.object(s.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),self.assertRaises(s.InputError):
            s.validate_custom({'endpoint':'https://example.com','model':'m','apiKey':'k'})
    def test_invalid_prompt_cannot_call_api(self):
        for prompt in ['',None,'a'*26001]:
            with patch.object(s,'read_current_config') as config,self.assertRaises(s.InputError): s.explain({'prompt':prompt})
            config.assert_not_called()
    def test_request_origin_and_host_rules(self):
        handler=object.__new__(s.Handler)
        handler.server=type('Server',(),{'server_address':('127.0.0.1',8768)})()
        for origin in ['http://127.0.0.1:8768','http://localhost:8768','null',None]:
            handler.headers={'Host':'127.0.0.1:8768','Origin':origin}
            self.assertTrue(handler.allowed())
        handler.headers={'Host':'127.0.0.1:8768','Origin':'https://unrelated.example'}; self.assertFalse(handler.allowed())
        handler.headers={'Host':'unrelated.example:8768'}; self.assertFalse(handler.allowed())
    def test_refresh_runs_once_in_the_background(self):
        with patch.object(s.subprocess,'Popen') as popen, patch.dict(s.REFRESH,{'process':None}):
            popen.return_value.poll.return_value=None
            self.assertEqual(s.start_refresh(),{'running':True,'exitCode':None})
            s.start_refresh()
            self.assertEqual(popen.call_count,1)
            self.assertIn('--if-due',popen.call_args.args[0])
            popen.return_value.poll.return_value=3
            self.assertEqual(s.refresh_status(),{'running':False,'exitCode':3})

class NotesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(s, 'ROOT', self.root); self.root_patch.start()
        self.log_patch = patch.object(s.Handler, 'log_message'); self.log_patch.start()
        self.api_patch = patch.object(s, 'explain', side_effect=AssertionError('Tests must never call the API')); self.api_patch.start()
        self.server = s.ThreadingHTTPServer(('127.0.0.1', 0), partial(s.Handler, directory=str(self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.port = self.server.server_address[1]
        self.payload = {'article': {'id': 'article_1', 'title': 'Battery research', 'titleZh': '电池研究',
                                   'category': '新能源', 'source': '研究机构', 'brief': '一项实验',
                                   'url': 'https://example.com/story', 'apiKey': 'must-not-save'},
                        'messages': [{'role': 'user', 'content': '为什么老化？', 'model': '', 'time': '2026-10-11T02:00:00Z'},
                                     {'role': 'assistant', 'content': '可逆化学反应。', 'model': 'mock-model', 'time': '2026-10-11T02:00:01Z', 'apiKey': 'must-not-save'}],
                        'body': '已读取的原文', 'url': 'https://example.com/story',
                        'bodySource': {'url': 'https://example.com/story', 'title': '原文', 'truncated': False, 'endpoint': 'must-not-save'},
                        'apiKey': 'must-not-save', 'endpoint': 'must-not-save', 'model': 'must-not-save'}
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.api_patch.stop(); self.log_patch.stop(); self.root_patch.stop(); self.directory.cleanup()
    def request(self, method, path, payload=None, headers=None, raw=None):
        connection = HTTPConnection('127.0.0.1', self.port, timeout=3)
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        supplied = {'Origin': 'null'}
        if payload is not None or raw is not None: supplied['Content-Type'] = 'application/json'
        supplied.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read()) if response.status != 204 else None
        finally: connection.close()
    def test_learning_snapshot_preserves_evidence(self):
        self.payload['article']['evidence'] = '动物或细胞'
        self.assertEqual(self.request('POST', '/api/notes', self.payload), (200, {'saved': True}))
        status, value = self.request('GET', '/api/notes?id=article_1')
        self.assertEqual(status, 200)
        self.assertEqual(value['record']['article']['evidence'], '动物或细胞')

    def test_save_load_and_list_round_trip_without_connection_settings(self):
        self.assertEqual(self.request('POST', '/api/notes', self.payload), (200, {'saved': True}))
        status, value = self.request('GET', '/api/notes?id=article_1')
        self.assertEqual(status, 200)
        self.assertEqual(value['record']['body'], '已读取的原文')
        self.assertEqual(value['record']['messages'][1]['model'], 'mock-model')
        text = (self.root/'data'/'notes'/'article_1.json').read_text(encoding='utf-8')
        self.assertNotIn('must-not-save', text); self.assertNotIn('apiKey', text)
        self.assertNotIn('endpoint', text)
        self.assertEqual(self.request('GET', '/api/notes')[1]['records'][0]['article']['titleZh'], '电池研究')
        self.assertEqual(self.request('GET', '/api/notes?id=missing'), (200, {'record': None}))
        self.assertFalse(list((self.root/'data'/'notes').glob('*.tmp')))
    def test_invalid_ids_rejected_before_file_operations(self):
        for article_id in ['../escape', 'a/b', 'a\\b', '', 'a'*101, 'CON', 'a.json']:
            with self.subTest(article_id=article_id):
                payload = {**self.payload, 'article': {**self.payload['article'], 'id': article_id}}
                self.assertEqual(self.request('POST', '/api/notes', payload)[0], 400)
        self.assertEqual(self.request('GET', '/api/notes?id=..%2Fescape')[0], 400)
        self.assertFalse((self.root/'data').exists())
    def test_size_limits_reject_request_and_preserve_previous_record(self):
        self.request('POST', '/api/notes', self.payload)
        before = (self.root/'data'/'notes'/'article_1.json').read_bytes()
        self.assertEqual(self.request('POST', '/api/notes', raw=b'{}', headers={'Content-Length': str(s.NOTES_LIMIT+1)})[0], 413)
        payload = {**self.payload, 'messages': [self.payload['messages'][0], {**self.payload['messages'][1], 'content': 'a'*100001}]}
        self.assertEqual(self.request('POST', '/api/notes', payload)[0], 400)
        self.assertEqual((self.root/'data'/'notes'/'article_1.json').read_bytes(), before)
    def test_notes_preserve_dialogue_survive_later_saves_and_delete(self):
        self.request('POST', '/api/notes', self.payload)
        status, value = self.request('POST', '/api/note', {'action': 'add', 'articleId': 'article_1', 'content': '我的删改笔记', 'apiKey': 'must-not-save'})
        self.assertEqual(status, 200); note = value['notes'][0]
        self.request('POST', '/api/notes', self.payload)
        record = self.request('GET', '/api/notes?id=article_1')[1]['record']
        self.assertEqual(record['notes'][0]['content'], '我的删改笔记')
        self.assertEqual(len(record['messages']), 2)
        self.assertEqual(self.request('POST', '/api/note', {'action': 'delete', 'articleId': 'article_1', 'noteId': note['id']})[1], {'notes': []})
    def test_private_config_and_internal_files_are_not_served(self):
        for name in ['ai-settings.json','AI-SETTINGS.JSON','.env','.git/config','logs/server.log','LOGS/server.log']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('private-test-value', encoding='utf-8')
            status, body = self.request('GET', '/' + name)
            self.assertEqual(status, 403)
            self.assertNotIn('private-test-value', json.dumps(body))
        status, body = self.request('GET', '/ai-settings.json?download=1')
        self.assertEqual(status, 403)
        self.assertNotIn('private-test-value', json.dumps(body))

    def test_notes_cannot_bypass_json_origin_host_or_static_file_rules(self):
        self.assertEqual(self.request('POST', '/api/notes', self.payload, {'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/notes', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/notes', self.payload, {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/notes', raw=b'not json')[0], 400)
        self.assertEqual(self.request('POST', '/api/notes', payload=[])[0], 400)
        self.assertEqual(self.request('OPTIONS', '/api/notes')[0], 204)
        self.request('POST', '/api/notes', self.payload)
        for path in ['/data/notes/article_1.json', '/data/%6eotes/article_1.json', '/data/notes/']:
            self.assertEqual(self.request('GET', path)[0], 403)
    def test_list_sorts_by_last_question_and_reports_damaged_records(self):
        self.request('POST', '/api/notes', self.payload)
        newer = {**self.payload, 'article': {**self.payload['article'], 'id': 'article_2'},
                 'messages': [{**self.payload['messages'][0], 'time': '2026-10-11T05:00:00Z'}]}
        self.request('POST', '/api/notes', newer)
        (self.root/'data'/'notes'/'damaged.json').write_text('{', encoding='utf-8')
        value = self.request('GET', '/api/notes')[1]
        self.assertEqual([row['article']['id'] for row in value['records']], ['article_2', 'article_1'])
        self.assertEqual(value['unreadable'], 1)
    def test_total_record_limit_and_failed_atomic_write_keep_previous_record(self):
        payload = {**self.payload, 'messages': [{**self.payload['messages'][0], 'content': 'a'*95000},
                                               {**self.payload['messages'][1], 'content': 'b'*95000}]}
        self.assertEqual(self.request('POST', '/api/notes', payload)[0], 200)
        path = self.root/'data'/'notes'/'article_1.json'; before = path.read_bytes()
        status, value = self.request('POST', '/api/note', {'action': 'add', 'articleId': 'article_1', 'content': 'c'*20000})
        self.assertEqual(status, 400); self.assertIn('200KB', value['error'])
        self.assertEqual(path.read_bytes(), before)
        with patch.object(s.os, 'replace', side_effect=OSError('simulated write failure')):
            self.assertEqual(self.request('POST', '/api/notes', self.payload)[0], 500)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(path.parent.glob('*.tmp')))
    def test_message_roles_and_timestamps_are_validated(self):
        for field, value in [('role', 'system'), ('time', 'not a date'), ('time', '2026-10-11T01:00:00'), ('content', '')]:
            payload = {**self.payload, 'messages': [{**self.payload['messages'][0], field: value}]}
            self.assertEqual(self.request('POST', '/api/notes', payload)[0], 400)
        self.assertFalse((self.root/'data').exists())

if __name__=='__main__': unittest.main()
