# baixar_corpora.ps1 — Descarrega os corpora latinos para o Busca Latina
# Execucao: clique direito -> "Executar com PowerShell"
# Ou no terminal: powershell -ExecutionPolicy Bypass -File baixar_corpora.ps1

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$base   = "$env:USERPROFILE\cltk_data\lat\text"
$tmpDir = "$env:TEMP\busca_latina_corpora"

function Instalar-Corpus {
    param(
        [string]$Nome,
        [string]$Url,
        [string]$Destino,
        [string]$PastaZip   # nome da pasta dentro do ZIP (normalmente "repo-master")
    )

    if (Test-Path "$Destino\.git" -ErrorAction SilentlyContinue) {
        Write-Host "  [ja instalado via git] $Nome" -ForegroundColor Green
        return
    }
    if ((Test-Path $Destino) -and (Get-ChildItem $Destino -ErrorAction SilentlyContinue | Measure-Object).Count -gt 5) {
        Write-Host "  [ja instalado] $Nome" -ForegroundColor Green
        return
    }

    Write-Host "`nA descarregar $Nome..." -ForegroundColor Cyan
    $zip = "$tmpDir\$Nome.zip"
    New-Item -ItemType Directory -Force $tmpDir | Out-Null

    # Download com barra de progresso
    $wc = New-Object System.Net.WebClient
    $wc.DownloadFile($Url, $zip)

    Write-Host "  A extrair..." -ForegroundColor Cyan
    $extracted = "$tmpDir\$Nome"
    Remove-Item $extracted -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $extracted -Force

    # Mover para o destino (a pasta dentro do ZIP tem sufixo "-master" ou "-main")
    $inner = Get-ChildItem $extracted | Select-Object -First 1
    if ($null -eq $inner) {
        Write-Warning "ZIP vazio ou estrutura inesperada para $Nome"
        return
    }

    New-Item -ItemType Directory -Force $Destino | Out-Null
    Get-ChildItem $inner.FullName | Move-Item -Destination $Destino -Force

    Remove-Item $zip      -Force -ErrorAction SilentlyContinue
    Remove-Item $extracted -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: $Destino" -ForegroundColor Green
}

Write-Host "============================================================"
Write-Host " Busca Latina — Instalacao dos corpora latinos"
Write-Host "============================================================"
Write-Host " Destino: $base"
Write-Host ""

New-Item -ItemType Directory -Force $base | Out-Null

# Latin Library (~26 MB)
Instalar-Corpus `
    -Nome     "lat_text_latin_library" `
    -Url      "https://github.com/cltk/lat_text_latin_library/archive/refs/heads/master.zip" `
    -Destino  "$base\lat_text_latin_library"

# Perseus / CLTK
Instalar-Corpus `
    -Nome     "lat_text_perseus" `
    -Url      "https://github.com/cltk/lat_text_perseus/archive/refs/heads/master.zip" `
    -Destino  "$base\lat_text_perseus"

Write-Host ""
Write-Host "============================================================"
Write-Host " Corpora instalados com sucesso!"
Write-Host ""
Write-Host " Latin Library:" (Get-ChildItem "$base\lat_text_latin_library" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count "ficheiros"
Write-Host " Perseus:      " (Get-ChildItem "$base\lat_text_perseus"        -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count "ficheiros"
Write-Host "============================================================"

Read-Host "`nPressione Enter para fechar"
