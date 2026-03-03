"""
启动脚本
启动 Trending Service (后台运行模式)
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# 设置UTF-8编码环境变量
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入配置
from src.config import SERVER, LOGGING


def get_logger():
    """获取日志记录器"""
    import logging

    # 确保日志目录存在
    log_file = Path(LOGGING['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 配置日志
    logger = logging.getLogger('trending_service_start')
    logger.setLevel(getattr(logging, LOGGING['level']))

    # 文件处理器
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(getattr(logging, LOGGING['level']))
    formatter = logging.Formatter(LOGGING['format'], datefmt=LOGGING['date_format'])
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def start_service_background():
    """后台启动服务"""
    # 获取日志记录器
    logger = get_logger()

    pid_file = project_root / 'trending_service.pid'

    logger.info("🚀 开始启动 Trending Service...")

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
                msg = f"⚠️  服务已在运行中 (PID: {pid})"
                print(msg)
                logger.warning(msg)
                return
            else:
                # 进程不存在，删除旧PID文件
                pid_file.unlink()
                logger.info("📝 删除旧的PID文件")
        except (ValueError, OSError) as e:
            # 进程不存在或读取失败，删除旧PID文件
            logger.warning(f"⚠️  读取PID文件失败: {e}")
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

    logger.info(f"🐍 Python解释器: {python_exe}")
    logger.info(f"📜 启动脚本: {main_script}")

    # 后台启动进程
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        process = subprocess.Popen(
            [python_exe, str(main_script)],
            cwd=str(project_root),
            env=env,
            startupinfo=startupinfo,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

        msg = f"✅ Trending Service 已启动 (PID: {process.pid})"
        print(msg)
        logger.info(msg)
        logger.info(f"📝 PID文件: {pid_file}")
        logger.info(f"🌐 访问地址: http://{SERVER['host']}:{SERVER['port']}/report.html")
        print(f"📝 PID文件: {pid_file}")
        print(f"🌐 访问地址: http://{SERVER['host']}:{SERVER['port']}/report.html")
        print(f"\n使用以下命令停止服务:")
        print(f"  python scripts/stop_service.py")
    except Exception as e:
        error_msg = f"❌ 启动服务失败: {e}"
        print(error_msg)
        logger.error(error_msg)
        raise


if __name__ == "__main__":
    start_service_background()
