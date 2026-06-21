# criar_atalho.ps1 — Cria atalho do Classicus no Ambiente de Trabalho
# Execucao: powershell -ExecutionPolicy Bypass -File criar_atalho.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Pasta deste script (onde estao os ficheiros .py)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Localizar pythonw.exe (Python sem janela de consola)
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonExe) {
    Write-Warning "Python nao encontrado no PATH. Execute instalar.bat primeiro."
    exit 1
}
$pythonwExe = Join-Path (Split-Path $pythonExe) "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $pythonwExe = $pythonExe
}

# Caminho do Ambiente de Trabalho (funciona com OneDrive e sem)
$desktop = [Environment]::GetFolderPath("Desktop")
$atalho  = Join-Path $desktop "Classicus.lnk"

# Icone personalizado
$iconePath = Join-Path $scriptDir "classicus.png"

# Criar o atalho via WScript.Shell
$wsh      = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($atalho)

$shortcut.TargetPath       = $pythonwExe
$shortcut.Arguments        = "`"$scriptDir\classicus_gui.py`""
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description      = "Classicus — Hebraico, Grego Antigo e Latim"
$shortcut.IconLocation     = "$pythonwExe,0"

$shortcut.Save()

Write-Host ""
Write-Host "Atalho criado em:" -ForegroundColor Green
Write-Host "  $atalho" -ForegroundColor White
Write-Host ""
