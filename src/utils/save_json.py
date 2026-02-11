"""
JSON保存工具
提供统一的JSON文件保存功能
"""

import json
from pathlib import Path
from typing import Dict, Any


def save_json(data: Dict[str, Any], filepath: Path, ensure_ascii: bool = False, indent: int = 2) -> bool:
    """
    保存JSON数据到文件

    Args:
        data: 要保存的数据
        filepath: 文件路径
        ensure_ascii: 是否确保ASCII编码
        indent: 缩进空格数

    Returns:
        保存是否成功
    """
    try:
        # 确保目录存在
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON数据
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
        
        return True
    except Exception as e:
        print(f"保存JSON文件失败: {e}")
        return False