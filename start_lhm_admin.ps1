# start_lhm_admin.ps1 — Launch LibreHardwareMonitor as admin (silent)
$path = Join-Path $PSScriptRoot '_lhm\LibreHardwareMonitor.exe'
Start-Process -FilePath $path -Verb RunAs -WindowStyle Hidden
