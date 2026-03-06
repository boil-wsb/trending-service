"""
启动脚本
启动 Trending Service (后台运行模式)
"""

import sys
import os
import subprocess
import time
import socket
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


_logger_instance = None

def get_logger():
    """获取日志记录器（单例模式）"""
    global _logger_instance
    import logging

    if _logger_instance is not None:
        return _logger_instance

    # 确保日志目录存在
    log_file = Path(LOGGING['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 配置日志
    logger = logging.getLogger('trending_service_start')
    logger.setLevel(getattr(logging, LOGGING['level']))

    # 清除现有处理器（防止重复）
    logger.handlers = []

    # 文件处理器
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(getattr(logging, LOGGING['level']))
    formatter = logging.Formatter(LOGGING['format'], datefmt=LOGGING['date_format'])
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    _logger_instance = logger
    return logger


def check_port_open(host, port, timeout=1):
    """检查端口是否开放"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def wait_for_service(host, port, pid, max_wait=30):
    """
    等待服务启动并健康检查

    Args:
        host: 服务器地址
        port: 服务器端口
        pid: 进程ID
        max_wait: 最大等待秒数

    Returns:
        (success, message)
    """
    logger = get_logger()
    start_time = time.time()
    check_interval = 0.5

    logger.info(f"⏳ 等待服务启动 (最多等待 {max_wait} 秒)...")

    while time.time() - start_time < max_wait:
        # 检查端口是否开放（主要检查项）
        if check_port_open(host, port):
            return True, f"服务已成功启动并在端口 {port} 监听"

        time.sleep(check_interval)

    # 超时后再次检查端口，可能服务刚好启动
    if check_port_open(host, port):
        return True, f"服务已成功启动并在端口 {port} 监听"

    return False, f"等待超时 ({max_wait} 秒)，服务可能未正常启动"


def start_service_background():
    """后台启动服务"""
    # 获取日志记录器
    logger = get_logger()

    pid_file = project_root / 'trending_service.pid'

    logger.info("=" * 60)
    logger.info("🚀 开始启动 Trending Service...")
    logger.info("=" * 60)

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
                # 检查端口是否开放
                if check_port_open(SERVER['host'], SERVER['port']):
                    msg = f"⚠️  服务已在运行中 (PID: {pid})"
                    print(msg)
                    logger.warning(msg)
                    return
                else:
                    logger.warning(f"PID文件存在但服务未响应，删除旧PID文件")
                    pid_file.unlink()
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

    # 使用相对路径显示
    try:
        python_exe_rel = Path(python_exe).relative_to(project_root)
    except ValueError:
        python_exe_rel = python_exe
    try:
        main_script_rel = main_script.relative_to(project_root)
    except ValueError:
        main_script_rel = main_script

    logger.info(f"🐍 Python解释器: {python_exe_rel}")
    logger.info(f"📜 启动脚本: {main_script_rel}")
    logger.info(f"🌐 服务地址: http://{SERVER['host']}:{SERVER['port']}")

    # 后台启动进程
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        # 使用 DETACHED_PROCESS 让子进程独立运行
        # 同时将输出重定向到日志文件以便调试
        log_dir = Path(LOGGING['file']).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = log_dir / 'service_stdout.log'
        stderr_log = log_dir / 'service_stderr.log'

        process = subprocess.Popen(
            [python_exe, str(main_script)],
            cwd=str(project_root),
            env=env,
            startupinfo=startupinfo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

        logger.info(f"📦 子进程已创建 (PID: {process.pid})")

        # 等待服务启动
        success, message = wait_for_service(SERVER['host'], SERVER['port'], process.pid)

        if success:
            msg = f"✅ Trending Service 已启动 (PID: {process.pid})"
            print(msg)
            logger.info(msg)
            logger.info(f"📝 PID文件: {pid_file}")
            logger.info(f"🌐 访问地址: http://{SERVER['host']}:{SERVER['port']}/report.html")
            print(f"📝 PID文件: {pid_file}")
            print(f"🌐 访问地址: http://{SERVER['host']}:{SERVER['port']}/report.html")
            print(f"\n使用以下命令停止服务:")
            print(f"  python scripts/stop_service.py")
            logger.info("=" * 60)
            logger.info("🎉 服务启动成功！")
            logger.info("=" * 60)
        else:
            error_msg = f"❌ 服务启动失败: {message}"
            print(error_msg)
            logger.error(error_msg)

            # 尝试终止进程
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, process.pid)
                if handle != 0:
                    kernel32.TerminateProcess(handle, 1)
                    kernel32.CloseHandle(handle)
                    logger.info(f"已终止进程 {process.pid}")
            except:
                pass

            raise RuntimeError(message)

    except Exception as e:
        error_msg = f"❌ 启动服务失败: {e}"
        print(error_msg)
        logger.error(error_msg)
        raise


if __name__ == "__main__":
    try:
        start_service_background()
    except Exception as e:
        print(f"\n启动失败，请检查日志: {LOGGING['file']}")
        sys.exit(1)
