"""
数据模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict
import json


@dataclass
class TrendingItem:
    """热点数据项"""
    id: Optional[int] = None
    source: str = ""                    # 数据源
    category: Optional[str] = None      # 分类
    title: str = ""                     # 标题
    url: str = ""                       # 链接
    author: Optional[str] = None        # 作者
    description: Optional[str] = None   # 描述
    hot_score: Optional[float] = None   # 热度分数
    keywords: List[str] = field(default_factory=list)  # 关键词
    extra: Dict = field(default_factory=dict)  # 额外信息
    fetched_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'source': self.source,
            'category': self.category,
            'title': self.title,
            'url': self.url,
            'author': self.author,
            'description': self.description,
            'hot_score': self.hot_score,
            'keywords': json.dumps(self.keywords, ensure_ascii=False),
            'extra': json.dumps(self.extra, ensure_ascii=False),
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TrendingItem':
        """从字典创建对象"""
        keywords = data.get('keywords', '')
        if isinstance(keywords, str):
            if keywords.startswith('['):
                # JSON 格式
                try:
                    keywords = json.loads(keywords)
                except:
                    keywords = []
            else:
                # 逗号分隔格式
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        
        fetched_at = data.get('fetched_at')
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)
        
        # 解析 extra 字段
        extra = data.get('extra', '{}')
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except:
                extra = {}
        
        return cls(
            id=data.get('id'),
            source=data.get('source', ''),
            category=data.get('category'),
            title=data.get('title', ''),
            url=data.get('url', ''),
            author=data.get('author'),
            description=data.get('description'),
            hot_score=data.get('hot_score'),
            keywords=keywords,
            extra=extra,
            fetched_at=fetched_at or datetime.now()
        )


@dataclass
class DailyStats:
    """每日统计"""
    id: Optional[int] = None
    date: date = field(default_factory=date.today)
    source: str = ""
    total_count: int = 0
    top_keywords: Dict[str, int] = field(default_factory=dict)
    avg_hot_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'source': self.source,
            'total_count': self.total_count,
            'top_keywords': json.dumps(self.top_keywords, ensure_ascii=False),
            'avg_hot_score': self.avg_hot_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DailyStats':
        """从字典创建对象"""
        top_keywords = data.get('top_keywords', '{}')
        if isinstance(top_keywords, str):
            try:
                top_keywords = json.loads(top_keywords)
            except:
                top_keywords = {}
        
        date_val = data.get('date')
        if isinstance(date_val, str):
            date_val = date.fromisoformat(date_val)
        
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        return cls(
            id=data.get('id'),
            date=date_val or date.today(),
            source=data.get('source', ''),
            total_count=data.get('total_count', 0),
            top_keywords=top_keywords,
            avg_hot_score=data.get('avg_hot_score', 0.0),
            created_at=created_at or datetime.now()
        )


@dataclass
class Notification:
    """通知记录"""
    id: Optional[int] = None
    type: str = ""                      # 通知类型
    status: str = "pending"             # pending/sent/failed
    content: Optional[str] = None       # 通知内容
    sent_at: Optional[datetime] = None  # 发送时间
    error_msg: Optional[str] = None     # 错误信息
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'type': self.type,
            'status': self.status,
            'content': self.content,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error_msg': self.error_msg,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class StockData:
    """股票行情数据"""
    id: Optional[int] = None
    code: str = ""                       # 股票代码 (如 000001)
    name: str = ""                        # 股票名称 (如 平安银行)
    price: float = 0.0                    # 当前价格
    change: float = 0.0                   # 涨跌额
    change_pct: float = 0.0               # 涨跌幅 (%)
    volume: int = 0                       # 成交量 (手)
    amount: float = 0.0                   # 成交额 (元)
    market_cap: float = 0.0               # 总市值 (元)
    turnover_rate: float = 0.0            # 换手率 (%)
    source: str = "eastmoney"             # 数据源
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'price': round(self.price, 2),
            'change': round(self.change, 2),
            'change_pct': round(self.change_pct, 2),
            'volume': self.volume,
            'amount': round(self.amount / 100000000, 2) if self.amount else 0,
            'market_cap': round(self.market_cap / 100000000, 2) if self.market_cap else 0,
            'turnover_rate': round(self.turnover_rate, 2),
            'source': self.source,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StockData':
        """从字典创建对象"""
        fetched_at = data.get('fetched_at')
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)

        return cls(
            id=data.get('id'),
            code=data.get('code', ''),
            name=data.get('name', ''),
            price=data.get('price', 0.0),
            change=data.get('change', 0.0),
            change_pct=data.get('change_pct', 0.0),
            volume=data.get('volume', 0),
            amount=data.get('amount', 0.0),
            market_cap=data.get('market_cap', 0.0),
            turnover_rate=data.get('turnover_rate', 0.0),
            source=data.get('source', 'eastmoney'),
            fetched_at=fetched_at or datetime.now()
        )
