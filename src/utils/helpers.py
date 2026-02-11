"""
辅助工具函数
"""

import json
from pathlib import Path
from typing import Any


def save_json(data: Any, filepath: Path) -> None:
    """
    保存数据到JSON文件

    Args:
        data: 要保存的数据
        filepath: 文件路径
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath: Path) -> Any:
    """
    从JSON文件加载数据

    Args:
        filepath: 文件路径

    Returns:
        加载的数据
    """
    if not filepath.exists():
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
