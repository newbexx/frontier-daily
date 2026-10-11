"""Fresh-install AI setup without a Codex account or real provider credentials."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('setup_serve', ROOT / 'tools/serve.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class AISetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.codex = self.folder / 'absent-config.toml'
        self.settings = self.folder / 'ai-settings.json'
        runtime = {name:value for name,value in os.environ.items() if name.upper() in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP','COMSPEC','PATHEXT')}
        runtime.update(USERPROFILE=str(self.folder), HOME=str(self.folder))
        self.env = patch.dict(os.environ, runtime, clear=True)
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()
    def config(self, **fields):
        self.settings.write_text(json.dumps(fields), encoding='utf-8')
        return s.read_current_config(self.codex, self.settings)
    def test_project_connection_needs_no_codex(self):
        os.environ['FRONTIER_API_KEY'] = 'local-test-secret'
        result = self.config(endpoint='https://provider.example/v1', model='test-model', wireApi='chat')
        self.assertEqual(result, {'endpoint':'https://provider.example/v1','model':'test-model','key':'local-test-secret','wire':'chat'})
    def test_environment_only_setup(self):
        os.environ.update(FRONTIER_API_BASE='https://provider.example/v1', FRONTIER_MODEL='env-model', FRONTIER_API_KEY='local-test-secret')
        self.assertEqual(s.read_current_config(self.codex, self.settings)['wire'], 'chat')
    def test_environment_overrides_project_fields(self):
        os.environ.update(FRONTIER_API_BASE='https://override.example/v1', FRONTIER_MODEL='env-model', FRONTIER_WIRE_API='responses', FRONTIER_API_KEY='local-test-secret')
        result = self.config(endpoint='https://project.example/v1', model='project-model', wireApi='chat')
        self.assertEqual((result['endpoint'], result['model'], result['wire']), ('https://override.example/v1','env-model','responses'))
    def test_named_key_environment(self):
        os.environ['MY_PROVIDER_KEY'] = 'local-test-secret'
        self.assertEqual(self.config(endpoint='https://provider.example', model='m', apiKeyEnv='MY_PROVIDER_KEY')['key'], 'local-test-secret')
    def test_missing_key_is_actionable(self):
        with self.assertRaises(s.InputError) as error:
            self.config(endpoint='https://provider.example', model='m')
        self.assertIn('FRONTIER_API_KEY', str(error.exception))
    def test_invalid_explicit_connection_cannot_fall_back(self):
        os.environ['FRONTIER_API_KEY'] = 'local-test-secret'
        for fields in [dict(endpoint='http://provider.example',model='m'),dict(endpoint='https://user:pass@provider.example',model='m'),dict(endpoint='https://provider.example?key=test',model='m'),dict(endpoint='https://provider.example',model='m',wireApi='invalid'),dict(endpoint='https://provider.example',model='m',apiKeyEnv='../bad'),dict(endpoint='https://provider.example',model='')]:
            with self.subTest(fields=fields), self.assertRaises(s.InputError):
                self.config(**fields)
    def test_no_configuration_has_setup_message(self):
        with self.assertRaises(s.InputError) as error:
            s.read_current_config(self.codex, self.settings)
        self.assertIn('ai-settings', str(error.exception))
    def test_mock_provider_full_call_and_check_command(self):
        received = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path,self.headers.get('Authorization'),body))
                response = {'choices':[{'message':{'content':'OK'}}]} if self.path.endswith('/chat/completions') else {'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]}
                raw = json.dumps(response).encode()
                self.send_response(200); self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1',0), Provider)
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            endpoint = 'http://127.0.0.1:' + str(server.server_port) + '/v1'
            for wire in ['chat','responses']:
                os.environ.update(FRONTIER_API_BASE=endpoint, FRONTIER_MODEL='test-model', FRONTIER_API_KEY='local-test-secret', FRONTIER_WIRE_API=wire)
                with patch.object(s,'CONFIG',self.codex), patch.object(s,'SETTINGS',self.settings):
                    self.assertEqual(s.explain({'prompt':'测试连接','mode':'current'})['answer'],'OK')
                env = dict(os.environ)
                result = subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/check-ai.py')],capture_output=True,text=True,encoding='utf-8',env=env,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('成功',result.stdout)
                self.assertNotIn('local-test-secret',result.stdout+result.stderr)
            self.assertEqual([item[0] for item in received], ['/v1/chat/completions','/v1/chat/completions','/v1/responses','/v1/responses'])
            self.assertTrue(all(item[1]=='Bearer local-test-secret' for item in received))
        finally:
            server.shutdown();server.server_close();thread.join()
