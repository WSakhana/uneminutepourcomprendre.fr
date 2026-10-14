# Tâche utilisateur locale ; aucune clé ni aucun mot de passe dans sa définition.
$ErrorActionPreference = 'Stop'
$taskName = 'UMPC - Synchronisation articles YouTube'
$repoPath = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot 'run_article_sync.py'
$pythonPath = Join-Path $repoPath '.venv\Scripts\pythonw.exe'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $scriptPath + '"') -WorkingDirectory $repoPath
$repeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) -RepetitionInterval (New-TimeSpan -Minutes 15)
$logon = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($repeat, $logon) -Settings $settings -Principal $principal -Description 'Vérifie le statut YouTube réel ; publie les articles prêts par les outils OVH existants. Aucun changement des descriptions YouTube.' -Force | Select-Object TaskName,State
