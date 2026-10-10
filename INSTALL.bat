@echo off
REM AgentOS Windows Installer
REM Creates a simple installation with shortcuts

@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo   AgentOS - Multi-Agent AI Software Company
echo   Windows Installer
echo ==========================================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
set "EXE_PATH=%SCRIPT_DIR%dist\AgentOS.exe"
set "INSTALL_DIR=%LOCALAPPDATA%\AgentOS"
set "SHORTCUT_NAME=AgentOS"

echo Checking for executable...
if not exist "%EXE_PATH%" (
    echo ERROR: AgentOS.exe not found at %EXE_PATH%
    echo Please run build.py first to create the executable.
    pause
    exit /b 1
)

echo Found: %EXE_PATH%
echo.

REM Create installation directory
echo Creating installation directory: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy executable and required files
echo Copying files...
xcopy /Y /E "%SCRIPT_DIR%dist\*" "%INSTALL_DIR%\" >nul

REM Create desktop shortcut
echo Creating desktop shortcut...
powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; ^
    $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\%SHORTCUT_NAME%.lnk'); ^
    $Shortcut.TargetPath = '%INSTALL_DIR%\AgentOS.exe'; ^
    $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; ^
    $Shortcut.Description = 'AgentOS - Multi-Agent AI Software Company'; ^
    $Shortcut.Save()"

if %ERRORLEVEL% equ 0 (
    echo Desktop shortcut created successfully.
) else (
    echo Warning: Could not create desktop shortcut (may need admin rights).
)

REM Create Start Menu shortcut
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\AgentOS"
if not exist "%START_MENU%" mkdir "%START_MENU%"
powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; ^
    $Shortcut = $WshShell.CreateShortcut('%START_MENU%\%SHORTCUT_NAME%.lnk'); ^
    $Shortcut.TargetPath = '%INSTALL_DIR%\AgentOS.exe'; ^
    $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; ^
    $Shortcut.Description = 'AgentOS - Multi-Agent AI Software Company'; ^
    $Shortcut.Save()"

if %ERRORLEVEL% equ 0 (
    echo Start Menu shortcut created successfully.
) else (
    echo Warning: Could not create Start Menu shortcut.
)

echo.
echo ==========================================
echo Installation complete!
echo ==========================================
echo.
echo Installed to: %INSTALL_DIR%
echo.
echo You can now run AgentOS from:
echo   - Desktop shortcut
echo   - Start Menu > AgentOS
echo   - Or run: %INSTALL_DIR%\AgentOS.exe
echo.
echo The app will start a local server and open
echo your browser automatically at http://localhost:8000
echo.
pause