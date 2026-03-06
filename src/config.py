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
    'port': 8888,
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
    },
    'stock': {
        'enabled': True,
        'auto_fetch': False,  # 默认不自动获取股票数据
    }
}

# 定时任务配置
# 支持两种格式：
# 1. 简单时间格式: "HH:MM" - 每日指定时间执行
# 2. Cron表达式: "0 */8 * * *" - 标准5段式cron格式 (分 时 日 月 周)
SCHEDULE = {
    'fetch_trending': {
        'schedule': "0 */8 * * *",  # 每8小时执行一次
        'enabled': True,
        'description': "获取所有热点信息",
        'timezone': 'Asia/Shanghai'  # 时区设置
    },
    'fetch_stock': {
        'schedule': "*/2 * * * *",  # 每2分钟执行一次
        'enabled': False,  # 默认禁用股票数据获取
        'description': "获取股票行情数据",
        'timezone': 'Asia/Shanghai'
    }
}


def parse_cron_expression(cron_expr: str) -> dict:
    """
    解析标准5段式Cron表达式
    
    格式: 分 时 日 月 周
    示例:
        "0 */8 * * *"    - 每8小时执行
        "0 8 * * *"      - 每天8:00执行
        "0 8,20 * * *"   - 每天8:00和20:00执行
        "*/30 * * * *"   - 每30分钟执行
    
    Args:
        cron_expr: Cron表达式字符串
        
    Returns:
        解析后的配置字典
        
    Raises:
        ValueError: 表达式格式错误
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}. Expected 5 parts, got {len(parts)}")
    
    def parse_field(field: str, min_val: int, max_val: int, field_name: str) -> list:
        """解析单个字段"""
        values = set()
        
        # 处理逗号分隔的多个值
        for part in field.split(','):
            part = part.strip()
            
            # 处理 */n 步长格式
            if part.startswith('*/'):
                step = int(part[2:])
                values.update(range(min_val, max_val + 1, step))
            # 处理 n-m 范围
            elif '-' in part:
                start, end = map(int, part.split('-'))
                values.update(range(start, end + 1))
            # 处理单个数字
            elif part.isdigit():
                values.add(int(part))
            # 处理 * 通配符
            elif part == '*':
                values.update(range(min_val, max_val + 1))
            else:
                raise ValueError(f"Invalid {field_name} value: {part}")
        
        # 验证范围
        for v in values:
            if not (min_val <= v <= max_val):
                raise ValueError(f"{field_name} value {v} out of range [{min_val}, {max_val}]")
        
        return sorted(list(values))
    
    return {
        'minute': parse_field(parts[0], 0, 59, 'minute'),
        'hour': parse_field(parts[1], 0, 23, 'hour'),
        'day': parse_field(parts[2], 1, 31, 'day'),
        'month': parse_field(parts[3], 1, 12, 'month'),
        'weekday': parse_field(parts[4], 0, 6, 'weekday'),
        'raw': cron_expr
    }


def validate_cron_expression(cron_expr: str) -> bool:
    """
    验证Cron表达式是否有效
    
    Args:
        cron_expr: Cron表达式字符串
        
    Returns:
        是否有效
    """
    try:
        parse_cron_expression(cron_expr)
        return True
    except ValueError:
        return False


def get_next_run_time(cron_expr: str, timezone: str = 'Asia/Shanghai') -> 'datetime':
    """
    获取下次执行时间
    
    Args:
        cron_expr: Cron表达式
        timezone: 时区
        
    Returns:
        下次执行的datetime对象
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    
    parsed = parse_cron_expression(cron_expr)
    now = datetime.now(ZoneInfo(timezone))
    
    # 从当前时间开始查找下一个匹配的时间点
    check_time = now.replace(second=0, microsecond=0)
    
    for _ in range(366 * 24 * 60):  # 最多查找一年
        check_time += timedelta(minutes=1)
        
        if (check_time.minute in parsed['minute'] and
            check_time.hour in parsed['hour'] and
            check_time.day in parsed['day'] and
            check_time.month in parsed['month'] and
            check_time.weekday() in parsed['weekday']):
            return check_time
    
    raise ValueError("Could not find next run time within one year")


def is_time_to_run(schedule_config: dict, current_time: 'datetime' = None) -> bool:
    """
    检查当前是否应该执行任务
    
    Args:
        schedule_config: 调度配置字典
        current_time: 当前时间，默认为现在
        
    Returns:
        是否应该执行
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    if not schedule_config.get('enabled', False):
        return False
    
    schedule = schedule_config.get('schedule', '')
    timezone = schedule_config.get('timezone', 'Asia/Shanghai')
    
    if current_time is None:
        current_time = datetime.now(ZoneInfo(timezone))
    else:
        current_time = current_time.astimezone(ZoneInfo(timezone))
    
    # 简单时间格式 HH:MM
    if ':' in schedule and ' ' not in schedule and schedule.count(':') == 1:
        hour, minute = map(int, schedule.split(':'))
        return current_time.hour == hour and current_time.minute == minute
    
    # Cron表达式
    try:
        parsed = parse_cron_expression(schedule)
        return (current_time.minute in parsed['minute'] and
                current_time.hour in parsed['hour'] and
                current_time.day in parsed['day'] and
                current_time.month in parsed['month'] and
                current_time.weekday() in parsed['weekday'])
    except ValueError:
        return False

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