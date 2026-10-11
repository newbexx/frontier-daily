param([string]$TaskName = 'FrontierDaily-Personal-0800')
$ErrorActionPreference = 'Stop'
$projectDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$refreshPath = Join-Path $PSScriptRoot 'refresh.py'
$pythonPath = (& python -c 'import sys; print(sys.executable)').Trim()
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python runtime not found.' }
$pythonWindowless = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (Test-Path -LiteralPath $pythonWindowless) { $pythonPath = $pythonWindowless }
if ((Get-TimeZone).BaseUtcOffset.TotalHours -ne 8) { throw 'This installer expects the Windows timezone to be UTC+08:00 for the 08:00 Beijing schedule.' }
$userName = [Environment]::UserDomainName + '\' + [Environment]::UserName
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not ($existing.Actions | Where-Object { $_.Arguments -like ('*"' + $refreshPath + '"*') })) { throw 'A different task already uses this name. No task was changed.' }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('-X utf8 "' + $refreshPath + '" --if-due') -WorkingDirectory $projectDir
$daily = New-ScheduledTaskTrigger -Daily -At '08:00'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $userName
$logon.Delay = 'PT1M'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily,$logon) -Settings $settings -Principal $principal -Description 'Frontier Daily: collect public RSS at 08:00 China time and let the AI editor pick the news; catch up at user logon.' -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{ TaskName=$task.TaskName; State=$task.State.ToString(); NextRunTime=$info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss'); Execute=$task.Actions.Execute; Arguments=$task.Actions.Arguments; StartWhenAvailable=$task.Settings.StartWhenAvailable; LogonType=$task.Principal.LogonType.ToString(); RunLevel=$task.Principal.RunLevel.ToString(); WakeToRun=$task.Settings.WakeToRun } | ConvertTo-Json
