"""
检查脚本
检查 Trending Service 状态并打开浏览器预览
"""

import sys
import os
import webbrowser
import requests
import socket
from pathlib import Path
from datetime import datetime

# 添加src目录到Python路径
project_root = Path(__file__).parent.parent
src_dir = project_root / 'src'
sys.path.insert(0, str(src_dir))

from config import SERVER, BROWSER


def check_service_status(host: str = None, port: int = None) -> dict:
    """
    检查服务状态

    Args:
        host: 服务器地址
        port: 服务器端口

    Returns:
        服务状态信息
    """
    host = host or SERVER['host']
    port = port or SERVER['port']
    url = f"http://{host}:{port}"
    report_url = f"{url}/report.html"

    status = {
        'running': False,
        'url': url,
        'report_url': report_url,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'checks': {}
    }

    # 检查端口是否开放
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        status['checks']['port'] = result == 0
        sock.close()
    except Exception as e:
        status['checks']['port'] = False
        status['checks']['port_error'] = str(e)

    # 检查HTTP服务
    try:
        response = requests.get(url, timeout=5)
        status['checks']['http'] = response.status_code == 200
        status['checks']['http_status'] = response.status_code
    except Exception as e:
        status['checks']['http'] = False
        status['checks']['http_error'] = str(e)

    # 检查报告页面
    try:
        response = requests.get(report_url, timeout=5)
        status['checks']['report'] = response.status_code == 200
        status['checks']['report_status'] = response.status_code
        status['checks']['report_content'] = 'html' in response.headers.get('content-type', '')
    except Exception as e:
        status['checks']['report'] = False
        status['checks']['report_error'] = str(e)

    # 综合判断服务是否运行
    status['running'] = (
        status['checks'].get('port', False) and
        status['checks'].get('http', False) and
        status['checks'].get('report', False)
    )

    return status


def print_status(status: dict):
    """
    打印服务状态

    Args:
        status: 服务状态信息
    """
    print("=" * 60)
    print("Trending Service 状态检查")
    print("=" * 60)
    print(f"检查时间: {status['timestamp']}")
    print(f"服务地址: {status['url']}")
    print(f"报告地址: {status['report_url']}")
    print("-" * 60)

    # 打印各项检查结果
    checks = status['checks']
    for check_name, check_result in checks.items():
        if check_name.endswith('_error'):
            continue

        icon = "✅" if check_result else "❌"
        print(f"{icon} {check_name.upper()}: {'正常' if check_result else '异常'}")

        # 打印错误信息
        error_key = f"{check_name}_error"
        if error_key in checks:
            print(f"   错误: {checks[error_key]}")

    print("-" * 60)

    # 总体状态
    if status['running']:
        print("🎉 服务运行正常!")
    else:
        print("⚠️  服务未正常运行，请检查服务状态")

    print("=" * 60)


def check_and_preview(host: str = None, port: int = None, auto_open: bool = True):
    """
    检查服务并打开浏览器预览

    Args:
        host: 服务器地址
        port: 服务器端口
        auto_open: 是否自动打开浏览器
    """
    host = host or SERVER['host']
    port = port or SERVER['port']

    print("🔍 检查 Trending Service 状态...")

    # 检查服务状态
    status = check_service_status(host, port)

    # 打印状态
    print_status(status)

    # 如果服务运行正常，打开浏览器
    if status['running'] and auto_open:
        print(f"\n🌐 打开浏览器预览: {status['report_url']}")
        try:
            webbrowser.open(status['report_url'])
            print("✅ 浏览器已打开")
        except Exception as e:
            print(f"❌ 打开浏览器失败: {e}")
    else:
        print("\n⚠️  服务未正常运行，无法打开浏览器预览")
        print(f"💡 提示: 请先启动服务: python {project_root}/src/main.py")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='检查 Trending Service 状态并打开浏览器预览')
    parser.add_argument('--host', default=SERVER['host'], help='服务器地址')
    parser.add_argument('--port', type=int, default=SERVER['port'], help='服务器端口')
    parser.add_argument('--no-open', action='store_true', help='不自动打开浏览器')

    args = parser.parse_args()

    check_and_preview(
        host=args.host,
        port=args.port,
        auto_open=not args.no_open
    )


if __name__ == "__main__":
    main()