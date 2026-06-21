@echo off
cd /d "%~dp0"

:: Localizar python.exe no PATH
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "PYEXE=%%i"
    goto :found_py
)
echo ERRO: Python nao encontrado. Instale Python 3.11+ e marque "Add to PATH".
pause
exit /b 1

:found_py
:: Usar pythonw (sem janela de console) se existir no mesmo diretorio
set "PYWEXE=%PYEXE:python.exe=pythonw.exe%"
if exist "%PYWEXE%" (
    start "" "%PYWEXE%" "%~dp0classicus_gui.py"
) else (
    start "" "%PYEXE%" "%~dp0classicus_gui.py"
)
