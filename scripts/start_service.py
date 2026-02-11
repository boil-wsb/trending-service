"""
启动脚本
启动 Trending Service
"""

import sys
import os
from pathlib import Path

# 设置UTF-8编码环境变量
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.main import TrendingService


def start_service():
    """启动服务"""
    print("启动 Trending Service...")

    try:
        service = TrendingService()
        service.start()
    except KeyboardInterrupt:
        print("\n收到停止信号...")
        service.stop()
    except Exception as e:
        print(f"启动服务失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_service()
