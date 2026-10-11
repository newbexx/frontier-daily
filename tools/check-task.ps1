param([switch]$RunNow, [string]$TaskName='FrontierDaily-Personal-0800')
$ErrorActionPreference = 'Stop'
if ($RunNow) {
    $before = (Get-ScheduledTaskInfo -TaskName $TaskName).LastRunTime
    Start-ScheduledTask -TaskName $TaskName
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        $task = Get-ScheduledTask -TaskName $TaskName
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        if ($task.State -ne 'Running' -and $info.LastRunTime -gt $before) { break }
    }
}
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{ TaskName=$task.TaskName; State=$task.State.ToString(); LastRunTime=$info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss'); LastTaskResult=$info.LastTaskResult; NextRunTime=$info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss'); DailyAt=$task.Triggers[0].StartBoundary; LogonCatchUp=($task.Triggers.Count -gt 1); RestartCount=$task.Settings.RestartCount; Action=$task.Actions.Arguments } | ConvertTo-Json
