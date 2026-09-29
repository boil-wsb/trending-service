# -*- coding: utf-8 -*-
"""8899 临时实例（e2e 验证用，绕过 Session 0 生产服务）。"""
import sys

sys.path.insert(0, r'D:\MYDATA\Include\trending-service')
from src.server import TrendingServer

TrendingServer(port=8899).start(blocking=True)
