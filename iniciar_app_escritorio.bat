@echo off
cd /d "%~dp0"
title PDF a CAD (DXF) Studio - Desktop

set "PY=python"
if exist "C:\Users\Dante Eduardo\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PY=C:\Users\Dante Eduardo\AppData\Local\Programs\Python\Python311\python.exe"
)

echo Iniciando interfaz grafica de escritorio...
"%PY%" gui_app.py
if errorlevel 1 (
    echo.
    echo ========================================================
    echo  Ocurrio un problema al ejecutar la aplicacion.
    echo ========================================================
    pause
)
