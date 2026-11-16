@echo off
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python tidak ditemukan. Pasang Python 3.10 atau lebih baru.
        exit /b 1
    )
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)
if not exist "%~dp0tools\whisper.cpp\whisper-cli.exe" (
    echo whisper.cpp belum ditemukan. Instalasi dimulai di jendela terpisah.
    start "SubGen whisper.cpp installer" /min %PYTHON_CMD% -u "%~dp0dl_vulkan.py"
)
echo Membuka aplikasi SubGen...
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0app.py" %*
    exit /b 0
)
start "" %PYTHON_CMD% "%~dp0app.py" %*