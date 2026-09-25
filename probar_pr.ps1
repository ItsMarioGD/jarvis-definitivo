[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [int]$PR = 0
)

& {
if ($PR -le 0) {
    $PR = [int](Read-Host "Numero de PR de GitHub a probar (ej. 5)")
}
if ($PR -le 0) { Write-Host "Numero de PR invalido." -ForegroundColor Red; return }

# --- Carpeta de JARVIS: la actual, la de siempre o la que digas ---
$J = (Get-Location).Path
if (-not (Test-Path "$J\.git") -or -not (Test-Path "$J\web_interface")) { $J = "C:\Users\ItsMarioGD\Downloads\jarvis definitivo" }
if (-not (Test-Path "$J\.git")) { $J = (Read-Host "Pega la ruta de la carpeta de JARVIS").Trim().Trim('"') }
if (-not (Test-Path "$J\.git")) { Write-Host "Ahi no esta JARVIS (no hay carpeta .git)." -ForegroundColor Red; return }
Set-Location $J
$py = if (Test-Path "C:\Python314\python.exe") { "C:\Python314\python.exe" } else { "python" }

Write-Host "`nProbando el PR #$PR (no es la version estable: nadie lo reviso ni le paso las pruebas todavia)." -ForegroundColor Magenta

Write-Host "`n[1/6] Parando JARVIS..." -ForegroundColor Cyan
foreach ($p in 5000, 5001, 8002, 8766, 3000, 5173) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "[2/6] Copia de seguridad de tus archivos locales..." -ForegroundColor Cyan
$bk = Join-Path (Split-Path $J -Parent) ("jarvis-respaldo-" + (Get-Date -Format "yyyyMMdd-HHmm"))
$lista = @(git -c core.quotepath=off ls-files --others --modified --exclude-standard) +
         @(Get-ChildItem -Recurse -File -Filter "__init__.py" -ErrorAction SilentlyContinue |
           Where-Object { $_.FullName -notmatch '[\\/](node_modules|\.git|__pycache__|\.?venv|site-packages)[\\/]' } |
           ForEach-Object { Resolve-Path -Relative -LiteralPath $_.FullName })
$lista | Where-Object { $_ -and $_ -notmatch '^(\.[\\/])?(\.?venv|env)[\\/]' } | ForEach-Object {
    $d = Join-Path $bk $_
    New-Item -ItemType Directory -Force (Split-Path $d) | Out-Null
    Copy-Item -LiteralPath $_ -Destination $d -Force -ErrorAction SilentlyContinue
}
if (Test-Path $bk) { Write-Host "      Respaldo en $bk" -ForegroundColor Yellow }

Write-Host "[3/6] Bajando el PR #$PR de GitHub..." -ForegroundColor Cyan
git fetch origin "pull/$PR/head"
if ($LASTEXITCODE -ne 0) { Write-Host "No pude bajar el PR #$PR. Revisa la conexion o el numero de PR." -ForegroundColor Red; return }
git checkout -f -B "jarvis-pr-$PR" FETCH_HEAD
if ($LASTEXITCODE -ne 0) { Write-Host "Git no pudo cambiar a la version nueva (mira el mensaje de arriba)." -ForegroundColor Red; return }

Write-Host "[4/6] Limpiando restos de versiones anteriores..." -ForegroundColor Cyan
foreach ($d in "web-hud", "jarvis-fui", "liquid-glass-jarvis") {
    if (Test-Path $d) { Remove-Item $d -Recurse -Force -ErrorAction SilentlyContinue }
}
Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch 'node_modules|venv|site-packages' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[5/6] Comprobando dependencias..." -ForegroundColor Cyan
& $py -c "import flask, flask_socketio, qrcode, requests" 2>$null
if ($LASTEXITCODE -ne 0) { & $py -m pip install -r requirements.txt --quiet --disable-pip-version-check }

Write-Host "[6/6] Arrancando JARVIS..." -ForegroundColor Cyan
& $py reiniciar_todo.py
# Solo los PR que traen la app de escritorio nueva (p. ej. "ORIGEN") tienen
# este archivo; en el resto simplemente no se ejecuta este paso.
if (Test-Path "escritorio.py") { & $py escritorio.py --acceso }

Write-Host "`nListo. Version instalada (PR #$PR):" -ForegroundColor Green
git log -1 --format="  %h  %s  (%cr)"
$faltan = git -c core.quotepath=off ls-files --others --exclude-standard | Where-Object { $_ -match '\.py$' }
if ($faltan) {
    Write-Host "`nEstan en tu PC pero NO en este PR (por si eran cambios tuyos sueltos):" -ForegroundColor Yellow
    $faltan | ForEach-Object { Write-Host "  $_" }
}
if (-not (Get-Command tailscale -ErrorAction SilentlyContinue) -and -not (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) {
    Write-Host "`nPara usar JARVIS desde el movil fuera de casa: instala Tailscale en el PC y en el movil" -ForegroundColor Yellow
    Write-Host "con la misma cuenta (https://tailscale.com/download) y luego toca Emparejar en JARVIS." -ForegroundColor Yellow
}
Write-Host "`nEstas en la rama del PR #$PR, no en la version estable. Para volver: git checkout master"
}
