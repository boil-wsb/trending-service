"""
数据分析模块
包含关键词提取、话题聚类、趋势分析等智能分析功能

使用延迟导入策略，避免启动时加载重型依赖（scikit-learn、jieba 等）
"""


def extract_keywords_for_items(items, top_k=5):
    """延迟导入并执行关键词提取"""
    from .keywords import extract_keywords_for_items as _extract
    return _extract(items, top_k=top_k)


def cluster_items_by_source(items, n_clusters=5):
    """延迟导入并执行话题聚类"""
    from .clustering import cluster_items_by_source as _cluster
    return _cluster(items, n_clusters=n_clusters)


def generate_trend_chart_data(dao, days=7):
    """延迟导入并生成趋势图表数据"""
    from .trends import generate_trend_chart_data as _trend
    return _trend(dao, days=days)


__all__ = [
    'extract_keywords_for_items',
    'cluster_items_by_source',
    'generate_trend_chart_data',
]
