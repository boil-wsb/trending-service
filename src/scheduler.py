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
from typing import Callable, Dict, List, Optional
from pathlib import Path
import sys

# 添加项目根目录到Python路径（支持直接运行和作为包导入）
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import SCHEDULE, DATA_SOURCES, REPORTS_DIR, BROWSER, SERVER, DATABASE, is_time_to_run
from src.utils import get_logger, ReportGenerator
from src.utils.retry_manager import RetryManager, FetchResult, FetchStatus, RetryConfig
from src.db import TrendingDAO, FetchFailureDAO
from src.fetchers import (
    GitHubTrendingFetcher, 
    BilibiliHotFetcher, 
    ArxivPapersFetcher,
    HackerNewsFetcher,
    ZhihuHotFetcher,
    WeiboHotFetcher,
    DouyinHotFetcher
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

        # 尝试计算并显示下次执行时间
        try:
            from src.config import get_next_run_time
            next_run = get_next_run_time(schedule)
            self.logger.info(f"  下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            self.logger.warning(f"  无法计算下次执行时间: {e}")

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

        # 使用配置中的 is_time_to_run 函数检查是否应该执行
        # 支持简单格式 "HH:MM" 和 cron 表达式 "0 */8 * * *"
        try:
            from src.config import is_time_to_run

            # 构建调度配置
            schedule_config = {
                'schedule': schedule,
                'enabled': True,
                'timezone': 'Asia/Shanghai'
            }

            if is_time_to_run(schedule_config):
                # 检查是否在当前分钟内已经执行过
                now = datetime.now()
                if last_run is None:
                    return True
                # 确保同一分钟内不会重复执行
                time_diff = (now - last_run).total_seconds()
                if time_diff >= 60:  # 至少间隔60秒
                    return True

        except Exception as e:
            self.logger.error(f"检查任务执行时间失败: {e}")

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
    """Trending Service 定时任务调度器（集成重试机制）"""

    def __init__(self, logger=None):
        # 先调用父类初始化设置 logger
        super().__init__(logger)
        
        self.dao = TrendingDAO(DATABASE['path'])
        self.failure_dao = FetchFailureDAO(DATABASE['path'])
        
        # 初始化重试管理器
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=60,
            max_delay=300,
            exponential_base=2.0
        )
        self.retry_manager = RetryManager(config=retry_config, logger=self.logger)
        
        # 设置持久化回调
        self.retry_manager.set_persist_callback(self._persist_fetch_result)
        
        # 注册数据源获取函数
        self._register_fetchers()
        
        self._setup_tasks()
        
        # 加载待重试的任务
        self._load_pending_retries()

    def _register_fetchers(self):
        """注册所有数据源获取函数到重试管理器"""
        fetchers = {
            'github': lambda: GitHubTrendingFetcher(logger=self.logger).fetch(),
            'github_ai': lambda: GitHubTrendingFetcher(logger=self.logger).get_ai_repos(),
            'bilibili': lambda: BilibiliHotFetcher(logger=self.logger).fetch(),
            'arxiv': lambda: ArxivPapersFetcher(logger=self.logger).fetch(),
            'hackernews': lambda: HackerNewsFetcher(logger=self.logger).fetch(),
            'zhihu': lambda: ZhihuHotFetcher(logger=self.logger).fetch(),
            'weibo': lambda: WeiboHotFetcher(logger=self.logger).fetch(),
            'douyin': lambda: DouyinHotFetcher(logger=self.logger).fetch(),
        }
        
        for source, fetcher in fetchers.items():
            # github_ai 是 github 的衍生数据源，跟随 github 的启用状态
            if source == 'github_ai':
                if DATA_SOURCES.get('github', {}).get('enabled'):
                    self.retry_manager.register_fetcher(source, fetcher)
                    self.logger.debug(f"注册数据源: {source}")
            elif DATA_SOURCES.get(source, {}).get('enabled'):
                self.retry_manager.register_fetcher(source, fetcher)
                self.logger.debug(f"注册数据源: {source}")

    def _persist_fetch_result(self, result: FetchResult):
        """持久化获取结果到数据库"""
        try:
            if result.success:
                # 如果成功，标记为成功
                self.failure_dao.mark_success(result.source)
            else:
                # 如果失败，保存失败记录
                next_retry = None
                if result.retry_count < self.retry_manager.config.max_retries:
                    delay = self.retry_manager.config.calculate_delay(result.retry_count)
                    from datetime import timedelta
                    next_retry = datetime.now() + timedelta(seconds=delay)
                
                self.failure_dao.save_failure(
                    source=result.source,
                    error_message=result.error_message,
                    retry_count=result.retry_count,
                    next_retry_at=next_retry
                )
        except Exception as e:
            self.logger.error(f"持久化获取结果失败: {e}")

    def _load_pending_retries(self):
        """从数据库加载待重试的任务"""
        try:
            pending = self.failure_dao.get_pending_failures()
            for failure in pending:
                result = FetchResult(
                    source=failure.source,
                    success=False,
                    item_count=0,
                    error_message=failure.error_message,
                    timestamp=failure.last_try_at or datetime.now(),
                    retry_count=failure.retry_count,
                    status=FetchStatus.PENDING
                )
                # 重新加入重试队列
                self.retry_manager.record_result(result)
            
            if pending:
                self.logger.info(f"加载了 {len(pending)} 个待重试的数据源")
        except Exception as e:
            self.logger.error(f"加载待重试任务失败: {e}")

    def _setup_tasks(self):
        """设置默认任务"""
        # 添加获取热点任务
        self.add_task(
            name='fetch_trending',
            schedule=SCHEDULE['fetch_trending']['schedule'],
            task_func=self._fetch_all_trending,
            enabled=SCHEDULE['fetch_trending']['enabled']
        )

        # 添加数据清理任务（每天凌晨3点执行）
        self.add_task(
            name='cleanup_old_data',
            schedule='0 3 * * *',
            task_func=self._cleanup_old_data,
            enabled=True
        )

    def _run_scheduler(self):
        """调度器主循环（集成重试逻辑）"""
        self.logger.info("调度器开始运行（集成重试机制）...")

        while self.running and not self.stop_event.is_set():
            try:
                # 1. 检查并执行定时任务
                for name, task in self.tasks.items():
                    if not task['enabled']:
                        continue

                    if self._should_run(task):
                        self.logger.info(f"执行任务: {name}")
                        try:
                            task['func']()
                            task['last_run'] = datetime.now()
                        except Exception as e:
                            self.logger.error(f"任务 {name} 执行失败: {e}")

                # 2. 处理重试队列
                retry_results = self.retry_manager.process_retries()
                if retry_results:
                    # 如果有重试成功的，重新生成报告
                    success_sources = [r.source for r in retry_results if r.success]
                    if success_sources:
                        self.logger.info(f"数据源 {', '.join(success_sources)} 重试成功，重新生成报告...")
                        self._generate_report()

                # 3. 等待一段时间再检查
                time.sleep(60)  # 每分钟检查一次

            except Exception as e:
                self.logger.error(f"调度器运行错误: {e}")
                time.sleep(60)

        self.logger.info("调度器已停止")

    def _fetch_all_trending(self):
        """获取所有热点信息（集成重试记录）"""
        self.logger.info("=" * 60)
        self.logger.info("开始获取所有热点信息...")

        all_items = []
        fetch_results = []

        # 获取GitHub数据
        if DATA_SOURCES.get('github', {}).get('enabled'):
            result = self._fetch_source('github', "📈 获取 GitHub Trending...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)
            
            # 获取GitHub AI数据
            result_ai = self._fetch_source('github_ai', "🤖 获取 GitHub AI...")
            if result_ai and result_ai.success:
                all_items.extend(self._get_items_from_result(result_ai))
            fetch_results.append(result_ai)

        # 获取B站数据
        if DATA_SOURCES.get('bilibili', {}).get('enabled'):
            result = self._fetch_source('bilibili', "🎥 获取 B站热门...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)

        # 获取arXiv数据
        if DATA_SOURCES.get('arxiv', {}).get('enabled'):
            result = self._fetch_source('arxiv', "📚 获取 ArXiv论文...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)
        
        # 获取HackerNews数据
        if DATA_SOURCES.get('hackernews', {}).get('enabled'):
            result = self._fetch_source('hackernews', "📰 获取 HackerNews...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)
        
        # 获取知乎热榜数据
        if DATA_SOURCES.get('zhihu', {}).get('enabled'):
            result = self._fetch_source('zhihu', "🔥 获取 知乎热榜...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)
        
        # 获取微博数据
        if DATA_SOURCES.get('weibo', {}).get('enabled'):
            result = self._fetch_source('weibo', "📱 获取 微博热搜...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)
        
        # 获取抖音数据
        if DATA_SOURCES.get('douyin', {}).get('enabled'):
            result = self._fetch_source('douyin', "🎵 获取 抖音热榜...")
            if result and result.success:
                all_items.extend(self._get_items_from_result(result))
            fetch_results.append(result)

        # 提取关键词
        if all_items:
            self.logger.info("🔍 提取关键词...")
            all_items = extract_keywords_for_items(all_items, top_k=5)
        
        # 保存到数据库
        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        # 生成报告
        self._generate_report()

        # 记录获取结果到重试管理器
        for result in fetch_results:
            if result:
                self.retry_manager.record_result(result)

        self.logger.info(f"热点信息获取完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

    def _fetch_source(self, source: str, message: str) -> Optional[FetchResult]:
        """获取单个数据源的数据"""
        self.logger.info(message)
        
        try:
            fetcher = self.retry_manager._fetchers.get(source)
            if not fetcher:
                self.logger.warning(f"数据源 {source} 未注册")
                return None
            
            items = fetcher()
            
            result = FetchResult(
                source=source,
                success=len(items) > 0,
                item_count=len(items),
                error_message=None,
                timestamp=datetime.now(),
                retry_count=0,
                status=FetchStatus.SUCCESS
            )
            
            self.logger.info(f"✅ {source} 数据获取完成: {len(items)} 条")
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"❌ 获取 {source} 数据失败: {error_msg}")
            
            result = FetchResult(
                source=source,
                success=False,
                item_count=0,
                error_message=error_msg,
                timestamp=datetime.now(),
                retry_count=0,
                status=FetchStatus.PENDING
            )
            
            return result

    def _get_items_from_result(self, result: FetchResult) -> List:
        """从获取结果中提取数据项（实际获取数据）"""
        try:
            fetcher = self.retry_manager._fetchers.get(result.source)
            if fetcher:
                return fetcher()
        except Exception as e:
            self.logger.error(f"获取 {result.source} 数据项失败: {e}")
        return []

    def _generate_report(self):
        """生成HTML报告"""
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

    def refresh_data(self, sources: list = None):
        """
        刷新指定数据源的数据
        用于手动刷新或修复数据问题
        """
        self.logger.info("=" * 60)
        self.logger.info("开始刷新数据...")

        all_items = []

        # 定义所有可用的 fetcher
        fetchers = {
            'github': (GitHubTrendingFetcher, "📈 刷新 GitHub Trending...", 'fetch'),
            'github_ai': (GitHubTrendingFetcher, "🤖 刷新 GitHub AI...", 'get_ai_repos'),
            'bilibili': (BilibiliHotFetcher, "🎥 刷新 B站热门...", 'fetch'),
            'arxiv': (ArxivPapersFetcher, "📚 刷新 ArXiv论文...", 'fetch'),
            'hackernews': (HackerNewsFetcher, "📰 刷新 HackerNews...", 'fetch'),
            'zhihu': (ZhihuHotFetcher, "🔥 刷新 知乎热榜...", 'fetch'),
            'weibo': (WeiboHotFetcher, "📱 刷新 微博热搜...", 'fetch'),
            'douyin': (DouyinHotFetcher, "🎵 刷新 抖音热榜...", 'fetch'),
        }

        # 如果没有指定数据源，刷新所有启用的
        if sources is None:
            sources = [name for name, config in DATA_SOURCES.items() if config.get('enabled')]
            # 添加 github_ai
            if 'github' in sources and 'github_ai' not in sources:
                sources.append('github_ai')

        for source in sources:
            if source not in fetchers:
                self.logger.warning(f"⚠️  未知的数据源: {source}")
                continue

            fetcher_class, message, method_name = fetchers[source]

            # github_ai 跟随 github 的启用状态
            if source == 'github_ai':
                if not DATA_SOURCES.get('github', {}).get('enabled'):
                    self.logger.info(f"⏭️  跳过 {source} (GitHub 未启用)")
                    continue
            elif not DATA_SOURCES.get(source, {}).get('enabled'):
                self.logger.info(f"⏭️  跳过 {source} (未启用)")
                continue

            try:
                self.logger.info(message)
                fetcher = fetcher_class(logger=self.logger)
                # 调用指定的方法
                fetch_method = getattr(fetcher, method_name)
                items = fetch_method()
                all_items.extend(items)
                self.logger.info(f"✅ {source} 数据刷新完成: {len(items)} 条")
                
                # 标记为成功
                self.failure_dao.mark_success(source)
            except Exception as e:
                self.logger.error(f"❌ 刷新 {source} 数据失败: {e}")

        # 提取关键词
        if all_items:
            self.logger.info("🔍 提取关键词...")
            all_items = extract_keywords_for_items(all_items, top_k=5)

        # 保存到数据库
        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        # 生成报告
        self._generate_report()

        self.logger.info(f"数据刷新完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

        return len(all_items)

    def get_fetch_status(self) -> Dict[str, Dict]:
        """
        获取所有数据源的状态
        
        Returns:
            数据源状态字典
        """
        status = {}
        
        # 获取重试管理器中的结果
        results = self.retry_manager.get_all_results()
        
        for source in DATA_SOURCES.keys():
            if not DATA_SOURCES[source].get('enabled'):
                continue
                
            result = results.get(source)
            failure = self.failure_dao.get_by_source(source)
            
            if result:
                status[source] = {
                    'success': result.success,
                    'item_count': result.item_count,
                    'last_update': result.timestamp.isoformat(),
                    'error_message': result.error_message,
                    'retry_count': result.retry_count,
                    'status': result.status.value
                }
            elif failure:
                status[source] = {
                    'success': failure.status == 'success',
                    'item_count': 0,
                    'last_update': failure.last_try_at.isoformat() if failure.last_try_at else None,
                    'error_message': failure.error_message,
                    'retry_count': failure.retry_count,
                    'status': failure.status
                }
            else:
                status[source] = {
                    'success': False,
                    'item_count': 0,
                    'last_update': None,
                    'error_message': None,
                    'retry_count': 0,
                    'status': 'unknown'
                }
        
        return status

    def force_retry_source(self, source: str) -> bool:
        """
        强制立即重试指定数据源
        
        Args:
            source: 数据源名称
            
        Returns:
            是否成功
        """
        self.logger.info(f"强制重试数据源: {source}")
        
        result = self.retry_manager.force_retry(source)
        
        if result and result.success:
            self.logger.info(f"✅ {source} 重试成功，获取 {result.item_count} 条数据")
            # 保存数据
            try:
                items = self._get_items_from_result(result)
                if items:
                    self.dao.save_items(items)
                    self._generate_report()
                return True
            except Exception as e:
                self.logger.error(f"保存 {source} 数据失败: {e}")
                return False
        else:
            self.logger.error(f"❌ {source} 重试失败")
            return False

    def _cleanup_old_data(self):
        """清理过期数据"""
        try:
            self.logger.info("🧹 开始清理过期数据...")
            days = DATABASE.get('cleanup_days', 30)
            deleted = self.dao.delete_old_data(days)
            self.logger.info(f"✅ 清理完成: 删除 {deleted} 条过期数据")
            
            # 清理旧的失败记录
            deleted_failures = self.failure_dao.delete_old_failures(days=7)
            self.logger.info(f"✅ 清理完成: 删除 {deleted_failures} 条过期失败记录")
        except Exception as e:
            self.logger.error(f"❌ 清理数据失败: {e}")
