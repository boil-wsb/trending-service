"""
定时任务调度器模块
管理定时任务的执行
"""

import time
import webbrowser
import socket
import requests
from threading import Thread, Event
from datetime import datetime
from typing import Callable, Dict, List
from pathlib import Path
import sys

# 添加项目根目录到Python路径（支持直接运行和作为包导入）
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import SCHEDULE, DATA_SOURCES, REPORTS_DIR, BROWSER, SERVER, DATABASE
from src.utils import get_logger, ReportGenerator
from src.db import TrendingDAO
from src.fetchers import (
    GitHubTrendingFetcher, 
    BilibiliHotFetcher, 
    ArxivPapersFetcher,
    HackerNewsFetcher,
    ZhihuHotFetcher
)
from src.analytics import extract_keywords_for_items


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self, logger=None):
        self.logger = logger or get_logger('scheduler')
        self.tasks: Dict[str, Dict] = {}
        self.running = False
        self.stop_event = Event()
        self.scheduler_thread = None

    def add_task(self, name: str, schedule: str, task_func: Callable, enabled: bool = True):
        """
        添加定时任务

        Args:
            name: 任务名称
            schedule: cron表达式 (简化版: "HH:MM" 或 "H * * * *")
            task_func: 任务函数
            enabled: 是否启用
        """
        self.tasks[name] = {
            'schedule': schedule,
            'func': task_func,
            'enabled': enabled,
            'last_run': None
        }
        self.logger.info(f"添加任务: {name} (schedule: {schedule})")

    def remove_task(self, name: str):
        """移除定时任务"""
        if name in self.tasks:
            del self.tasks[name]
            self.logger.info(f"移除任务: {name}")

    def enable_task(self, name: str, enabled: bool = True):
        """启用/禁用任务"""
        if name in self.tasks:
            self.tasks[name]['enabled'] = enabled
            self.logger.info(f"任务 {name} {'启用' if enabled else '禁用'}")

    def start(self):
        """启动调度器"""
        if self.running:
            self.logger.warning("调度器已在运行中")
            return

        self.running = True
        self.stop_event.clear()
        self.scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("定时任务调度器已启动")

    def stop(self):
        """停止调度器"""
        if not self.running:
            return

        self.running = False
        self.stop_event.set()

        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)

        self.logger.info("定时任务调度器已停止")

    def _run_scheduler(self):
        """调度器主循环"""
        self.logger.info("调度器开始运行...")

        while self.running and not self.stop_event.is_set():
            try:
                # 检查每个任务
                for name, task in self.tasks.items():
                    if not task['enabled']:
                        continue

                    # 检查是否应该执行
                    if self._should_run(task):
                        self.logger.info(f"执行任务: {name}")
                        try:
                            task['func']()
                            task['last_run'] = datetime.now()
                        except Exception as e:
                            self.logger.error(f"任务 {name} 执行失败: {e}")

                # 等待一段时间再检查
                time.sleep(60)  # 每分钟检查一次

            except Exception as e:
                self.logger.error(f"调度器运行错误: {e}")
                time.sleep(60)

        self.logger.info("调度器已停止")

    def _should_run(self, task: Dict) -> bool:
        """检查任务是否应该执行"""
        schedule = task['schedule']
        last_run = task['last_run']

        # 简化版cron解析：支持 "HH:MM" 格式
        if ':' in schedule:
            try:
                now = datetime.now()
                target_time = datetime.strptime(schedule, "%H:%M").time()
                current_time = now.time()

                # 检查是否到了执行时间且今天还没执行过
                if (current_time.hour == target_time.hour and
                    current_time.minute == target_time.minute):
                    if last_run is None or last_run.date() != now.date():
                        return True
            except:
                pass

        return False

    def run_task_now(self, name: str):
        """立即执行指定任务"""
        if name in self.tasks:
            self.logger.info(f"立即执行任务: {name}")
            try:
                self.tasks[name]['func']()
                self.tasks[name]['last_run'] = datetime.now()
            except Exception as e:
                self.logger.error(f"任务 {name} 执行失败: {e}")


class TrendingTaskScheduler(TaskScheduler):
    """Trending Service 定时任务调度器"""

    def __init__(self, logger=None):
        self.dao = TrendingDAO(DATABASE['path'])
        super().__init__(logger)
        self._setup_tasks()

    def _setup_tasks(self):
        """设置默认任务"""
        # 添加获取热点任务
        self.add_task(
            name='fetch_trending',
            schedule=SCHEDULE['fetch_trending']['schedule'],
            task_func=self._fetch_all_trending,
            enabled=SCHEDULE['fetch_trending']['enabled']
        )

        # 添加数据清理任务
        self.add_task(
            name='cleanup_old_data',
            schedule='03:00',
            task_func=self._cleanup_old_data,
            enabled=True
        )

    def refresh_data(self, sources: list = None):
        """
        刷新指定数据源的数据
        用于手动刷新或修复数据问题

        Args:
            sources: 要刷新的数据源列表，None 表示刷新所有
        """
        self.logger.info("=" * 60)
        self.logger.info("开始刷新数据...")

        all_items = []

        # 定义所有可用的 fetcher
        fetchers = {
            'github': (GitHubTrendingFetcher, "📈 刷新 GitHub Trending..."),
            'bilibili': (BilibiliHotFetcher, "🎥 刷新 B站热门..."),
            'arxiv': (ArxivPapersFetcher, "📚 刷新 ArXiv论文..."),
            'hackernews': (HackerNewsFetcher, "📰 刷新 HackerNews..."),
            'zhihu': (ZhihuHotFetcher, "🔥 刷新 知乎热榜..."),
        }

        # 如果没有指定数据源，刷新所有启用的
        if sources is None:
            sources = [name for name, config in DATA_SOURCES.items() if config.get('enabled')]

        for source in sources:
            if source not in fetchers:
                self.logger.warning(f"⚠️  未知的数据源: {source}")
                continue

            fetcher_class, message = fetchers[source]

            if not DATA_SOURCES.get(source, {}).get('enabled'):
                self.logger.info(f"⏭️  跳过 {source} (未启用)")
                continue

            try:
                self.logger.info(message)
                fetcher = fetcher_class(logger=self.logger)
                items = fetcher.fetch()
                all_items.extend(items)
                self.logger.info(f"✅ {source} 数据刷新完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 刷新 {source} 数据失败: {e}")

        # 提取关键词
        if all_items:
            self.logger.info("🔍 提取关键词...")
            all_items = extract_keywords_for_items(all_items, top_k=5)

        # 保存到数据库（使用 refresh_items 确保完全更新）
        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        # 生成HTML报告
        try:
            self.logger.info("📄 生成HTML报告...")
            generator = ReportGenerator(REPORTS_DIR)
            report_path = generator.generate_report()
            if report_path and report_path.exists():
                self.logger.info(f"✅ 报告已生成: {report_path}")
            else:
                self.logger.warning("⚠️  报告生成失败")
        except Exception as e:
            self.logger.error(f"❌ 生成报告失败: {e}")

        self.logger.info(f"数据刷新完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

        return len(all_items)

    def _fetch_all_trending(self):
        """获取所有热点信息并保存到数据库"""
        self.logger.info("=" * 60)
        self.logger.info("开始获取所有热点信息...")

        all_items = []

        # 获取GitHub数据
        if DATA_SOURCES.get('github', {}).get('enabled'):
            try:
                self.logger.info("📈 获取 GitHub Trending...")
                github_fetcher = GitHubTrendingFetcher(logger=self.logger)
                items = github_fetcher.fetch_all()
                all_items.extend(items)
                self.logger.info(f"✅ GitHub数据获取完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 获取GitHub数据失败: {e}")

        # 获取B站数据
        if DATA_SOURCES.get('bilibili', {}).get('enabled'):
            try:
                self.logger.info("🎥 获取 B站热门...")
                bilibili_fetcher = BilibiliHotFetcher(logger=self.logger)
                items = bilibili_fetcher.fetch()
                all_items.extend(items)
                self.logger.info(f"✅ B站数据获取完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 获取B站数据失败: {e}")

        # 获取arXiv数据
        if DATA_SOURCES.get('arxiv', {}).get('enabled'):
            try:
                self.logger.info("📚 获取 ArXiv论文...")
                arxiv_fetcher = ArxivPapersFetcher(logger=self.logger)
                items = arxiv_fetcher.fetch()
                all_items.extend(items)
                self.logger.info(f"✅ ArXiv数据获取完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 获取arXiv数据失败: {e}")
        
        # 获取HackerNews数据
        if DATA_SOURCES.get('hackernews', {}).get('enabled'):
            try:
                self.logger.info("📰 获取 HackerNews...")
                hn_fetcher = HackerNewsFetcher(logger=self.logger)
                items = hn_fetcher.fetch()
                all_items.extend(items)
                self.logger.info(f"✅ HackerNews数据获取完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 获取HackerNews数据失败: {e}")
        
        # 获取知乎热榜数据
        if DATA_SOURCES.get('zhihu', {}).get('enabled'):
            try:
                self.logger.info("🔥 获取 知乎热榜...")
                zhihu_fetcher = ZhihuHotFetcher(logger=self.logger)
                items = zhihu_fetcher.fetch()
                all_items.extend(items)
                self.logger.info(f"✅ 知乎热榜数据获取完成: {len(items)} 条")
            except Exception as e:
                self.logger.error(f"❌ 获取知乎热榜数据失败: {e}")

        # 提取关键词
        if all_items:
            self.logger.info("🔍 提取关键词...")
            all_items = extract_keywords_for_items(all_items, top_k=5)
        
        # 保存到数据库（使用 refresh_items 确保数据完全更新）
        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        # 生成HTML报告
        try:
            self.logger.info("📄 生成HTML报告...")
            generator = ReportGenerator(REPORTS_DIR)
            report_path = generator.generate_report()
            if report_path and report_path.exists():
                self.logger.info(f"✅ 报告已生成: {report_path}")
            else:
                self.logger.warning("⚠️  报告生成失败")
        except Exception as e:
            self.logger.error(f"❌ 生成报告失败: {e}")

        self.logger.info(f"热点信息获取完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

    def _cleanup_old_data(self):
        """清理过期数据"""
        try:
            self.logger.info("🧹 开始清理过期数据...")
            days = DATABASE.get('cleanup_days', 30)
            deleted = self.dao.delete_old_data(days)
            self.logger.info(f"✅ 清理完成: 删除 {deleted} 条过期数据")
        except Exception as e:
            self.logger.error(f"❌ 清理数据失败: {e}")

    def _check_service_status(self) -> dict:
        """
        检查服务状态

        Returns:
            服务状态信息
        """
        host = SERVER['host']
        port = SERVER['port']
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

    def _print_service_status(self, status: dict):
        """
        打印服务状态

        Args:
            status: 服务状态信息
        """
        self.logger.info("=" * 60)
        self.logger.info("Trending Service 状态检查")
        self.logger.info("=" * 60)
        self.logger.info(f"检查时间: {status['timestamp']}")
        self.logger.info(f"服务地址: {status['url']}")
        self.logger.info(f"报告地址: {status['report_url']}")
        self.logger.info("-" * 60)

        # 打印各项检查结果
        for check_name, check_result in status['checks'].items():
            if isinstance(check_result, bool):
                icon = "✅" if check_result else "❌"
                self.logger.info(f"{icon} {check_name.upper()}: {'正常' if check_result else '异常'}")
            elif isinstance(check_result, int):
                self.logger.info(f"📊 {check_name.upper()}: {check_result}")
            elif isinstance(check_result, str) and not check_name.endswith('_error'):
                self.logger.info(f"ℹ️  {check_name.upper()}: {check_result}")

        self.logger.info("-" * 60)

        if status['running']:
            self.logger.info("🎉 服务运行正常!")
        else:
            self.logger.warning("⚠️  服务可能未正常运行")

        self.logger.info("=" * 60)

    def check_and_preview(self):
        """检查服务状态并打开浏览器预览"""
        self.logger.info("🔍 检查服务状态...")

        status = self._check_service_status()
        self._print_service_status(status)

        if status['running'] and BROWSER['auto_open']:
            self.logger.info(f"🌐 打开浏览器预览: {status['report_url']}")
            try:
                webbrowser.open(status['report_url'])
                self.logger.info("✅ 浏览器已打开")
            except Exception as e:
                self.logger.error(f"❌ 打开浏览器失败: {e}")

        return status
