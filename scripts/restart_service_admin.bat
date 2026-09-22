@echo off
REM ============================================================
REM 重启 TrendingService（需管理员权限）
REM
REM 背景：该服务由 NSSM 注册为 Windows 服务 "TrendingService"
REM （Session 0，用户会话下 taskkill 会返回 Access denied），
REM 因此加载新代码必须通过服务管理器重启。
REM
REM 用法：右键「以管理员身份运行」
REM ============================================================

setlocal

echo [1/4] 检查服务状态...
sc query TrendingService | findstr /I "STATE"
if errorlevel 1 (
    echo [ERROR] 未找到服务 TrendingService，请确认 NSSM 注册名是否正确。
    pause
    exit /b 1
)

echo.
echo [2/4] 停止服务...
sc stop TrendingService >nul 2>&1
timeout /t 6 /nobreak >nul

echo.
echo [3/4] 启动服务...
sc start TrendingService >nul 2>&1
timeout /t 8 /nobreak >nul

echo.
echo [4/4] 结果确认:
sc query TrendingService | findstr /I "STATE"
netstat -ano -p TCP | findstr ":8888" | findstr "LISTENING"

echo.
echo ============================================================
echo 验证接口是否已加载去重逻辑（期望 raw_total_items 字段存在）:
echo   curl "http://localhost:8888/api/data?start_date=2026-09-16^&end_date=2026-09-19"
echo ============================================================
pause
