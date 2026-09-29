# -*- coding: utf-8 -*-
"""重生成 /report.html（前端片段更新后必须重生成才生效）。"""
import sys

sys.path.insert(0, r'D:\MYDATA\Include\trending-service')
from src.utils.report_generator import ReportGenerator

path = ReportGenerator().generate_report()
print(f'report regenerated: {path}')
