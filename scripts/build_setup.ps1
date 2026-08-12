<#
.SYNOPSIS
    编译 TrendingServiceSetup.exe（Windows 服务安装/卸载程序）
.DESCRIPTION
    使用 Windows 内置 .NET Framework 编译器 (csc.exe)，无需安装任何额外工具。
    生成的 exe 支持 GUI 和命令行两种模式。
#>

$projectRoot = Resolve-Path "$PSScriptRoot\.."
$sourceFile = "$projectRoot\scripts\setup\SetupForm.cs"
$outputDir = "$projectRoot\dist"
$outputExe = "$outputDir\TrendingServiceSetup.exe"

# csc.exe 路径（Windows 内置）
$cscPaths = @(
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $null
foreach ($p in $cscPaths) {
    if (Test-Path $p) { $csc = $p; break }
}
if (-not $csc) {
    Write-Host "ERROR: 未找到 csc.exe，请检查 .NET Framework 是否已安装" -ForegroundColor Red
    exit 1
}

Write-Host "编译器: $csc" -ForegroundColor Cyan
Write-Host "源码:   $sourceFile" -ForegroundColor Cyan
Write-Host "输出:   $outputExe" -ForegroundColor Cyan
Write-Host ""

# 创建输出目录
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }

# 编译参数
# /target:winexe  - Windows 应用程序（不弹出控制台窗口）
# /optimize+      - 启用优化
# /warn:0         - 关闭警告（减少噪音）
$references = @(
    "/reference:System.Windows.Forms.dll",
    "/reference:System.Drawing.dll",
    "/reference:System.ServiceProcess.dll",
    "/reference:Microsoft.CSharp.dll"
)

$args = @(
    "/target:winexe",
    "/optimize+",
    "/warn:0",
    "/nologo",
    "/win32icon:$projectRoot\scripts\setup\app.ico",
    $references,
    "/out:`"$outputExe`"",
    "`"$sourceFile`""
) | Where-Object { $_ -ne $null }

# 如果没有图标文件，移除 win32icon 参数
if (-not (Test-Path "$projectRoot\scripts\setup\app.ico")) {
    $args = $args | Where-Object { $_ -notlike "/win32icon:*" }
}

Write-Host "执行编译..." -ForegroundColor Yellow
& $csc $args

if ($LASTEXITCODE -eq 0 -and (Test-Path $outputExe)) {
    $size = [math]::Round((Get-Item $outputExe).Length / 1KB, 1)
    Write-Host ""
    Write-Host "✅ 编译成功！" -ForegroundColor Green
    Write-Host "   输出: $outputExe" -ForegroundColor Green
    Write-Host "   大小: ${size} KB" -ForegroundColor Green
    Write-Host ""
    Write-Host "使用方式:" -ForegroundColor Cyan
    Write-Host "  GUI 模式:    双击 TrendingServiceSetup.exe" -ForegroundColor White
    Write-Host "  命令行安装:  TrendingServiceSetup.exe -install `"D:\项目路径`"" -ForegroundColor White
    Write-Host "  命令行卸载:  TrendingServiceSetup.exe -uninstall" -ForegroundColor White
    Write-Host "  查看状态:    TrendingServiceSetup.exe -status" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ 编译失败 (exit code: $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
