"""
数据获取模块
包含各种数据源的获取器

使用延迟导入策略，避免启动时加载重型依赖（playwright、scikit-learn 等）
"""

from .base import BaseFetcher, TrendingItem

_FETCHER_REGISTRY = {
    'github': ('src.fetchers.github_trending', 'GitHubTrendingFetcher'),
    'github_ai': ('src.fetchers.github_trending', 'GitHubTrendingFetcher'),
    'bilibili': ('src.fetchers.bilibili_hot', 'BilibiliHotFetcher'),
    'arxiv': ('src.fetchers.arxiv_papers', 'ArxivPapersFetcher'),
    'hackernews': ('src.fetchers.hackernews', 'HackerNewsFetcher'),
    'zhihu': ('src.fetchers.zhihu_hot', 'ZhihuHotFetcher'),
    'weibo': ('src.fetchers.weibo_hot', 'WeiboHotFetcher'),
    'douyin': ('src.fetchers.douyin_hot', 'DouyinHotFetcher'),
    'aihot': ('src.fetchers.aihot', 'AihotFetcher'),
}

_cached_classes = {}


def get_fetcher_class(source: str):
    """按需导入并返回指定数据源的 Fetcher 类"""
    if source in _cached_classes:
        return _cached_classes[source]

    if source not in _FETCHER_REGISTRY:
        raise ValueError(f"未知的数据源: {source}")

    module_path, class_name = _FETCHER_REGISTRY[source]
    import importlib
    module = importlib.import_module(module_path)
    fetcher_class = getattr(module, class_name)
    _cached_classes[source] = fetcher_class
    return fetcher_class


def get_available_sources():
    """返回所有可用的数据源名称"""
    return list(_FETCHER_REGISTRY.keys())


__all__ = [
    'BaseFetcher',
    'TrendingItem',
    'get_fetcher_class',
    'get_available_sources',
    '_FETCHER_REGISTRY',
]
