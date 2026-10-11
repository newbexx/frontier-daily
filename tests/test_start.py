import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


POWERSHELL = shutil.which('powershell.exe')
START = Path(__file__).resolve().parents[1] / 'tools' / 'start.ps1'


@unittest.skipUnless(POWERSHELL, 'Windows PowerShell is required')
class LauncherTests(unittest.TestCase):
    def run_launcher(self, scenario='old', command='python -X utf8 tools/serve.py --port 8768'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            shutil.copyfile(START, root / 'tools' / 'start.ps1')
            shutil.copyfile(START.parents[1] / 'index.html', root / 'index.html')
            (root / 'fixture.json').write_text(json.dumps({'scenario': scenario, 'command': command.replace(str(START.with_name('serve.py')), str(root / 'tools' / 'serve.py'))}), encoding='utf-8')
            harness = root / 'check.ps1'
            harness.write_text(r'''
$ErrorActionPreference = 'Stop'
$global:launcherTest_fixture = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixture.json') -Raw | ConvertFrom-Json
$global:launcherTest_root = $PSScriptRoot
$global:launcherTest_started = 0
$global:launcherTest_stopped = 0
$global:launcherTest_opened = 0
function python { 'C:\test-python\python.exe' }
function Invoke-WebRequest {
    param($Uri, [switch]$UseBasicParsing, $TimeoutSec)
    if ($global:launcherTest_fixture.scenario -eq 'fresh' -and -not $global:launcherTest_started) { throw 'Connection refused' }
    if ($Uri.EndsWith('index.html')) {
        if ($global:launcherTest_fixture.scenario -eq 'foreign') { return @{ Content = 'Other website' } }
        if ($global:launcherTest_fixture.scenario -eq 'redesigned') { return @{ Content = [IO.File]::ReadAllText((Join-Path $global:launcherTest_root 'index.html')) } }
        return @{ Content = 'THE FRONTIER <button id="reload-edition">' }
    }
    if ($Uri -match '/tools/frontier-preview-') {
        if ($global:launcherTest_fixture.scenario -eq 'copy') { throw 'Not found in this copy' }
        $file = Join-Path $global:launcherTest_root ([uri]$Uri).AbsolutePath.TrimStart('/').Replace('/', '\')
        return @{ Content = [IO.File]::ReadAllText($file) }
    }
    if ($Uri.EndsWith('data/latest.json')) { return @{ Content = '{}' } }
    throw ('Unexpected request: ' + $Uri)
}
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    if (-not $Uri.EndsWith('api/health')) { throw 'Unexpected API' }
    if ($global:launcherTest_fixture.scenario -eq 'fresh' -and -not $global:launcherTest_started) { throw 'Connection refused' }
    if ($global:launcherTest_fixture.scenario -eq 'foreign-health') { return @{ service = 'other-site'; version = 5; features = @('notes') } }
    if ($global:launcherTest_fixture.scenario -in @('current','redesigned') -or $global:launcherTest_started) {
        if ($global:launcherTest_fixture.scenario -eq 'unready') { return @{ service = 'frontier-personal'; version = 5; features = @('explain') } }
        return @{ service = 'frontier-personal'; version = 5; features = @('notes') }
    }
    return @{ service = 'frontier-personal'; version = 4; features = @('explain') }
}
function Get-NetTCPConnection {
    param($LocalPort, $State, $ErrorAction)
    if ($global:launcherTest_fixture.scenario -eq 'inspect-error') { throw 'Process inspection denied' }
    [pscustomobject]@{ OwningProcess = 1234 }
}
function Get-CimInstance {
    param($ClassName, $Filter)
    @{ ProcessId = 1234; CommandLine = $global:launcherTest_fixture.command }
}
function Stop-Process {
    param($Id, $ErrorAction)
    if ($global:launcherTest_fixture.scenario -eq 'stop-error') { throw 'Process stop denied' }
    $global:launcherTest_stopped++
}
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle)
    if ($FilePath -eq 'http://127.0.0.1:8768/') { $global:launcherTest_opened++ }
    else { $global:launcherTest_started++ }
}
function Start-Sleep { param($Milliseconds) }
$failure = $null
try { & (Join-Path $PSScriptRoot 'tools\start.ps1') } catch { $failure = $_.Exception.Message }
@{ started = $global:launcherTest_started; stopped = $global:launcherTest_stopped; opened = $global:launcherTest_opened; error = $failure;
   probes = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'tools') -Filter 'frontier-preview-*').Count } | ConvertTo-Json -Compress
''', encoding='utf-8')
            result = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout.strip())

    def test_old_service_relative_and_absolute_paths_restart(self):
        for command in ['python -X utf8 tools/serve.py --port 8768',
                        'python -X utf8 tools\\serve.py --port 8768',
                        f'python -X utf8 "{START.with_name("serve.py")}" --port 8768']:
            with self.subTest(command=command):
                result = self.run_launcher(command=command)
                self.assertIsNone(result['error'], result)
                self.assertEqual((result['stopped'], result['started'], result['opened']), (1, 1, 1))
                self.assertEqual(result['probes'], 0)

    def test_current_service_reused(self):
        result = self.run_launcher('current')
        self.assertIsNone(result['error'])
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 0, 1))
        self.assertEqual(result['probes'], 0)

    def test_redesigned_page_reuses_current_service(self):
        result = self.run_launcher('redesigned')
        self.assertIsNone(result['error'], result)
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 0, 1))
        self.assertEqual(result['probes'], 0)

    def test_foreign_health_never_stopped_or_opened(self):
        result = self.run_launcher('foreign-health')
        self.assertTrue(result['error'])
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 0, 0))

    def test_foreign_site_never_stopped_or_opened(self):
        result = self.run_launcher('foreign')
        self.assertTrue(result['error'])
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 0, 0))

    def test_other_project_copy_never_stopped(self):
        result = self.run_launcher('copy', f'python "{START.with_name("serve.py")}" --port 8768')
        self.assertTrue(result['error'])
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 0, 0))
        self.assertEqual(result['probes'], 0)

    def test_process_inspection_error_is_reported(self):
        result = self.run_launcher('inspect-error')
        self.assertEqual(result['error'], 'Process inspection denied')
        self.assertEqual(result['opened'], 0)
        self.assertEqual(result['probes'], 0)

    def test_process_stop_error_is_reported(self):
        result = self.run_launcher('stop-error', f'python "{START.with_name("serve.py")}" --port 8768')
        self.assertEqual(result['error'], 'Process stop denied')
        self.assertEqual((result['started'], result['opened']), (0, 0))
        self.assertEqual(result['probes'], 0)

    def test_fresh_server_starts(self):
        result = self.run_launcher('fresh')
        self.assertIsNone(result['error'])
        self.assertEqual((result['stopped'], result['started'], result['opened']), (0, 1, 1))

    def test_start_requires_notes_api_health(self):
        result = self.run_launcher('unready', f'python "{START.with_name("serve.py")}" --port 8768')
        self.assertTrue(result['error'])
        self.assertEqual(result['opened'], 0)
