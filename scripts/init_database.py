"""
数据库初始化脚本
创建 SQLite 数据库文件和表结构
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import DATABASE
from src.db import TrendingDAO


def init_database():
    """初始化数据库"""
    db_path = DATABASE['path']
    
    print('=' * 60)
    print('数据库初始化')
    print('=' * 60)
    print(f'数据库路径: {db_path}')
    print()
    
    # 检查目录是否存在
    db_dir = db_path.parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
        print(f'✅ 创建目录: {db_dir}')
    else:
        print(f'✅ 目录已存在: {db_dir}')
    
    # 初始化数据库（会自动创建表结构）
    try:
        dao = TrendingDAO(db_path)
        print('✅ 数据库初始化成功')
        print('✅ 表结构创建成功')
    except Exception as e:
        print(f'❌ 数据库初始化失败: {e}')
        return False
    
    # 验证数据库文件
    if db_path.exists():
        file_size = db_path.stat().st_size
        print(f'✅ 数据库文件已生成: {db_path}')
        print(f'   文件大小: {file_size} bytes')
    else:
        print(f'❌ 数据库文件未生成')
        return False
    
    # 测试数据库连接
    try:
        count = dao.get_count()
        print(f'✅ 数据库连接正常')
        print(f'   当前数据量: {count} 条')
    except Exception as e:
        print(f'❌ 数据库连接失败: {e}')
        return False
    
    print()
    print('=' * 60)
    print('数据库初始化完成！')
    print('=' * 60)
    return True


if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
