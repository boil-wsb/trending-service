"""
文件工具模块
提供文件操作相关的工具函数
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime


def ensure_dir(path: Path) -> Path:
    """
    确保目录存在，不存在则创建

    Args:
        path: 目录路径

    Returns:
        目录路径
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(data: Dict, filepath: Path, indent: int = 2, ensure_ascii: bool = False) -> None:
    """
    保存数据到JSON文件

    Args:
        data: 要保存的数据
        filepath: 文件路径
        indent: JSON缩进
        ensure_ascii: 是否确保ASCII编码
    """
    filepath = Path(filepath)
    ensure_dir(filepath.parent)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)


def load_json(filepath: Path) -> Dict:
    """
    从JSON文件加载数据

    Args:
        filepath: 文件路径

    Returns:
        加载的数据
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_timestamp(timestamp: str = None) -> str:
    """
    格式化时间戳

    Args:
        timestamp: 时间戳字符串，为空则使用当前时间

    Returns:
        格式化后的时间字符串
    """
    if timestamp is None:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp


def get_file_age(filepath: Path) -> int:
    """
    获取文件年龄（秒）

    Args:
        filepath: 文件路径

    Returns:
        文件年龄（秒）
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return -1

    return int(datetime.now().timestamp() - filepath.stat().st_mtime)