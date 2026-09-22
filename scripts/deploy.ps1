# Trending Service 一键部署脚本（uv 方案）
# 用法: 在项目根目录执行
#   powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
# 功能: 定位 uv -> 自动安装 Python 3.12 -> 按 uv.lock 同步依赖到 venv/
#       -> 安装 Playwright Chromium（缺失时）-> 初始化 .env
# 说明: 目标机无需预装 Python/依赖，仅需网络可达 PyPI 镜像（脚本内置清华源）

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== Trending Service 一键部署 ===" -ForegroundColor Cyan
Write-Host "项目目录: $ProjectRoot"

# 1. 定位 uv.exe（优先捆绑版本，其次 PATH）
$uvExe = Join-Path $ProjectRoot 'vendor\uv\uv.exe'
if (-not (Test-Path $uvExe)) {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { $uvExe = $cmd.Source }
}
if (-not (Test-Path $uvExe)) {
    Write-Host "[错误] 未找到 uv.exe" -ForegroundColor Red
    Write-Host "  方式1: 将 uv.exe 放到 vendor\uv\uv.exe"
    Write-Host "  方式2: 安装 uv 后重试  powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
    exit 1
}
Write-Host "[1/5] uv: $uvExe"

# 2. 安装 Python 3.12（已装则跳过；失败不中断，可能系统已有可用的 3.12）
Write-Host "[2/5] 检查 Python 3.12 ..."
& $uvExe python install 3.12
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [警告] uv 自动安装 Python 失败（可能网络受限），将尝试使用系统已装的 Python 3.12" -ForegroundColor Yellow
}

# 3. 同步依赖到 venv/（UV_PROJECT_ENVIRONMENT 必须为 venv —— 安装器硬编码 venv\Scripts\pythonw.exe）
Write-Host "[3/5] 同步依赖（uv sync --frozen，来源: uv.lock + 清华镜像）..."
$env:UV_PROJECT_ENVIRONMENT = 'venv'
& $uvExe sync --frozen
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 依赖同步失败。若提示 lock 过期，请在有网环境执行: uv lock" -ForegroundColor Red
    exit 1
}

# 验证虚拟环境
$pythonExe = Join-Path $ProjectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    Write-Host "[错误] venv\Scripts\python.exe 未生成" -ForegroundColor Red
    exit 1
}

# 4. 安装 Playwright Chromium（发布包已内置浏览器则自动跳过；GitHub 克隆场景必需）
$pwDir = Join-Path $ProjectRoot 'vendor\playwright-browsers'
if (-not (Test-Path $pwDir) -or -not (Get-ChildItem $pwDir -ErrorAction SilentlyContinue)) {
    Write-Host "[4/5] 安装 Playwright Chromium（知乎/抖音数据源必需）..."
    & $pythonExe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [警告] Chromium 安装失败，知乎/抖音数据源将不可用；可稍后手动执行:" -ForegroundColor Yellow
        Write-Host "    venv\Scripts\python.exe -m playwright install chromium"
    }
} else {
    Write-Host "[4/5] Playwright Chromium 已内置，跳过"
}

# 5. 初始化 .env（不存在时从模板复制）
$envFile = Join-Path $ProjectRoot '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $ProjectRoot '.env.example') $envFile
    Write-Host "[5/5] 已生成 .env（请编辑填入 API Key 等敏感配置）"
} else {
    Write-Host "[5/5] .env 已存在，跳过"
}
$ver = & $pythonExe --version

Write-Host ""
Write-Host "=== 部署完成 ===" -ForegroundColor Green
Write-Host "Python: $ver"
Write-Host "后续步骤:"
Write-Host "  1. 编辑 .env 填入密钥（LLM_STATS_API_KEY 等）"
Write-Host "  2. 测试运行: venv\Scripts\python.exe -m src.main"
Write-Host "  3. 注册 Windows 服务（推荐）: 以管理员运行 dist\TrendingServiceSetup.exe"
