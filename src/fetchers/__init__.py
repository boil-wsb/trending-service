"""
数据获取模块
包含各种数据源的获取器
"""

from .github_trending import GitHubTrendingFetcher
from .bilibili_hot import BilibiliHotFetcher
from .arxiv_papers import ArxivPapersFetcher

__all__ = ['GitHubTrendingFetcher', 'BilibiliHotFetcher', 'ArxivPapersFetcher']