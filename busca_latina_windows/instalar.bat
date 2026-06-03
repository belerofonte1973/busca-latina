@echo off
chcp 65001 >nul
echo ============================================================
echo  Busca Latina — Instalacao para Windows 11 ARM
echo ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Instale Python 3.11 ou superior em: https://www.python.org/downloads/
    echo Marque a opcao "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

echo Python encontrado:
python --version
echo.

:: Actualizar pip
echo [1/4] A actualizar pip...
python -m pip install --upgrade pip --quiet
echo     OK
echo.

:: Instalar dependencias principais
echo [2/4] A instalar dependencias (PyQt6, edge-tts, pygame)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO durante a instalacao. Verifique a ligacao a internet.
    pause
    exit /b 1
)
echo.

:: Verificar instalacao
echo [3/4] A verificar instalacao...
python -c "import PyQt6; print('  PyQt6: OK -', PyQt6.QtCore.PYQT_VERSION_STR)"
python -c "import edge_tts; print('  edge-tts: OK')"
python -c "import pygame; print('  pygame: OK -', pygame.version.ver)"
python -c "import requests; print('  requests: OK')"
echo.

:: Informacao sobre Ollama
echo [4/4] Ollama (IA local — opcional):
echo   Instale em: https://ollama.com/download/windows
echo   Depois execute: ollama pull llama3.2
echo.

:: Informacao sobre espeak-ng (IPA)
echo   espeak-ng para IPA (opcional):
echo   Instale em: https://github.com/espeak-ng/espeak-ng/releases
echo.

:: Criar atalho no Ambiente de Trabalho
echo [5/5] A criar atalho no Ambiente de Trabalho...
powershell -ExecutionPolicy Bypass -File "%~dp0criar_atalho.ps1"
if errorlevel 1 (
    echo   Aviso: nao foi possivel criar o atalho automaticamente.
    echo   Execute manualmente: powershell -File criar_atalho.ps1
) else (
    echo   Atalho "Busca Latina" criado no Ambiente de Trabalho.
)
echo.

echo ============================================================
echo  Instalacao concluida!
echo  Abra o Busca Latina pelo atalho no Ambiente de Trabalho
echo  ou clique duas vezes em busca_latina.bat
echo ============================================================
echo.
pause
