$ErrorActionPreference = 'Stop'
$projectDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = (& python -c 'import sys; print(sys.executable)').Trim()
# The page asks this server to collect when the edition is out of date (AI editing takes a minute or two).
$address = 'http://127.0.0.1:8768/'
$serving = $false
$response = $null
try { $response = Invoke-WebRequest -Uri ($address + 'index.html') -UseBasicParsing -TimeoutSec 3 } catch {
    if ($_.Exception.Response) { throw 'Port 8768 is occupied by another HTTP service.' }
}
if ($response) {
    # Use a stable control ID; branding changes must not reject our own page.
    $serving = $response.Content.Contains('id="reload-edition"')
    if (-not $serving) { throw 'Port 8768 is serving a different site.' }
    $health = Invoke-RestMethod -Uri ($address + 'api/health') -TimeoutSec 3
    if ($health.service -ne 'frontier-personal') { throw 'Port 8768 is serving a different site.' }
    # A unique file proves the server uses this checkout, including legacy relative-path launches.
    $probeToken = [Guid]::NewGuid().ToString('N')
    $probeName = 'frontier-preview-' + $probeToken + '.txt'
    $probePath = Join-Path $PSScriptRoot $probeName
    try {
        [IO.File]::WriteAllText($probePath, $probeToken)
        $probe = Invoke-WebRequest -Uri ($address + 'tools/' + $probeName) -UseBasicParsing -TimeoutSec 3
        if ($probe.Content -ne $probeToken) { throw 'Port 8768 is serving a different project directory.' }
    } finally {
        if (Test-Path -LiteralPath $probePath) { Remove-Item -LiteralPath $probePath -ErrorAction Stop }
    }
    if ($health.version -lt 5 -or $health.features -notcontains 'notes') {
        $owners = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique)
        if ($owners.Count -ne 1) { throw 'Could not identify the local preview server process.' }
        $existing = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owners[0])
        if (-not $existing.CommandLine -or $existing.CommandLine -notmatch '(?:^|[\s"\\/])serve\.py(?=$|[\s"])') {
            throw 'Port 8768 is serving a different site.'
        }
        Stop-Process -Id $existing.ProcessId -ErrorAction Stop
        $serving = $false
    }
}
if (-not $serving) {
    $pythonWindowless = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
    if (Test-Path -LiteralPath $pythonWindowless) { $pythonPath = $pythonWindowless }
    Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8',('"' + (Join-Path $PSScriptRoot 'serve.py') + '"'), '--port', '8768') -WorkingDirectory $projectDir -WindowStyle Hidden
    for ($attempt=0; $attempt -lt 12; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri ($address + 'api/health') -TimeoutSec 2
            if ($health.service -eq 'frontier-personal' -and $health.version -ge 5 -and $health.features -contains 'notes') { $serving=$true; break }
        } catch {}
        Start-Sleep -Milliseconds 400
    }
    if (-not $serving) { throw 'The local preview server could not be started with learning records enabled.' }
}
Start-Process $address
