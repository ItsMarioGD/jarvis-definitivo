<#
    abrir_firewall.ps1 - Deja que el telefono llegue a JARVIS.

    Windows bloquea las conexiones entrantes salvo que haya una regla que las
    permita. Sin ella el movil carga la pagina a veces si y a veces no: al
    instalar Python, Windows crea una regla solo para el perfil de red que
    estuviera activo en ese momento, asi que en cuanto la Wi-Fi cambia de
    «publica» a «privada» (o al reves) el telefono deja de conectar y parece
    que JARVIS se ha roto.

    Esta regla abre los puertos de JARVIS en TODOS los perfiles de red, de una
    vez y para siempre.

    Hay que ejecutarlo COMO ADMINISTRADOR:
        clic derecho en herramientas\abrir_firewall.ps1
        -> "Ejecutar con PowerShell" (aceptando el aviso de administrador)

    O desde una consola de administrador:
        powershell -ExecutionPolicy Bypass -File herramientas\abrir_firewall.ps1

    Para quitarla:
        powershell -ExecutionPolicy Bypass -File herramientas\abrir_firewall.ps1 -Quitar
#>
param(
    [switch]$Quitar,
    [int[]]$Puertos = @(5000, 8766)
)

$ErrorActionPreference = "Stop"
$NOMBRE = "JARVIS (movil)"

function EsAdministrador {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (EsAdministrador)) {
    Write-Host ""
    Write-Host "  Esto necesita permisos de administrador." -ForegroundColor Yellow
    Write-Host "  Cierra esta ventana y abrelo con clic derecho ->"
    Write-Host "  'Ejecutar como administrador'."
    Write-Host ""
    Read-Host "  Pulsa Enter para salir"
    exit 1
}

$existente = Get-NetFirewallRule -DisplayName $NOMBRE -ErrorAction SilentlyContinue
if ($existente) {
    Remove-NetFirewallRule -DisplayName $NOMBRE
    Write-Host "  Regla anterior eliminada."
}

if ($Quitar) {
    Write-Host ""
    Write-Host "  Listo: el telefono ya no podra conectarse a JARVIS." -ForegroundColor Green
    Write-Host ""
    exit 0
}

New-NetFirewallRule -DisplayName $NOMBRE `
    -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Puertos -Profile Any `
    -Description "Permite que el telefono se conecte a JARVIS y ULTRON en la red local." | Out-Null

Write-Host ""
Write-Host "  Firewall configurado." -ForegroundColor Green
Write-Host "  Puertos abiertos para entrada: $($Puertos -join ', ')"
Write-Host "  En todos los perfiles de red (publica, privada y de dominio)."
Write-Host ""

# La IP que hay que teclear en el telefono, por comodidad.
try {
    $ip = (Get-NetIPConfiguration |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1).IPv4Address.IPAddress
    if ($ip) {
        Write-Host "  Emparejar el telefono:  http://${ip}:5000/pair" -ForegroundColor Cyan
        Write-Host ""
    }
} catch { }
