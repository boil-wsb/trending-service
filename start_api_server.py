#!/usr/bin/env python3
"""
启动 API 服务器

使用配置中的端口（默认 8000）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.scheduler import TrendingTaskScheduler
from src.api import APIServer
from src.utils import get_logger
from src.config import SERVER

logger = get_logger('api_server')
scheduler = TrendingTaskScheduler(logger=logger)

# 使用配置中的端口，不再硬编码
api_server = APIServer(scheduler, logger=logger)
api_server.start()

host = SERVER.get('host', 'localhost')
port = SERVER.get('port', 8000)

print(f'API 服务器已启动: http://{host}:{port}')
print(f'  - 获取状态: GET http://{host}:{port}/api/status')
print(f'  - 刷新数据源: POST http://{host}:{port}/api/refresh/<source>')
print(f'  - 刷新所有: POST http://{host}:{port}/api/refresh-all')
print('按 Ctrl+C 停止')

import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    api_server.stop()
    print('API 服务器已停止')
