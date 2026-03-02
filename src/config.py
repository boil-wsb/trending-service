"""
配置文件
统一管理 Trending Service 的配置信息
"""

import os
from pathlib import Path

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    # 加载项目根目录的 .env 文件
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装，跳过

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
LOGS_DIR = DATA_DIR / "logs"
DB_DIR = DATA_DIR / "db"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DB_DIR.mkdir(exist_ok=True)

# 数据库配置
DATABASE = {
    'path': DB_DIR / 'trending.db',
    'backup_count': 7,  # 保留7天备份
    'cleanup_days': 30,  # 自动清理30天前的数据
}

# HTTP服务器配置（用于API服务）
SERVER = {
    'host': 'localhost',
    'port': 8888,  # API 服务器端口，避免与报告服务器冲突
    'debug': False,
    'threaded': True,
}

# 数据源配置
DATA_SOURCES = {
    'github': {
        'enabled': True,
        'limit': 20,
        'languages': ['python', 'javascript', 'go', 'rust', 'java'],
        'since': 'weekly'
    },
    'bilibili': {
        'enabled': True,
        'limit': 20,
        'categories': ['科技', '人工智能', '编程']
    },
    'arxiv': {
        'enabled': True,
        'limit': 20,
        'categories': ['cs.AI', 'cs.LG', 'cs.CV']
    },
    'ai': {
        'enabled': True,
        'limit': 20,
        'keywords': ['ai', 'machine', 'learning', 'ml', 'neural', 'gpt']
    },
    'hackernews': {
        'enabled': True,
        'limit': 30,
    },
    'zhihu': {
        'enabled': True,
        'limit': 50,
    },
    'weibo': {
        'enabled': True,
        'limit': 50,
    },
    'douyin': {
        'enabled': True,
        'limit': 50,
    }
}

# 定时任务配置
SCHEDULE = {
    'fetch_trending': {
        'schedule': "08:00",  # 每日8:00
        'enabled': True,
        'description': "获取所有热点信息"
    }
}

# 日志配置
LOGGING = {
    'level': 'INFO',
    'format': '%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s:%(lineno)d - %(message)s',
    'date_format': '%Y-%m-%d %H:%M:%S',
    'file': LOGS_DIR / 'trending_service.log',
    'max_size': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5
}

# 数据文件配置
DATA_FILES = {
    'github_trending': REPORTS_DIR / 'github_trending.json',
    'github_weekly_growth': REPORTS_DIR / 'github_weekly_growth.json',
    'ai_trending': REPORTS_DIR / 'ai_trending.json',
    'bilibili_trending': REPORTS_DIR / 'bilibili_trending.json',
    'arxiv_biology': REPORTS_DIR / 'arxiv_biology.json',
    'arxiv_computer_ai': REPORTS_DIR / 'arxiv_computer_ai.json'
}

# HTTP路由配置
ROUTES = {
    'report': '/report.html',
    'api': '/api/',
    'static': '/static/'
}

# 浏览器配置
BROWSER = {
    'auto_open': True,
    'url': 'http://localhost:8000/report.html'
}

# 请求配置
REQUESTS = {
    'timeout': 60,
    'retry_count': 3,
    'delay': 1,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 代理配置（如果需要）
PROXY = {
    'enabled': False,
    'http': '',
    'https': ''
}

# 数据源URL配置
SOURCE_URLS = {
    'github_trending': 'https://github.com/trending',
    'bilibili_hot': 'https://www.bilibili.com/hot',
    'arxiv_search': 'https://arxiv.org/search'
}