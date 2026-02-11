"""
停止脚本
停止 Trending Service
"""

import sys
import os
import signal
from pathlib import Path

# 添加src目录到Python路径
project_root = Path(__file__).parent.parent
src_dir = project_root / 'src'
sys.path.insert(0, str(src_dir))


def stop_service():
    """停止服务"""
    print("🛑 停止 Trending Service...")

    # 尝试读取PID文件
    pid_file = project_root / 'trending_service.pid'

    if not pid_file.exists():
        print("⚠️  未找到PID文件，服务可能未运行")
        return

    try:
        # 读取PID
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        # 发送停止信号
        os.kill(pid, signal.SIGTERM)
        print(f"✅ 已发送停止信号到进程 {pid}")

        # 删除PID文件
        pid_file.unlink()
        print("✅ PID文件已删除")

    except ProcessLookupError:
        print("⚠️  进程不存在，删除PID文件")
        pid_file.unlink()
    except PermissionError:
        print("❌ 权限不足，无法停止服务")
    except Exception as e:
        print(f"❌ 停止服务失败: {e}")


if __name__ == "__main__":
    stop_service()