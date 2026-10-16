@echo off
setlocal
chcp 65001 >nul
set "RVJINX_ENGINE=%~1"
if defined RVJINX_ENGINE goto validate
if exist "%~dp0Ruta_Unreal.txt" set /p RVJINX_ENGINE=<"%~dp0Ruta_Unreal.txt"
if defined RVJINX_ENGINE goto validate
if exist "%ProgramFiles%\Epic Games\UE_5.6\Engine\Build\Build.version" set "RVJINX_ENGINE=%ProgramFiles%\Epic Games\UE_5.6"
if defined RVJINX_ENGINE goto validate
if exist "D:\Epic Games\UE_5.6\Engine\Build\Build.version" set "RVJINX_ENGINE=D:\Epic Games\UE_5.6"
if defined RVJINX_ENGINE goto validate
if exist "D:\Program Files\Epic Games\UE_5.6\Engine\Build\Build.version" set "RVJINX_ENGINE=D:\Program Files\Epic Games\UE_5.6"
if defined RVJINX_ENGINE goto validate
echo No se encontro Unreal Engine 5.6.
echo Instalarlo desde Epic Games Launcher: https://www.unrealengine.com/download
echo Si ya esta instalado en otra carpeta, guardar su ruta en Ruta_Unreal.txt.
echo Ejemplo de contenido: D:\Unreal\UE_5.6
pause
exit /b 1

:validate
set "RVJINX_PYTHON=%RVJINX_ENGINE%\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
if not exist "%RVJINX_PYTHON%" (
    echo No se encontro el Python incluido con Unreal 5.6.
    echo Revisar Ruta_Unreal.txt. Debe indicar la carpeta UE_5.6 completa.
    pause
    exit /b 1
)
echo Preparando Jinx con Unreal Engine 5.6.
echo El proceso guardara los recursos en esta carpeta.
"%RVJINX_PYTHON%" "%~dp0Tools\build_rv_jinx.py" "%RVJINX_ENGINE%"
set "RVJINX_RESULT=%ERRORLEVEL%"
echo.
if "%RVJINX_RESULT%"=="0" (
    echo Subir al chat Resultado\Cocinados_Jinx_RV.zip para terminar el mod.
) else (
    echo El proceso se detuvo. Enviar el error indicado de la carpeta Logs.
)
pause
exit /b %RVJINX_RESULT%
