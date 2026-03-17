@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   露天多商品搜尋工具
echo ========================================
echo.

:: 檢查虛擬環境
if exist venv\Scripts\activate.bat (
    echo 啟動虛擬環境...
    call venv\Scripts\activate.bat
    if errorlevel 1 (
        echo 虛擬環境啟動失敗！
        pause
        exit /b 1
    )
) else (
    echo 虛擬環境不存在，使用系統 Python...
)

:: 安裝依賴
echo.
echo 檢查依賴...
pip install -q -r requirements.txt 2>nul
if errorlevel 1 (
    echo 警告：安裝依賴時發生錯誤，繼續執行...
)

:: 啟動伺服器
echo.
echo 啟動伺服器 (http://127.0.0.1:8000)...
echo 按 Ctrl+C 停止伺服器
echo.

timeout /t 2 /nobreak >nul

:: Windows 10+ 自動打開瀏覽器
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "http://127.0.0.1:8000"
) else if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "http://127.0.0.1:8000"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" "http://127.0.0.1:8000"
) else (
    echo 未檢測到 Chrome，請手動開啟瀏覽器訪問 http://127.0.0.1:8000
)

:: 啟動 uvicorn
uvicorn app:app --reload --host 127.0.0.1 --port 8000

pause
