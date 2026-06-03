@echo off
chcp 65001 >nul
cd /d "%~dp0"
python busca_latina_gui.py
if errorlevel 1 (
    echo.
    echo Erro ao iniciar. Certifique-se de que correu instalar.bat primeiro.
    pause
)
