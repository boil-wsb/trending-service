"""
Trending Service 主程序
集成HTTP服务器和定时任务调度器
"""

# ===== 诊断基础设施（必须在所有其他 import 之前启用）=====
# 根因：服务多次突然中断且无任何日志/异常堆栈，第一性原理分析指向 C 扩展段错误。
# faulthandler 在段错误时打印 Python 回溯到 stderr，是定位段错误根因的唯一手段。
import faulthandler
import sys as _sys
from pathlib import Path as _Path

# 1. 启用主线程段错误回溯（输出到 stderr，与 service_stderr.log 对齐）
faulthandler.enable()

# 2. 段错误专用日志文件（与主日志同目录，便于排查时一并查看）
_crash_log = _Path(__file__).parent.parent / 'data' / 'logs' / 'crash_traceback.log'
_crash_log.parent.mkdir(parents=True, exist_ok=True)
_crash_fp = open(_crash_log, 'a', encoding='utf-8')
faulthandler.enable(file=_crash_fp)

# 3. 每 300 秒转储所有线程堆栈到 crash 文件，捕获死锁/挂起场景
#    （重复调用会替换前一个定时器，不会堆积）
faulthandler.dump_traceback_later(timeout=300, repeat=True, file=_crash_fp, exit=False)

# 4. 捕获子线程未处理异常（默认子线程异常只打印到 stderr，进程可能静默退出）
import threading as _threading
_orig_init = _threading.Thread.__init__

def _patched_thread_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    _orig_run = self.run

    def _wrapped_run(*args, **kw):
        try:
            return _orig_run(*args, **kw)
        except SystemExit:
            raise
        except BaseException as e:
            import traceback as _tb
            msg = f"[threading-excepthook] 线程 {self.name} 未捕获异常: {e}\n" + ''.join(_tb.format_exception(type(e), e, e.__traceback__))
            try:
                _crash_fp.write(msg + '\n')
                _crash_fp.flush()
            except Exception:
                pass
            # 同时写到主日志（通过 stderr，会被 service_stderr.log 捕获）
            print(msg, file=_sys.stderr, flush=True)
            raise

    self.run = _wrapped_run

_threading.Thread.__init__ = _patched_thread_init
# 5. stderr 强制行缓冲：start_service.py 将 stderr 重定向到文件，
#    Python 文本模式默认块缓冲，段错误时缓冲区丢失。改为行缓冲确保落盘。
try:
    _sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    # Python < 3.7 或 stderr 不支持 reconfigure（如已关闭）
    pass

# ===== 诊断基础设施结束 =====

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
            # 优化：先检查数据库是否存在上一个运行周期的数据，存在则跳过
            import threading
            from datetime import datetime, timedelta

            def _parse_schedule_hours(cron_expr: str) -> int:
                """从 cron 表达式估算调度周期（小时），用于判断是否跳过启动获取"""
                try:
                    parts = cron_expr.strip().split()
                    if len(parts) != 5:
                        return 0
                    hour_part = parts[1]
                    if hour_part.startswith('*/'):
                        return int(hour_part[2:])
                    if hour_part.isdigit():
                        return 24  # 每天一次
                    return 0
                except Exception:
                    return 0

            def fetch_initial_data():
                try:
                    from src.config import SCHEDULE as _SCHEDULE, DATABASE as _DATABASE
                    from src.db import TrendingDAO

                    # 检查数据库中各数据源的最新抓取时间
                    cron = _SCHEDULE.get('fetch_trending', {}).get('schedule', '0 */8 * * *')
                    cycle_hours = _parse_schedule_hours(cron) or 8
                    skip_threshold = timedelta(hours=cycle_hours - 1)  # 留 1 小时缓冲

                    try:
                        dao = TrendingDAO(_DATABASE['path'])
                        fetch_times = dao.get_source_fetch_times()
                    except Exception as e:
                        self.logger.warning(f"查询数据抓取时间失败，将执行获取: {e}")
                        fetch_times = {}

                    now = datetime.now()
                    if fetch_times:
                        latest_overall = max(t for t in fetch_times.values() if t) if any(fetch_times.values()) else None
                        if latest_overall and (now - latest_overall) < skip_threshold:
                            self.logger.info(
                                f"⏭️  数据库已有上一个运行周期内的数据"
                                f"（最新抓取: {latest_overall.strftime('%Y-%m-%d %H:%M')}，"
                                f"距今 {(now - latest_overall).total_seconds() / 3600:.1f} 小时），跳过启动获取"
                            )
                            self.logger.info("✅ 首次热点信息获取完成（跳过）")
                            return

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
