@echo off
title The Room — Dashboard
echo ================================
echo  The Room Argentina - Dashboard
echo ================================
echo.

:: Verificar Python
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado.
    echo Instalalo desde https://python.org
    pause
    exit /b 1
)

:: Instalar dependencias si no estan
echo Verificando dependencias...
py -3 -m pip install -r requirements.txt --quiet --disable-pip-version-check

echo.
echo Iniciando dashboard...
echo Abri http://localhost:8501 en tu navegador
echo Presiona Ctrl+C para detener
echo.

py -3 -m streamlit run app.py --server.port 8501 --server.address localhost --browser.gatherUsageStats false

pause
