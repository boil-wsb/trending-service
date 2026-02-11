"""
Trending Service 主模块
"""

# 延迟导入，避免循环导入问题
# 这些导入将在实际使用时才执行

__all__ = ['TrendingService', 'TrendingServer', 'TrendingTaskScheduler']

# 使用延迟导入属性
def __getattr__(name):
    if name == 'TrendingService':
        from .main import TrendingService
        return TrendingService
    elif name == 'TrendingServer':
        from .server import TrendingServer
        return TrendingServer
    elif name == 'TrendingTaskScheduler':
        from .scheduler import TrendingTaskScheduler
        return TrendingTaskScheduler
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
