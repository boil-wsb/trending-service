"""
定时任务调度器模块
管理定时任务的执行
"""

import time
import webbrowser
import socket
import requests
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Event
from datetime import datetime
from typing import Callable, Dict, List, Optional
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import SCHEDULE, DATA_SOURCES, REPORTS_DIR, BROWSER, SERVER, DATABASE, is_time_to_run
from src.utils import get_logger, ReportGenerator
from src.utils.retry_manager import RetryManager, FetchResult, FetchStatus, RetryConfig
from src.db import TrendingDAO, FetchFailureDAO
from src.fetchers import get_fetcher_class

_FETCHER_METHOD_MAP = {
    'github': 'fetch',
    'github_ai': 'get_ai_repos',
    'bilibili': 'fetch',
    'arxiv': 'fetch',
    'hackernews': 'fetch',
    'zhihu': 'fetch',
    'weibo': 'fetch',
    'douyin': 'fetch',
    'aihot': 'fetch',
    'index': 'fetch',
}


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self, logger=None):
        self.logger = logger or get_logger('scheduler')
        self.tasks: Dict[str, Dict] = {}
        self.running = False
        self.stop_event = Event()
        self.scheduler_thread = None

    def add_task(self, name: str, schedule: str, task_func: Callable, enabled: bool = True):
        self.tasks[name] = {
            'schedule': schedule,
            'func': task_func,
            'enabled': enabled,
            'last_run': None
        }
        self.logger.info(f"添加任务: {name} (schedule: {schedule})")

        try:
            from src.config import get_next_run_time
            next_run = get_next_run_time(schedule)
            self.logger.info(f"  下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            self.logger.warning(f"  无法计算下次执行时间: {e}")

    def remove_task(self, name: str):
        if name in self.tasks:
            del self.tasks[name]
            self.logger.info(f"移除任务: {name}")

    def enable_task(self, name: str, enabled: bool = True):
        if name in self.tasks:
            self.tasks[name]['enabled'] = enabled
            self.logger.info(f"任务 {name} {'启用' if enabled else '禁用'}")

    def start(self):
        if self.running:
            self.logger.warning("调度器已在运行中")
            return

        self.running = True
        self.stop_event.clear()
        self.scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("定时任务调度器已启动")

    def stop(self):
        if not self.running:
            return

        self.running = False
        self.stop_event.set()

        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)

        self.logger.info("定时任务调度器已停止")

    def _run_scheduler(self):
        self.logger.info("调度器开始运行...")

        while self.running and not self.stop_event.is_set():
            try:
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

                time.sleep(60)

            except Exception as e:
                self.logger.error(f"调度器运行错误: {e}")
                time.sleep(60)

        self.logger.info("调度器已停止")

    def _should_run(self, task: Dict) -> bool:
        schedule = task['schedule']
        last_run = task['last_run']

        try:
            from src.config import is_time_to_run

            schedule_config = {
                'schedule': schedule,
                'enabled': True,
                'timezone': 'Asia/Shanghai'
            }

            if is_time_to_run(schedule_config):
                now = datetime.now()
                if last_run is None:
                    return True
                time_diff = (now - last_run).total_seconds()
                if time_diff >= 60:
                    return True

        except Exception as e:
            self.logger.error(f"检查任务执行时间失败: {e}")

        return False

    def run_task_now(self, name: str):
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
        super().__init__(logger)
        
        self.dao = TrendingDAO(DATABASE['path'])
        self.failure_dao = FetchFailureDAO(DATABASE['path'])
        
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=60,
            max_delay=300,
            exponential_base=2.0
        )
        self.retry_manager = RetryManager(config=retry_config, logger=self.logger)
        
        self.retry_manager.set_persist_callback(self._persist_fetch_result)
        
        self._register_fetchers()
        
        self._setup_tasks()
        
        self._load_pending_retries()

    def _register_fetchers(self):
        for source in _FETCHER_METHOD_MAP:
            if source == 'github_ai':
                if not DATA_SOURCES.get('github', {}).get('enabled'):
                    continue
            elif not DATA_SOURCES.get(source, {}).get('enabled'):
                continue

            method_name = _FETCHER_METHOD_MAP[source]

            def _make_fetcher(src, method):
                def _fetcher():
                    fetcher_class = get_fetcher_class(src)
                    fetcher = fetcher_class(logger=self.logger)
                    return getattr(fetcher, method)()
                return _fetcher

            self.retry_manager.register_fetcher(source, _make_fetcher(source, method_name))
            self.logger.debug(f"注册数据源: {source}")

    def _persist_fetch_result(self, result: FetchResult):
        try:
            if result.success:
                self.failure_dao.mark_success(result.source)
            else:
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
                self.retry_manager.record_result(result)
            
            if pending:
                self.logger.info(f"加载了 {len(pending)} 个待重试的数据源")
        except Exception as e:
            self.logger.error(f"加载待重试任务失败: {e}")

    def _setup_tasks(self):
        self.add_task(
            name='fetch_trending',
            schedule=SCHEDULE['fetch_trending']['schedule'],
            task_func=self._fetch_all_trending,
            enabled=SCHEDULE['fetch_trending']['enabled']
        )

        self.add_task(
            name='fetch_index',
            schedule=SCHEDULE['fetch_index']['schedule'],
            task_func=self._fetch_index_data,
            enabled=SCHEDULE['fetch_index']['enabled']
        )

        self.add_task(
            name='fetch_index_kline',
            schedule='30 15 * * 1-5',
            task_func=self._fetch_index_kline_data,
            enabled=True
        )

        self.add_task(
            name='cleanup_old_data',
            schedule='0 3 * * *',
            task_func=self._cleanup_old_data,
            enabled=True
        )

    def _run_scheduler(self):
        self.logger.info("调度器开始运行（集成重试机制）...")

        while self.running and not self.stop_event.is_set():
            try:
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

                retry_results = self.retry_manager.process_retries()
                if retry_results:
                    success_sources = [r.source for r in retry_results if r.success]
                    if success_sources:
                        self.logger.info(f"数据源 {', '.join(success_sources)} 重试成功，重新生成报告...")
                        self._generate_report()

                time.sleep(60)

            except Exception as e:
                self.logger.error(f"调度器运行错误: {e}")
                time.sleep(60)

        self.logger.info("调度器已停止")

    def _fetch_all_trending(self):
        """获取所有热点信息（并行抓取 + 无重复请求）"""
        self.logger.info("=" * 60)
        self.logger.info("开始获取所有热点信息...")

        source_order = [
            ('github', "📈 获取 GitHub Trending..."),
            ('github_ai', "🤖 获取 GitHub AI..."),
            ('bilibili', "🎥 获取 B站热门..."),
            ('arxiv', "📚 获取 ArXiv论文..."),
            ('hackernews', "📰 获取 HackerNews..."),
            ('zhihu', "🔥 获取 知乎热榜..."),
            ('weibo', "📱 获取 微博热搜..."),
            ('douyin', "🎵 获取 抖音热榜..."),
            ('aihot', "🔥 获取 AIHOT..."),
        ]

        enabled_sources = []
        for source, message in source_order:
            if source == 'github_ai':
                if DATA_SOURCES.get('github', {}).get('enabled'):
                    enabled_sources.append((source, message))
            elif DATA_SOURCES.get(source, {}).get('enabled'):
                enabled_sources.append((source, message))

        all_items = []
        fetch_results = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {}
            for source, message in enabled_sources:
                self.logger.info(message)
                future = executor.submit(self._fetch_source, source, message)
                future_map[future] = source

            for future in as_completed(future_map):
                source = future_map[future]
                try:
                    result = future.result()
                    if result:
                        fetch_results.append(result)
                        if result.success and result.items:
                            all_items.extend(result.items)
                            self.logger.info(f"✅ {source} 数据获取完成: {len(result.items)} 条")
                except Exception as e:
                    self.logger.error(f"❌ {source} 数据获取异常: {e}")

        if all_items:
            self.logger.info("🔍 提取关键词...")
            from src.analytics import extract_keywords_for_items
            all_items = extract_keywords_for_items(all_items, top_k=5)
        
        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        self._generate_report()

        for result in fetch_results:
            if result:
                self.retry_manager.record_result(result)

        self.logger.info(f"热点信息获取完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

    def _fetch_source(self, source: str, message: str) -> Optional[FetchResult]:
        """获取单个数据源的数据（一次性获取，保存 items 避免重复请求）"""
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
                items=items,
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
                items=[],
                error_message=error_msg,
                timestamp=datetime.now(),
                retry_count=0,
                status=FetchStatus.PENDING
            )
            
            return result

    def _generate_report(self):
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
        self.logger.info("=" * 60)
        self.logger.info("开始刷新数据...")

        all_items = []

        if sources is None:
            sources = [name for name, config in DATA_SOURCES.items() if config.get('enabled')]
            if 'github' in sources and 'github_ai' not in sources:
                sources.append('github_ai')

        for source in sources:
            if source not in _FETCHER_METHOD_MAP:
                self.logger.warning(f"⚠️  未知的数据源: {source}")
                continue

            if source == 'github_ai':
                if not DATA_SOURCES.get('github', {}).get('enabled'):
                    self.logger.info(f"⏭️  跳过 {source} (GitHub 未启用)")
                    continue
            elif not DATA_SOURCES.get(source, {}).get('enabled'):
                self.logger.info(f"⏭️  跳过 {source} (未启用)")
                continue

            try:
                self.logger.info(f"🔄 刷新 {source}...")
                fetcher_class = get_fetcher_class(source)
                fetcher = fetcher_class(logger=self.logger)
                method_name = _FETCHER_METHOD_MAP[source]
                items = getattr(fetcher, method_name)()
                all_items.extend(items)
                self.logger.info(f"✅ {source} 数据刷新完成: {len(items)} 条")
                
                self.failure_dao.mark_success(source)
            except Exception as e:
                self.logger.error(f"❌ 刷新 {source} 数据失败: {e}")

        if all_items:
            self.logger.info("🔍 提取关键词...")
            from src.analytics import extract_keywords_for_items
            all_items = extract_keywords_for_items(all_items, top_k=5)

        if all_items:
            try:
                self.logger.info(f"💾 保存 {len(all_items)} 条数据到数据库...")
                saved_count = self.dao.refresh_items(all_items)
                self.logger.info(f"✅ 成功保存 {saved_count} 条数据")
            except Exception as e:
                self.logger.error(f"❌ 保存数据失败: {e}")

        self._generate_report()

        self.logger.info(f"数据刷新完成! 共 {len(all_items)} 条")
        self.logger.info("=" * 60)

        return len(all_items)

    def get_fetch_status(self) -> Dict[str, Dict]:
        status = {}
        
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
        self.logger.info(f"强制重试数据源: {source}")
        
        result = self.retry_manager.force_retry(source)
        
        if result and result.success:
            self.logger.info(f"✅ {source} 重试成功，获取 {result.item_count} 条数据")
            try:
                if result.items:
                    self.dao.save_items(result.items)
                    self._generate_report()
                return True
            except Exception as e:
                self.logger.error(f"保存 {source} 数据失败: {e}")
                return False
        else:
            self.logger.error(f"❌ {source} 重试失败")
            return False

    def _cleanup_old_data(self):
        try:
            self.logger.info("🧹 开始清理过期数据...")
            days = DATABASE.get('cleanup_days', 30)
            deleted = self.dao.delete_old_data(days)
            self.logger.info(f"✅ 清理完成: 删除 {deleted} 条过期数据")

            deleted_failures = self.failure_dao.delete_old_failures(days=7)
            self.logger.info(f"✅ 清理完成: 删除 {deleted_failures} 条过期失败记录")
        except Exception as e:
            self.logger.error(f"❌ 清理数据失败: {e}")

    def _is_trading_hours(self) -> bool:
        """判断当前是否在 A 股开盘时间内

        开盘时间窗口和交易日期从 config.yaml 的 schedule.fetch_index 读取：
        - trading_hours: [{start: "09:30", end: "11:30"}, {start: "13:00", end: "15:00"}]
        - trading_days: [1, 2, 3, 4, 5]  # 1=周一 ... 7=周日（ISO 标准）
        """
        try:
            from datetime import datetime, time as dt_time
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                from backports.zoneinfo import ZoneInfo  # type: ignore

            cfg = SCHEDULE.get('fetch_index', {})
            trading_hours_cfg = cfg.get('trading_hours')
            trading_days = cfg.get('trading_days', [1, 2, 3, 4, 5])
            tz_name = cfg.get('timezone', 'Asia/Shanghai')

            # 未配置 trading_hours 时，默认允许任意时间执行（向后兼容）
            if not trading_hours_cfg:
                return True

            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)

            # 周几判断（ISO: 1=周一 ... 7=周日）
            if now.isoweekday() not in trading_days:
                return False

            now_time = now.time()

            for window in trading_hours_cfg:
                start_str = window.get('start')
                end_str = window.get('end')
                if not start_str or not end_str:
                    continue
                sh, sm = map(int, start_str.split(':'))
                eh, em = map(int, end_str.split(':'))
                if dt_time(sh, sm) <= now_time <= dt_time(eh, em):
                    return True

            return False
        except Exception as e:
            self.logger.error(f"判断开盘时间失败: {e}，默认允许执行")
            return True

    def _fetch_index_data(self):
        """获取 A 股指数行情数据（市场指数 + 申万行业指数）

        仅在 A 股开盘时间内执行（9:30-11:30, 13:00-15:00，周一至周五）。
        非开盘时间直接跳过，避免无效请求。
        """
        if not self._is_trading_hours():
            self.logger.info("⏭️  当前非 A 股开盘时间，跳过指数行情数据获取")
            return

        try:
            self.logger.info("📈 开始获取指数行情数据...")
            from src.fetchers.index import IndexFetcher
            from src.config import DATABASE

            fetcher = IndexFetcher(logger=self.logger)
            count = fetcher.save_to_db(DATABASE['path'])
            self.logger.info(f"✅ 指数行情数据获取完成: {count} 条")
        except Exception as e:
            self.logger.error(f"❌ 获取指数行情数据失败: {e}")

    def _fetch_index_kline_data(self):
        """每日缓存所有市场指数的 K 线数据到数据库

        调度：每个交易日 15:30 执行（收盘后 30 分钟）
        作用：避免前端每次请求 K 线都从腾讯源实时拉取，提升响应速度
        """
        try:
            self.logger.info("📊 开始每日缓存指数 K 线数据...")
            from src.fetchers.index import IndexFetcher
            from src.config import DATABASE

            fetcher = IndexFetcher(logger=self.logger)
            count = fetcher.fetch_and_cache_all_klines(DATABASE['path'], days=365)
            self.logger.info(f"✅ 指数 K 线数据缓存完成: {count} 条")
        except Exception as e:
            self.logger.error(f"❌ 缓存指数 K 线数据失败: {e}")
