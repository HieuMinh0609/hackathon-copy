@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "VENV_PY=.venv\Scripts\python.exe"
set "COMMAND=%~1"
if "%COMMAND%"=="" set "COMMAND=run"

if /I "%COMMAND%"=="setup" goto setup
if /I "%COMMAND%"=="setup-global" goto setup_global
if /I "%COMMAND%"=="run" goto run
if /I "%COMMAND%"=="global" goto run_global
if /I "%COMMAND%"=="globle" goto run_global
if /I "%COMMAND%"=="--global" goto run_global
if /I "%COMMAND%"=="-global" goto run_global
if /I "%COMMAND%"=="backend" goto backend
if /I "%COMMAND%"=="test" goto test
if /I "%COMMAND%"=="help" goto help
if /I "%COMMAND%"=="--help" goto help
if /I "%COMMAND%"=="-h" goto help

echo [LOI] Lenh khong hop le: %COMMAND%
echo.
goto help_error

:setup
echo === Cai dat moi truong AI Buddy tren Windows ===
call :configure_pip_options %*
if errorlevel 1 exit /b 1
call :check_global_python
if errorlevel 1 exit /b 1

if not exist "%VENV_PY%" (
    echo Dang tao moi truong ao .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 exit /b 1
) else (
    echo Da tim thay .venv.
)

echo.
echo Buoc tiep theo se cai cac goi Python trong requirements.txt vao .venv.
choice /C YN /N /M "Ban co dong y tiep tuc? [Y/N]: "
if errorlevel 2 (
    echo Da huy cai dat dependency.
    exit /b 0
)

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo Da tao .env tu .env.example. Hay kiem tra lai cau hinh PostgreSQL.
) else (
    echo Giu nguyen file .env hien tai.
)

echo.
echo Cai dat Python da hoan tat.
echo Tiep theo, khoi dong PostgreSQL va Ollama theo huong dan trong README.md.
echo Sau do chay: run_windows.bat
exit /b 0

:setup_global
echo === Cai dependency vao Python global ===
call :configure_pip_options %*
if errorlevel 1 exit /b 1
call :check_global_python
if errorlevel 1 exit /b 1

echo.
echo Canh bao: lenh nay se thay doi moi truong Python global tren may.
choice /C YN /N /M "Ban co dong y cai requirements.txt vao Python global? [Y/N]: "
if errorlevel 2 (
    echo Da huy cai dat dependency global.
    exit /b 0
)

%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo Da tao .env tu .env.example. Hay kiem tra lai cau hinh PostgreSQL.
) else (
    echo Giu nguyen file .env hien tai.
)

echo Cai dat global da hoan tat. Chay ung dung bang: run_windows.bat global
exit /b 0

:run
call :check_runtime
if errorlevel 1 exit /b 1
echo Dang khoi dong AI Buddy (Backend + Desktop UI) bang %PYTHON_DISPLAY%...
echo [LOG] Log Backend va Frontend duoc ghi nhan truc tiep ben duoi va tai: logs\app.log
%PYTHON_RUN% main.py
exit /b %errorlevel%

:run_global
call :check_global_runtime
if errorlevel 1 exit /b 1
echo Dang khoi dong AI Buddy bang Python global (Backend + Desktop UI)...
echo [LOG] Log Backend va Frontend duoc ghi nhan truc tiep ben duoi va tai: logs\app.log
%PYTHON_CMD% main.py
exit /b %errorlevel%

:backend
call :check_runtime
if errorlevel 1 exit /b 1
echo Dang khoi dong backend API tai http://127.0.0.1:8765 bang %PYTHON_DISPLAY%...
%PYTHON_RUN% -m backend.main
exit /b %errorlevel%

:test
call :select_runtime
if errorlevel 1 exit /b 1
%PYTHON_RUN% -m pytest
exit /b %errorlevel%

:check_runtime
call :select_runtime
if errorlevel 1 exit /b 1
if not exist ".env" (
    echo [LOI] Chua co file .env. Hay sao chep .env.example thanh .env va kiem tra cau hinh.
    exit /b 1
)
%PYTHON_RUN% -c "import fastapi, flet, uvicorn" >nul 2>&1
if errorlevel 1 (
    if /I "%PYTHON_SOURCE%"=="venv" (
        echo [LOI] Dependency trong .venv chua day du. Hay chay lai: run_windows.bat setup
    ) else (
        echo [LOI] Dependency cua Python tren may chua day du. Hay chay: run_windows.bat setup-global
    )
    exit /b 1
)
exit /b 0

:select_runtime
set "PYTHON_RUN="
set "PYTHON_DISPLAY="
set "PYTHON_SOURCE="

if exist "%VENV_PY%" (
    set PYTHON_RUN="%VENV_PY%"
    set "PYTHON_DISPLAY=.venv"
    set "PYTHON_SOURCE=venv"
    exit /b 0
)

call :check_global_python
if errorlevel 1 exit /b 1
set "PYTHON_RUN=%PYTHON_CMD%"
set "PYTHON_DISPLAY=Python tren may (%PYTHON_CMD%)"
set "PYTHON_SOURCE=global"
echo Khong tim thay .venv, tu dong dung %PYTHON_DISPLAY%.
exit /b 0

:check_global_python
set "PYTHON_CMD="

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python3"
    )
)

if not defined PYTHON_CMD (
    echo [LOI] Khong tim thay Python 3.11 tro len.
    echo Hay cai Python va chon tuy chon "Add Python to PATH".
    exit /b 1
)

echo Su dung Python tren may: %PYTHON_CMD%
exit /b 0

:configure_pip_options
set "CUSTOM_PIP_INDEX_URL="
set "CUSTOM_PIP_TRUSTED_HOST="
shift

:parse_pip_options
if "%~1"=="" goto pip_options_ready

if /I "%~1"=="-i" (
    if "%~2"=="" (
        echo [LOI] Thieu URL sau tuy chon -i.
        exit /b 1
    )
    set "CUSTOM_PIP_INDEX_URL=%~2"
    shift
    shift
    goto parse_pip_options
)

if /I "%~1"=="--trusted-host" (
    if "%~2"=="" (
        echo [LOI] Thieu ten may sau tuy chon --trusted-host.
        exit /b 1
    )
    set "CUSTOM_PIP_TRUSTED_HOST=%~2"
    shift
    shift
    goto parse_pip_options
)

echo [LOI] Tuy chon pip khong hop le: %~1
echo Chi ho tro: -i URL va --trusted-host HOST
exit /b 1

:pip_options_ready
if defined CUSTOM_PIP_INDEX_URL set "PIP_INDEX_URL=%CUSTOM_PIP_INDEX_URL%"
if defined CUSTOM_PIP_TRUSTED_HOST set "PIP_TRUSTED_HOST=%CUSTOM_PIP_TRUSTED_HOST%"

if defined CUSTOM_PIP_INDEX_URL (
    echo Su dung pip index: %CUSTOM_PIP_INDEX_URL%
) else (
    echo Su dung cau hinh pip mac dinh tren may.
)
if defined CUSTOM_PIP_TRUSTED_HOST echo Trusted host: %CUSTOM_PIP_TRUSTED_HOST%
exit /b 0

:check_global_runtime
call :check_global_python
if errorlevel 1 exit /b 1
if not exist ".env" (
    echo [LOI] Chua co file .env. Hay tao tu .env.example.
    exit /b 1
)
%PYTHON_CMD% -c "import fastapi, flet, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Dependency global chua day du. Hay chay: run_windows.bat setup-global
    exit /b 1
)
exit /b 0

:help
echo Cach dung:
echo   run_windows.bat          Khoi dong app; uu tien .venv, neu thieu thi dung Python tren may
echo   run_windows.bat setup    Tao .venv, cai dependency va tao .env
echo       Tuy chon: -i URL --trusted-host HOST
echo   run_windows.bat global   Chay bang Python global, khong dung .venv
echo   run_windows.bat setup-global  Cai dependency vao Python global
echo       Tuy chon: -i URL --trusted-host HOST
echo   run_windows.bat backend  Chi khoi dong backend API, tu dong chon Python
echo   run_windows.bat test     Chay bo test, tu dong chon Python
echo   run_windows.bat help     Hien thi tro giup
exit /b 0

:help_error
echo Cach dung: run_windows.bat [setup^|setup-global^|run^|global^|backend^|test^|help]
exit /b 1
