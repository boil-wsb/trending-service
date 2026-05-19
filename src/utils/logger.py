"""
日志工具模块
提供统一的日志配置和管理
"""

import logging
import sys
import os
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

DEFAULT_FORMAT = '%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s:%(lineno)d - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

DEFAULT_LOGS_DIR = Path(__file__).parent.parent.parent / 'data' / 'logs'


class MonthlyRotatingFileHandler(TimedRotatingFileHandler):
    """按月轮转的日志处理器"""

    def __init__(self, filename, backupCount=12, encoding=None):
        super().__init__(
            filename,
            when='MIDNIGHT',
            interval=1,
            backupCount=backupCount,
            encoding=encoding,
            utc=False
        )

    def getFilesToDelete(self):
        """重写文件删除逻辑，按月份后缀匹配"""
        dir_name, base_name = os.path.dirname(self.baseFilename), os.path.basename(self.baseFilename)
        file_names = os.listdir(dir_name)
        result = []
        for file_name in file_names:
            if file_name.startswith(base_name + '.'):
                result.append(os.path.join(dir_name, file_name))
        if len(result) <= self.backupCount:
            return []
        result.sort(key=lambda x: os.path.getmtime(x))
        return result[:len(result) - self.backupCount]

    def shouldRollover(self, record):
        """检查是否需要轮转（月份变更时轮转）"""
        t = int(time.time())
        if t >= self.rolloverAt:
            return 1
        current_month = time.localtime(t).tm_mon
        if hasattr(self, '_last_month'):
            if current_month != self._last_month:
                return 1
        else:
            self._last_month = current_month
        self._last_month = time.localtime(t).tm_mon
        return 0

    def doRollover(self):
        """执行月度轮转"""
        self.stream.close()
        now = time.localtime()
        time_tuple = (now.tm_year, now.tm_mon, now.tm_mday,
                      now.tm_hour, now.tm_min, now.tm_sec,
                      now.tm_wday, now.tm_yday, now.tm_isdst)
        dfn = self.baseFilename + '.' + time.strftime('%Y-%m', time_tuple)
        if os.path.exists(dfn):
            os.remove(dfn)
        os.rename(self.baseFilename, dfn)
        self.stream = open(self.baseFilename, 'a', encoding=self.encoding)
        self._last_month = now.tm_mon
        self.rolloverAt = self.computeRollover(int(time.time()))
        if self.backupCount > 0:
            for file_to_delete in self.getFilesToDelete():
                os.remove(file_to_delete)


def setup_logger(
    name: str = 'trending_service',
    log_file: Path = None,
    level: str = 'INFO',
    logs_dir: Path = None
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    logger.handlers.clear()

    formatter = logging.Formatter(
        DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is None:
        logs_dir = logs_dir or DEFAULT_LOGS_DIR
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f'{name}.log'
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = MonthlyRotatingFileHandler(
        log_file,
        backupCount=12,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = 'trending_service') -> logging.Logger:
    return logging.getLogger(name)
