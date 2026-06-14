@echo off
title PatoToolBot - Build Menu
color 0A

cd /d "%~dp0"

echo ============================================
echo    PatoToolBot - Build Menu
echo ============================================
echo.
echo [1] Build Fast (keep old build files)
echo [2] Build Clean (remove old build files)
echo [3] Exit
echo.
set /p choice="Choose option (1-3): "

if "%choice%"=="1" goto build_fast
if "%choice%"=="2" goto build_clean
if "%choice%"=="3" goto end

echo Invalid choice!
pause
exit /b 1

:build_fast
echo.
echo ============================================
echo    Build FAST (skipping cleanup)
echo ============================================
echo.
goto setup

:build_clean
echo.
echo ============================================
echo    Build CLEAN (removing old files)
echo ============================================
echo.
echo Cleaning old builds...
if exist build      rmdir /s /q build      >nul 2>&1
if exist dist       rmdir /s /q dist       >nul 2>&1
if exist *.spec     del *.spec             >nul 2>&1
if exist build_env  rmdir /s /q build_env  >nul 2>&1
echo Cleaned!
echo.
goto setup

:setup
REM ── Create venv ───────────────────────────────────────────────────────────────
if not exist "build_env\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv build_env
    if errorlevel 1 (
        echo ERROR: Failed to create venv
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call build_env\Scripts\activate.bat

echo Upgrading pip/wheel/setuptools...
python -m pip install --upgrade pip wheel setuptools >nul 2>&1

REM ── PyTorch CPU-only ──────────────────────────────────────────────────────────
REM    CPU build keeps the bundle small (~600 MB). The +cu124 wheel pulls in
REM    ~2.8 GB of CUDA DLLs. The +cpu local version forces a reinstall even when
REM    a CUDA build is already present in build_env.
echo Installing PyTorch (CPU-only) (this may take a few minutes)...
python -m pip install torch==2.6.0+cpu torchvision==0.21.0+cpu ^
  --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo ERROR: Failed to install PyTorch.
    pause
    exit /b 1
)

echo.
echo Verifying PyTorch install...
python -c "import torch; print('PyTorch version:', torch.__version__)"
echo.

REM ── Other dependencies ────────────────────────────────────────────────────────
echo Installing other dependencies...
python -m pip install easyocr opencv-python pillow numpy pyautogui keyboard requests pywin32 psutil >nul 2>&1

REM ── PyInstaller 6 ─────────────────────────────────────────────────────────────
echo Installing PyInstaller...
python -m pip install --upgrade --force-reinstall pyinstaller
python -m pip install --upgrade setuptools

REM ── Download UPX if not present ───────────────────────────────────────────────
if not exist "upx\upx.exe" (
    echo Downloading UPX compressor...
    mkdir upx >nul 2>&1
    powershell -NoProfile -Command ^
      "Invoke-WebRequest -Uri 'https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip' -OutFile 'upx\upx.zip'"
    if errorlevel 1 (
        echo WARNING: UPX download failed - building without compression.
        set UPX_DIR=
    ) else (
        powershell -NoProfile -Command ^
          "Expand-Archive -Path 'upx\upx.zip' -DestinationPath 'upx\tmp' -Force; Copy-Item 'upx\tmp\upx-4.2.4-win64\upx.exe' 'upx\upx.exe'; Remove-Item 'upx\tmp' -Recurse -Force; Remove-Item 'upx\upx.zip' -Force"
        echo UPX ready.
        set UPX_DIR=upx
    )
) else (
    echo UPX found.
    set UPX_DIR=upx
)

REM ── Write the .spec file via Python (avoids encoding issues with accented paths)
REM    The ´ in the project folder name corrupts when stored in a batch variable.
REM    Python handles it natively — no batch variable ever touches the path.
echo Generating build spec...
python make_spec.py "%UPX_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to generate spec file.
    pause
    exit /b 1
)

REM ── Build ─────────────────────────────────────────────────────────────────────
echo.
echo Building PatoToolBot (PyInstaller 6 + UPX)...
python -m PyInstaller -y PatoToolBot.spec
if errorlevel 1 (
    echo.
    echo ============================================
    echo    BUILD FAILED
    echo ============================================
    echo Check output above for errors.
    call build_env\Scripts\deactivate.bat 2>nul
    pause
    exit /b 1
)

REM ── Result ────────────────────────────────────────────────────────────────────
if exist "dist\PatoToolBot\PatoToolBot.exe" (
    echo.
    echo ============================================
    echo    BUILD SUCCESSFUL!
    echo ============================================
    echo Executable: dist\PatoToolBot\PatoToolBot.exe
    echo.
    echo NOTE: The dist folder will be large (~3-5 GB with CUDA libs).
    echo       This is normal for GPU-enabled torch builds.
    echo.
) else (
    echo.
    echo ============================================
    echo    BUILD FAILED
    echo ============================================
    echo Check build output above for errors.
)

call build_env\Scripts\deactivate.bat 2>nul
pause

:end
exit /b 0
