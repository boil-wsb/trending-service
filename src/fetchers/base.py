"""
Fetcher 基类定义
所有数据获取器都应该继承这个基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TrendingItem:
    """统一的热点数据格式"""
    source: str = ""                    # 数据源名称
    category: Optional[str] = None      # 分类
    title: str = ""                     # 标题
    url: str = ""                       # 链接
    author: Optional[str] = None        # 作者
    description: Optional[str] = None   # 描述
    hot_score: Optional[float] = None   # 热度分数
    keywords: List[str] = field(default_factory=list)  # 关键词
    extra: Dict[str, Any] = field(default_factory=dict)  # 额外信息
    fetched_at: datetime = field(default_factory=datetime.now)


class BaseFetcher(ABC):
    """数据获取器基类"""
    
    name: str = ""           # 数据源名称（子类必须定义）
    enabled: bool = True     # 是否启用
    
    def __init__(self, config: Dict = None, logger=None):
        self.config = config or {}
        self.logger = logger
    
    @abstractmethod
    def fetch(self) -> List[TrendingItem]:
        """
        获取热点数据
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        pass
    
    def parse_item(self, raw_data: Dict) -> TrendingItem:
        """
        解析原始数据为统一格式
        子类可以覆盖此方法以自定义解析逻辑
        """
        return TrendingItem(
            source=self.name,
            title=raw_data.get('title', ''),
            url=raw_data.get('url', ''),
            author=raw_data.get('author'),
            description=raw_data.get('description'),
            hot_score=raw_data.get('hot_score'),
            category=raw_data.get('category'),
            extra=raw_data.get('extra', {})
        )
    
    def validate_item(self, item: TrendingItem) -> bool:
        """
        验证数据项是否有效
        
        Args:
            item: 待验证的数据项
            
        Returns:
            bool: 是否有效
        """
        return bool(item.title and item.url)
    
    def fetch_all(self) -> List[TrendingItem]:
        """
        获取所有数据（带验证和过滤）
        
        Returns:
            List[TrendingItem]: 有效的热点数据列表
        """
        items = self.fetch()
        valid_items = [item for item in items if self.validate_item(item)]
        
        if self.logger:
            self.logger.info(f"{self.name}: 获取 {len(items)} 条，有效 {len(valid_items)} 条")
        
        return valid_items
