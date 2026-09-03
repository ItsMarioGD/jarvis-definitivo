<#
    accesos_directos.ps1 - Crea o quita los accesos directos de JARVIS/ULTRON.

    Uso:
      powershell -ExecutionPolicy Bypass -File accesos_directos.ps1 -Raiz "C:\ruta" -Crear
      powershell -ExecutionPolicy Bypass -File accesos_directos.ps1 -Raiz "C:\ruta" -Crear -Autoarranque
      powershell -ExecutionPolicy Bypass -File accesos_directos.ps1 -Raiz "C:\ruta" -Quitar

    Los .lnk se crean en el Escritorio y en el Menu Inicio. El de autoarranque
    va en la carpeta Startup del usuario, que no necesita permisos de
    administrador y se puede quitar a mano desde shell:startup.
#>
param(
    [Parameter(Mandatory = $true)][string]$Raiz,
    [switch]$Crear,
    [switch]$Quitar,
    [switch]$Autoarranque
)

$ErrorActionPreference = "Stop"
$Escritorio = [Environment]::GetFolderPath("Desktop")
$MenuInicio = Join-Path ([Environment]::GetFolderPath("Programs")) "JARVIS"
$Inicio     = [Environment]::GetFolderPath("Startup")

# (nombre visible, .bat destino, icono)
$Apps = @(
    @{ Nombre = "JARVIS"; Bat = "start_jarvis.bat" },
    @{ Nombre = "ULTRON"; Bat = "ultron_start.bat" }
)

function Nuevo-Acceso($Destino, $Objetivo, $Trabajo, $Descripcion, $Icono) {
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut($Destino)
    $lnk.TargetPath = $Objetivo
    $lnk.WorkingDirectory = $Trabajo      # sin esto el .bat hereda el cwd del .lnk
    $lnk.Description = $Descripcion
    $lnk.WindowStyle = 7                  # 7 = minimizado
    if ($Icono -and (Test-Path $Icono)) { $lnk.IconLocation = $Icono }
    $lnk.Save()
    Write-Host "      $Destino"
}

if ($Quitar) {
    Write-Host "  Quitando accesos directos..."
    foreach ($a in $Apps) {
        foreach ($d in @($Escritorio, $MenuInicio, $Inicio)) {
            $f = Join-Path $d ("$($a.Nombre).lnk")
            if (Test-Path $f) { Remove-Item $f -Force; Write-Host "      quitado: $f" }
        }
    }
    $auto = Join-Path $Inicio "JARVIS (autoarranque).lnk"
    if (Test-Path $auto) { Remove-Item $auto -Force; Write-Host "      quitado: $auto" }
    if ((Test-Path $MenuInicio) -and -not (Get-ChildItem $MenuInicio -Force)) {
        Remove-Item $MenuInicio -Force
    }
    Write-Host "  Listo. El autoarranque ya no esta activo."
    exit 0
}

if (-not $Crear) { Write-Host "  Nada que hacer (usa -Crear o -Quitar)."; exit 0 }

if (-not (Test-Path $Raiz)) { throw "No existe la carpeta del proyecto: $Raiz" }
if (-not (Test-Path $MenuInicio)) { New-Item -ItemType Directory -Path $MenuInicio -Force | Out-Null }

$icono = Join-Path $Raiz "web_interface\icon-192.png"
if (-not (Test-Path $icono)) { $icono = $null }

Write-Host "  Accesos directos creados:"
foreach ($a in $Apps) {
    $bat = Join-Path $Raiz $a.Bat
    if (-not (Test-Path $bat)) {
        Write-Host "      [!] falta $($a.Bat); me lo salto"
        continue
    }
    foreach ($d in @($Escritorio, $MenuInicio)) {
        Nuevo-Acceso (Join-Path $d ("$($a.Nombre).lnk")) $bat $Raiz `
                     "Abrir $($a.Nombre)" $icono
    }
}

if ($Autoarranque) {
    $auto = Join-Path $Raiz "autoarranque.bat"
    if (Test-Path $auto) {
        Nuevo-Acceso (Join-Path $Inicio "JARVIS (autoarranque).lnk") $auto $Raiz `
                     "Arranca JARVIS al encender el PC" $icono
        Write-Host "  Autoarranque activado (carpeta Inicio del usuario)."
        Write-Host "  Para quitarlo: ejecuta este script con -Quitar, o borra el"
        Write-Host "  acceso desde  shell:startup"
    } else {
        Write-Host "  [!] No encuentro autoarranque.bat; no activo el autoarranque."
    }
}
