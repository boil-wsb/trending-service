"""
Trending Service 主程序
集成HTTP服务器和定时任务调度器
"""

import argparse
import os
import sys
import signal
import threading
import time
from pathlib import Path

# 添加项目根目录到Python路径（支持直接运行和作为包导入）
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import SERVER, SCHEDULE, LOGGING
from src.utils import get_logger, setup_logger
from src.server import TrendingServer
from src.scheduler import TrendingTaskScheduler


class TrendingService:
    """Trending Service 主服务"""

    def __init__(self, host: str = None, port: int = None, debug: bool = False, pid_file: str = None):
        self.host = host or SERVER['host']
        self.port = port or SERVER['port']
        self.debug = debug
        self.pid_file = pid_file
        self.logger = None
        self.server = None
        self.scheduler = None
        self.running = False

    def start(self):
        """启动服务"""
        try:
            # 设置日志
            self.logger = setup_logger('trending_service')
            self.logger.info("🚀 启动 Trending Service...")

            # 创建服务器
            self.server = TrendingServer(
                host=self.host,
                port=self.port,
                logger=self.logger
            )

            # 创建调度器
            self.scheduler = TrendingTaskScheduler(logger=self.logger)

            # 启动服务器
            self.server.start(blocking=False)
            self.logger.info("✅ HTTP服务器已启动")

            # 启动调度器
            self.scheduler.start()
            self.logger.info("✅ 定时任务调度器已启动")

            self.running = True

            # 启动后在后台异步获取热点信息（不阻塞启动流程）
            import threading
            def fetch_initial_data():
                try:
                    self.logger.info("🔄 正在后台获取热点信息...")
                    self.scheduler.run_task_now('fetch_trending')
                    self.logger.info("✅ 首次热点信息获取完成")
                except Exception as e:
                    self.logger.error(f"❌ 首次热点信息获取失败: {e}")

            threading.Thread(target=fetch_initial_data, daemon=True).start()

            # 写入PID文件
            if self.pid_file:
                try:
                    with open(self.pid_file, 'w') as f:
                        f.write(str(os.getpid()))
                    self.logger.info(f"📝 PID文件已写入: {self.pid_file} (PID: {os.getpid()})")
                except Exception as e:
                    self.logger.error(f"❌ 写入PID文件失败: {e}")

            self.logger.info(f"🎉 Trending Service 启动成功!")
            self.logger.info(f"🌐 访问地址: http://{self.host}:{self.port}/report.html")

            # 保持运行
            self._keep_running()

        except KeyboardInterrupt:
            self.logger.info("\n🛑 收到停止信号...")
            self.stop()
        except Exception as e:
            self.logger.error(f"启动服务失败: {e}")
            self.stop()

    def stop(self):
        """停止服务"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止 Trending Service...")

        # 停止调度器
        if self.scheduler:
            self.scheduler.stop()
            self.logger.info("✅ 定时任务调度器已停止")

        # 停止服务器
        if self.server:
            self.server.stop()
            self.logger.info("✅ HTTP服务器已停止")

        self.running = False

        # 删除PID文件
        if self.pid_file and os.path.exists(self.pid_file):
            os.remove(self.pid_file)
            self.logger.info("📝 PID文件已删除")

        self.logger.info("🎯 Trending Service 已完全停止")

    def _keep_running(self):
        """保持服务运行"""
        while self.running:
            time.sleep(1)

    def run_task_now(self, task_name: str):
        """立即执行指定任务"""
        if self.scheduler:
            self.scheduler.run_task_now(task_name)
        else:
            self.logger.error("调度器未启动")

    def get_status(self) -> dict:
        """获取服务状态"""
        return {
            'running': self.running,
            'server': {
                'running': self.server.is_running() if self.server else False,
                'host': self.host,
                'port': self.port
            },
            'scheduler': {
                'running': self.scheduler.running if self.scheduler else False,
                'tasks': list(self.scheduler.tasks.keys()) if self.scheduler else []
            } if self.scheduler else {}
        }


def signal_handler(signum, frame):
    """信号处理器"""
    global service
    if service:
        service.stop()
    sys.exit(0)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Trending Service - 热点信息采集服务')
    parser.add_argument('--host', default=SERVER['host'], help='服务器地址')
    parser.add_argument('--port', type=int, default=SERVER['port'], help='服务器端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    parser.add_argument('--run-task', choices=['fetch_trending'],
                       help='立即执行指定任务')
    parser.add_argument('--refresh', nargs='*', metavar='SOURCE',
                       help='刷新指定数据源的数据 (不指定则刷新所有)')
    parser.add_argument('--status', action='store_true', help='查看服务状态')
    
    args = parser.parse_args()

    # 全局服务实例
    global service
    pid_file = str(project_root / 'trending_service.pid')
    service = TrendingService(host=args.host, port=args.port, debug=args.debug, pid_file=pid_file)

    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.status:
        # 查看服务状态
        status = service.get_status()
        print("Trending Service 状态:")
        print(f"运行状态: {'运行中' if status['running'] else '已停止'}")
        print(f"HTTP服务器: {'运行中' if status['server']['running'] else '已停止'}")
        print(f"服务器地址: http://{status['server']['host']}:{status['server']['port']}")
        if status['scheduler']:
            print(f"调度器: {'运行中' if status['scheduler']['running'] else '已停止'}")
            print(f"任务列表: {', '.join(status['scheduler']['tasks'])}")
    elif args.run_task:
        # 立即执行任务
        print(f"🚀 立即执行任务: {args.run_task}")
        service.run_task_now(args.run_task)
        print("✅ 任务执行完成")
    elif args.refresh is not None:
        # 刷新数据
        sources = args.refresh if args.refresh else None
        if sources:
            print(f"🔄 刷新数据源: {', '.join(sources)}")
        else:
            print("🔄 刷新所有数据源")
        # 创建临时调度器来执行刷新
        from src.utils import setup_logger
        logger = setup_logger('trending_service')
        scheduler = TrendingTaskScheduler(logger=logger)
        scheduler.refresh_data(sources)
        print("✅ 数据刷新完成")
    else:
        # 启动服务
        service.start()


if __name__ == "__main__":
    main()