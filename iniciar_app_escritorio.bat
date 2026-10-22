@echo off
cd /d "%~dp0"
title PDF a CAD (DXF) Studio - Desktop
echo Iniciando interfaz grafica de escritorio...
python gui_app.py
if errorlevel 1 (
    echo.
    echo Ocurrio un error al iniciar la aplicacion.
    pause
)
