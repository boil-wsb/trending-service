#!/usr/bin/env python3
"""
数据获取重试管理器

管理数据获取失败后的自动重试逻辑
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import threading
import time
import logging


class FetchStatus(Enum):
    """数据获取状态"""
    PENDING = "pending"      # 等待重试
    SUCCESS = "success"      # 成功
    FAILED = "failed"        # 最终失败（超过最大重试次数）
    RETRYING = "retrying"    # 正在重试


@dataclass
class FetchResult:
    """数据获取结果"""
    source: str                    # 数据源名称
    success: bool                  # 是否成功
    item_count: int               # 获取条目数
    error_message: Optional[str]  # 错误信息
    timestamp: datetime           # 时间戳
    retry_count: int = 0          # 重试次数
    status: FetchStatus = FetchStatus.PENDING  # 状态
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'source': self.source,
            'success': self.success,
            'item_count': self.item_count,
            'error_message': self.error_message,
            'timestamp': self.timestamp.isoformat(),
            'retry_count': self.retry_count,
            'status': self.status.value
        }


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3          # 最大重试次数
    base_delay: int = 60          # 基础延迟（秒）
    max_delay: int = 300          # 最大延迟（秒）
    exponential_base: float = 2.0 # 指数基数
    
    def calculate_delay(self, retry_count: int) -> int:
        """
        计算重试延迟时间（指数退避）
        
        第1次重试：60秒
        第2次重试：120秒
        第3次重试：240秒
        
        Args:
            retry_count: 当前重试次数
            
        Returns:
            延迟秒数
        """
        delay = self.base_delay * (self.exponential_base ** retry_count)
        return min(int(delay), self.max_delay)


@dataclass
class RetryTask:
    """重试任务"""
    source: str
    retry_count: int
    next_retry_at: datetime
    error_message: Optional[str]
    created_at: datetime = field(default_factory=datetime.now)
    
    def should_retry_now(self) -> bool:
        """检查是否应该立即重试"""
        return datetime.now() >= self.next_retry_at


class RetryManager:
    """
    重试管理器
    
    管理数据获取失败后的重试逻辑
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, 
                 logger: Optional[logging.Logger] = None):
        """
        初始化重试管理器
        
        Args:
            config: 重试配置，使用默认配置如果为None
            logger: 日志记录器
        """
        self.config = config or RetryConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # 重试队列：source -> RetryTask
        self._retry_queue: Dict[str, RetryTask] = {}
        
        # 获取结果记录：source -> FetchResult
        self._results: Dict[str, FetchResult] = {}
        
        # 数据源获取函数：source -> callable
        self._fetchers: Dict[str, Callable] = {}
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 持久化回调函数
        self._persist_callback: Optional[Callable[[FetchResult], None]] = None
        
    def register_fetcher(self, source: str, fetcher: Callable):
        """
        注册数据源获取函数
        
        Args:
            source: 数据源名称
            fetcher: 获取函数，应该返回获取的数据列表
        """
        with self._lock:
            self._fetchers[source] = fetcher
            self.logger.debug(f"注册数据源获取函数: {source}")
    
    def set_persist_callback(self, callback: Callable[[FetchResult], None]):
        """
        设置持久化回调函数
        
        Args:
            callback: 回调函数，用于持久化FetchResult
        """
        self._persist_callback = callback
    
    def record_result(self, result: FetchResult):
        """
        记录数据获取结果
        
        Args:
            result: 获取结果
        """
        with self._lock:
            self._results[result.source] = result
            
            # 如果失败且未达到最大重试次数，加入重试队列
            if not result.success and result.retry_count < self.config.max_retries:
                self._add_to_retry_queue(result)
            
            # 持久化结果
            if self._persist_callback:
                try:
                    self._persist_callback(result)
                except Exception as e:
                    self.logger.error(f"持久化结果失败: {e}")
    
    def _add_to_retry_queue(self, result: FetchResult):
        """
        将失败的数据源加入重试队列
        
        Args:
            result: 获取结果
        """
        delay = self.config.calculate_delay(result.retry_count)
        next_retry = datetime.now() + timedelta(seconds=delay)
        
        task = RetryTask(
            source=result.source,
            retry_count=result.retry_count,
            next_retry_at=next_retry,
            error_message=result.error_message
        )
        
        self._retry_queue[result.source] = task
        self.logger.info(
            f"数据源 {result.source} 将在 {delay} 秒后重试 "
            f"(第{result.retry_count + 1}次重试)"
        )
    
    def process_retries(self) -> List[FetchResult]:
        """
        处理重试队列
        
        检查并重试所有到期的数据源
        
        Returns:
            本次重试的结果列表
        """
        results = []
        sources_to_retry = []
        
        # 找出需要重试的数据源
        with self._lock:
            for source, task in list(self._retry_queue.items()):
                if task.should_retry_now():
                    sources_to_retry.append(source)
        
        # 执行重试
        for source in sources_to_retry:
            result = self._retry_source(source)
            if result:
                results.append(result)
        
        return results
    
    def _retry_source(self, source: str) -> Optional[FetchResult]:
        """
        重试指定数据源
        
        Args:
            source: 数据源名称
            
        Returns:
            重试结果，如果数据源未注册则返回None
        """
        if source not in self._fetchers:
            self.logger.warning(f"数据源 {source} 未注册，无法重试")
            return None
        
        # 从重试队列移除
        with self._lock:
            if source in self._retry_queue:
                del self._retry_queue[source]
        
        self.logger.info(f"开始重试数据源: {source}")
        
        try:
            # 执行获取
            fetcher = self._fetchers[source]
            items = fetcher()
            
            # 创建成功结果
            result = FetchResult(
                source=source,
                success=len(items) > 0,
                item_count=len(items),
                error_message=None,
                timestamp=datetime.now(),
                retry_count=self._get_retry_count(source),
                status=FetchStatus.SUCCESS
            )
            
            self.logger.info(f"数据源 {source} 重试成功，获取 {len(items)} 条数据")
            
        except Exception as e:
            # 创建失败结果
            result = FetchResult(
                source=source,
                success=False,
                item_count=0,
                error_message=str(e),
                timestamp=datetime.now(),
                retry_count=self._get_retry_count(source) + 1,
                status=FetchStatus.PENDING
            )
            
            self.logger.error(f"数据源 {source} 重试失败: {e}")
        
        # 记录结果
        self.record_result(result)
        
        return result
    
    def _get_retry_count(self, source: str) -> int:
        """获取数据源的重试次数"""
        with self._lock:
            if source in self._results:
                return self._results[source].retry_count
            return 0
    
    def get_pending_retries(self) -> List[RetryTask]:
        """
        获取待重试的任务列表
        
        Returns:
            待重试任务列表
        """
        with self._lock:
            return list(self._retry_queue.values())
    
    def get_result(self, source: str) -> Optional[FetchResult]:
        """
        获取指定数据源的获取结果
        
        Args:
            source: 数据源名称
            
        Returns:
            获取结果，如果不存在则返回None
        """
        with self._lock:
            return self._results.get(source)
    
    def get_all_results(self) -> Dict[str, FetchResult]:
        """
        获取所有数据源的获取结果
        
        Returns:
            数据源名称 -> 获取结果 的字典
        """
        with self._lock:
            return self._results.copy()
    
    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._retry_queue.clear()
            self._results.clear()
            self.logger.info("重试管理器已清空")
    
    def force_retry(self, source: str) -> Optional[FetchResult]:
        """
        强制立即重试指定数据源
        
        Args:
            source: 数据源名称
            
        Returns:
            重试结果
        """
        self.logger.info(f"强制重试数据源: {source}")
        return self._retry_source(source)
