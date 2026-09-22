"""
发布包打包脚本（uv 一键部署方案）

将项目源码 + vendor/playwright-browsers/（Chromium 二进制）+ vendor/uv/uv.exe
+ pyproject.toml/uv.lock 一起打包成 zip。目标机解压后执行 scripts/deploy.ps1 即可：
uv 自动安装 Python 3.12 并按 uv.lock 秒级同步依赖，无需预装任何环境。

用法:
    python scripts/build_release.py

注意:
    - 打包的 Chromium 二进制与当前操作系统绑定（Windows 打包仅适用于 Windows 部署）
    - vendor/playwright-browsers/、vendor/uv/ 已在 .gitignore 中，不进 git，但本脚本会纳入 zip
    - dist/TrendingServiceSetup.exe 若存在也会一并打包（安装器双击注册 Windows 服务）
"""
import os
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / 'dist'

# 纳入发布包的顶层目录/文件（模板在 src/templates 下，已随 src 一并打包）
INCLUDE_DIRS = ['src', 'scripts', 'vendor']
INCLUDE_FILES = ['config.yaml', 'requirements.txt', 'setup.py', 'README.md',
                 'pyproject.toml', 'uv.lock', '.env.example']

# 排除的模式（路径片段匹配，大小写不敏感）
EXCLUDE_PATTERNS = ['__pycache__', '.pyc', '.git', 'data/', 'logs/', '.venv', 'venv/', 'env/', '.trae', '.workbuddy']


def should_exclude(path: Path) -> bool:
    p = str(path.relative_to(ROOT)).replace('\\', '/').lower()
    return any(pat.lower() in p for pat in EXCLUDE_PATTERNS)


def main():
    if not DIST.exists():
        DIST.mkdir(parents=True)

    date_str = datetime.now().strftime('%Y%m%d')
    zip_path = DIST / f'trending-service-{date_str}.zip'

    # 检查 vendor 浏览器二进制是否存在
    vendor_browser = ROOT / 'vendor' / 'playwright-browsers'
    if not vendor_browser.exists() or not any(vendor_browser.iterdir()):
        print('⚠️  警告: vendor/playwright-browsers/ 为空或不存在。')
        print('   请先执行: python -m playwright install chromium')
        print('   否则发布包部署后仍需联网下载浏览器。')

    # 检查 uv.exe 是否已捆绑（uv 一键部署的核心）
    vendor_uv = ROOT / 'vendor' / 'uv' / 'uv.exe'
    if not vendor_uv.exists():
        print('⚠️  警告: vendor/uv/uv.exe 不存在，目标机部署时需自行安装 uv。')
        print('   请复制 uv.exe 到 vendor/uv/uv.exe 后重新打包。')

    # 检查 uv.lock 是否存在（依赖可复现的关键）
    if not (ROOT / 'uv.lock').exists():
        print('⚠️  警告: uv.lock 不存在，请先执行: uv lock')

    count = 0
    total_size = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 添加目录
        for d in INCLUDE_DIRS:
            dir_path = ROOT / d
            if not dir_path.exists():
                print(f'跳过(不存在): {d}')
                continue
            for file in dir_path.rglob('*'):
                if file.is_file() and not should_exclude(file):
                    arcname = file.relative_to(ROOT)
                    zf.write(file, arcname)
                    count += 1
                    total_size += file.stat().st_size
        # 添加顶层文件
        for f in INCLUDE_FILES:
            file = ROOT / f
            if file.exists():
                zf.write(file, f)
                count += 1
                total_size += file.stat().st_size
        # 添加安装器（双击注册 Windows 服务，需先执行 scripts/build_setup.ps1 编译）
        setup_exe = DIST / 'TrendingServiceSetup.exe'
        if setup_exe.exists():
            zf.write(setup_exe, setup_exe.name)
            count += 1
            total_size += setup_exe.stat().st_size
        else:
            print('提示: dist/TrendingServiceSetup.exe 不存在（可执行 scripts/build_setup.ps1 编译），zip 中将不含安装器')

    zip_mb = zip_path.stat().st_size / 1024 / 1024
    raw_mb = total_size / 1024 / 1024
    print(f'✅ 打包完成: {zip_path}')
    print(f'   文件数: {count}')
    print(f'   原始大小: {raw_mb:.1f} MB | 压缩后: {zip_mb:.1f} MB')
    print()
    print('部署方式（目标机仅需网络，无需预装 Python）:')
    print('  1. 解压 zip 到目标目录')
    print('  2. 执行: powershell -ExecutionPolicy Bypass -File scripts\\deploy.ps1')
    print('     （uv 自动装 Python 3.12 + 按 uv.lock 同步依赖到 venv/ + 初始化 .env）')
    print('  3. 编辑 .env 填入密钥，测试运行: venv\\Scripts\\python.exe -m src.main')
    print('  4. 注册 Windows 服务（推荐）: 以管理员运行 TrendingServiceSetup.exe')
    print('注意: Chromium 二进制与打包机操作系统绑定，跨 OS 部署需重新执行 playwright install')


if __name__ == '__main__':
    main()
