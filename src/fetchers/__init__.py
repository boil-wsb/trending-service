"""
数据获取模块
包含各种数据源的获取器
"""

from .base import BaseFetcher, TrendingItem
from .github_trending import GitHubTrendingFetcher
from .bilibili_hot import BilibiliHotFetcher
from .arxiv_papers import ArxivPapersFetcher
from .hackernews import HackerNewsFetcher
from .zhihu_hot import ZhihuHotFetcher
from .weibo_hot import WeiboHotFetcher
from .douyin_hot import DouyinHotFetcher

__all__ = [
    'BaseFetcher',
    'TrendingItem',
    'GitHubTrendingFetcher',
    'BilibiliHotFetcher',
    'ArxivPapersFetcher',
    'HackerNewsFetcher',
    'ZhihuHotFetcher',
    'WeiboHotFetcher',
    'DouyinHotFetcher',
]
