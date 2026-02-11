"""
日志工具模块
提供统一的日志配置和管理
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 默认日志格式
DEFAULT_FORMAT = '%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s:%(lineno)d - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 默认日志目录
DEFAULT_LOGS_DIR = Path(__file__).parent.parent.parent / 'data' / 'logs'


def setup_logger(
    name: str = 'trending_service',
    log_file: Path = None,
    level: str = 'INFO',
    logs_dir: Path = None
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径（如果为None，则使用默认路径）
        level: 日志级别
        logs_dir: 日志目录（如果为None，则使用默认目录）

    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 清除现有处理器
    logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(
        DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 确定日志文件路径
    if log_file is None:
        logs_dir = logs_dir or DEFAULT_LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f'{name}.log'
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # 文件处理器
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = 'trending_service') -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    return logging.getLogger(name)
