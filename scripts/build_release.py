"""
发布包打包脚本（方案 B：发布包免下载）

将项目源码 + vendor/playwright-browsers/（Chromium 二进制）一起打包成 zip，
部署时解压即用，无需联网执行 `playwright install`。

用法:
    python scripts/build_release.py

注意:
    - 打包的 Chromium 二进制与当前操作系统绑定（Windows 打包仅适用于 Windows 部署）
    - vendor/playwright-browsers/ 已在 .gitignore 中，不会进入 git，但本脚本会将其纳入 zip
"""
import os
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / 'dist'

# 纳入发布包的顶层目录/文件（模板在 src/templates 下，已随 src 一并打包）
INCLUDE_DIRS = ['src', 'scripts', 'vendor']
INCLUDE_FILES = ['config.yaml', 'requirements.txt', 'setup.py', 'README.md']

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

    zip_mb = zip_path.stat().st_size / 1024 / 1024
    raw_mb = total_size / 1024 / 1024
    print(f'✅ 打包完成: {zip_path}')
    print(f'   文件数: {count}')
    print(f'   原始大小: {raw_mb:.1f} MB | 压缩后: {zip_mb:.1f} MB')
    print()
    print('部署方式:')
    print('  1. 解压 zip 到目标目录')
    print('  2. pip install -r requirements.txt')
    print('  3. python -m src.main  (或 python scripts/start_service.py)')
    print('注意: Chromium 二进制与打包机操作系统绑定，跨 OS 部署需重新执行 playwright install')


if __name__ == '__main__':
    main()
