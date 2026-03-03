"""
停止脚本
停止 Trending Service
"""

import sys
import os
import signal
import subprocess
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入日志配置
from src.config import LOGGING


def get_logger():
    """获取日志记录器"""
    import logging
    
    # 确保日志目录存在
    log_file = Path(LOGGING['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 配置日志
    logger = logging.getLogger('trending_service_stop')
    logger.setLevel(getattr(logging, LOGGING['level']))
    
    # 文件处理器
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(getattr(logging, LOGGING['level']))
    formatter = logging.Formatter(LOGGING['format'], datefmt=LOGGING['date_format'])
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    return logger


def find_service_processes():
    """查找 Trending Service 相关的进程"""
    processes = []
    try:
        # 使用 tasklist 查找 Python 进程
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
            capture_output=True,
            text=True
        )
        
        # 解析输出
        for line in result.stdout.strip().split('\n')[1:]:  # 跳过标题行
            if line.strip():
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        processes.append(pid)
                    except ValueError:
                        pass
    except Exception as e:
        print(f"查找进程时出错: {e}")
    
    return processes


def stop_service():
    """停止服务"""
    # 获取日志记录器
    logger = get_logger()
    
    print("🛑 停止 Trending Service...")
    logger.info("🛑 停止 Trending Service...")

    # 尝试读取PID文件
    pid_file = project_root / 'trending_service.pid'
    pid = None

    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            print(f"📄 从PID文件读取到进程ID: {pid}")
            logger.info(f"📄 从PID文件读取到进程ID: {pid}")
        except (ValueError, IOError) as e:
            print(f"⚠️  读取PID文件失败: {e}")
            logger.warning(f"⚠️  读取PID文件失败: {e}")
            pid = None
    else:
        print("⚠️  未找到PID文件")
        logger.warning("⚠️  未找到PID文件")

    # 如果找到PID，尝试停止该进程
    if pid:
        try:
            # Windows 上使用 taskkill 停止进程
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                         capture_output=True, check=True)
            print(f"✅ 已停止进程 {pid}")
            logger.info(f"✅ 已停止进程 {pid}")
            
            # 删除PID文件
            if pid_file.exists():
                pid_file.unlink()
                print("✅ PID文件已删除")
                logger.info("✅ PID文件已删除")
            logger.info("🎯 Trending Service 停止完成")
            return
        except subprocess.CalledProcessError:
            print(f"⚠️  进程 {pid} 不存在或无法停止")
            logger.warning(f"⚠️  进程 {pid} 不存在或无法停止")
        except Exception as e:
            print(f"❌ 停止进程 {pid} 失败: {e}")
            logger.error(f"❌ 停止进程 {pid} 失败: {e}")

    # 如果没有PID文件或停止失败，尝试查找并停止所有Python进程
    print("🔍 尝试查找 Trending Service 进程...")
    logger.info("🔍 尝试查找 Trending Service 进程...")
    
    # 查找占用端口 8888 的进程（修正端口号为配置中的端口）
    try:
        result = subprocess.run(
            ['netstat', '-ano', '|', 'findstr', ':8888'],
            capture_output=True,
            text=True,
            shell=True
        )
        
        pids_to_stop = set()
        for line in result.stdout.strip().split('\n'):
            if 'LISTENING' in line:
                parts = line.strip().split()
                if parts:
                    try:
                        listening_pid = int(parts[-1])
                        pids_to_stop.add(listening_pid)
                    except ValueError:
                        pass
        
        if pids_to_stop:
            for p in pids_to_stop:
                try:
                    subprocess.run(['taskkill', '/F', '/PID', str(p)], 
                                 capture_output=True, check=True)
                    print(f"✅ 已停止占用端口8888的进程 {p}")
                    logger.info(f"✅ 已停止占用端口8888的进程 {p}")
                except Exception as e:
                    logger.warning(f"停止进程 {p} 时出错: {e}")
        else:
            print("⚠️  未找到占用端口8888的进程")
            logger.warning("⚠️  未找到占用端口8888的进程")
            
    except Exception as e:
        print(f"查找端口占用时出错: {e}")
        logger.error(f"查找端口占用时出错: {e}")

    # 删除PID文件（如果存在）
    if pid_file.exists():
        try:
            pid_file.unlink()
            print("✅ PID文件已删除")
            logger.info("✅ PID文件已删除")
        except Exception as e:
            logger.warning(f"删除PID文件时出错: {e}")

    print("🎯 停止操作完成")
    logger.info("🎯 停止操作完成")


if __name__ == "__main__":
    stop_service()
