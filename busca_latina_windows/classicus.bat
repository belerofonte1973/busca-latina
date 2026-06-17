@echo off
chcp 65001 >nul
cd /d "%~dp0"
python classicus_gui.py %*
if errorlevel 1 (
    echo.
    echo Erro ao iniciar o Classicus. Verifique se o Python esta instalado.
    pause
)
