"""
日志工具模块
提供统一的日志配置和管理
"""

import logging
import logging.handlers
import sys
import os
import time
from pathlib import Path

DEFAULT_FORMAT = '%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s:%(lineno)d - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

DEFAULT_LOGS_DIR = Path(__file__).parent.parent.parent / 'data' / 'logs'


class MonthlyRotatingFileHandler(logging.handlers.BaseRotatingHandler):
    """按月轮转的日志处理器

    每月1日凌晨首次写日志时触发轮转：把上个月的日志整体归档为
    `baseFilename.YYYY-MM`，新月份的日志继续写入 `baseFilename`。

    - 仅按 (year, month) 变化触发轮转，不再每天凌晨轮转
    - 归档时若目标文件已存在则追加合并（而非删除覆盖），杜绝数据丢失
    - 归档文件用上一个月命名（旧文件装的就是上个月的日志）
    """

    def __init__(self, filename, backupCount=12, encoding=None):
        super().__init__(filename, mode='a', encoding=encoding, delay=False)
        self.backupCount = backupCount
        now = time.localtime()
        self._current_year = now.tm_year
        self._current_month = now.tm_mon

    def shouldRollover(self, record):
        """月份变更时返回 1"""
        now = time.localtime()
        if now.tm_year != self._current_year or now.tm_mon != self._current_month:
            return 1
        return 0

    def doRollover(self):
        """执行月度轮转"""
        if self.stream:
            self.stream.close()
            self.stream = None
        now = time.localtime()
        # 旧文件装的是上个月日志，归档用上个月命名
        if now.tm_mon == 1:
            prev_year, prev_month = now.tm_year - 1, 12
        else:
            prev_year, prev_month = now.tm_year, now.tm_mon - 1
        dfn = self.baseFilename + '.' + time.strftime(
            '%Y-%m', (prev_year, prev_month, 1, 0, 0, 0, 0, 1, -1)
        )
        # 追加合并，避免覆盖丢失
        if os.path.exists(dfn):
            with open(self.baseFilename, 'rb') as f1:
                content = f1.read()
            with open(dfn, 'ab') as f2:
                f2.write(content)
            os.remove(self.baseFilename)
        else:
            os.rename(self.baseFilename, dfn)
        self.stream = open(self.baseFilename, 'a', encoding=self.encoding)
        self._current_year = now.tm_year
        self._current_month = now.tm_mon
        if self.backupCount > 0:
            for file_to_delete in self.getFilesToDelete():
                try:
                    os.remove(file_to_delete)
                except OSError:
                    pass

    def getFilesToDelete(self):
        """按月份后缀匹配并保留最近 backupCount 个归档"""
        dir_name, base_name = os.path.dirname(self.baseFilename), os.path.basename(self.baseFilename)
        file_names = os.listdir(dir_name)
        result = []
        for file_name in file_names:
            # 仅匹配 baseFilename.YYYY-MM 形式的归档，排除 .log 自身
            if file_name.startswith(base_name + '.') and len(file_name) == len(base_name) + 8:
                result.append(os.path.join(dir_name, file_name))
        if len(result) <= self.backupCount:
            return []
        result.sort(key=lambda x: os.path.getmtime(x))
        return result[:len(result) - self.backupCount]


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
