"""
启动脚本
启动 Trending Service (后台运行模式)
"""

import sys
import os
import subprocess
from pathlib import Path

# 设置UTF-8编码环境变量
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def start_service_background():
    """后台启动服务"""
    pid_file = project_root / 'trending_service.pid'

    # 检查是否已运行
    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            # 检查进程是否存在 (Windows)
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle != 0:
                kernel32.CloseHandle(handle)
                print(f"⚠️  服务已在运行中 (PID: {pid})")
                return
            else:
                # 进程不存在，删除旧PID文件
                pid_file.unlink()
        except (ValueError, OSError):
            # 进程不存在或读取失败，删除旧PID文件
            try:
                pid_file.unlink()
            except:
                pass

    # 获取 Python 解释器路径
    python_exe = sys.executable

    # 启动脚本路径
    main_script = project_root / 'src' / 'main.py'

    # 设置环境变量，确保子进程知道项目根目录
    env = os.environ.copy()
    env['TRENDING_SERVICE_ROOT'] = str(project_root)

    # 后台启动进程
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    process = subprocess.Popen(
        [python_exe, str(main_script)],
        cwd=str(project_root),
        env=env,
        startupinfo=startupinfo,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    )

    print(f"✅ Trending Service 已启动 (PID: {process.pid})")
    print(f"📝 PID文件: {pid_file}")
    print(f"🌐 访问地址: http://localhost:8000/report.html")
    print(f"\n使用以下命令停止服务:")
    print(f"  python scripts/stop_service.py")


if __name__ == "__main__":
    start_service_background()
