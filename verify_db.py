"""
验证数据库结构
"""

import sqlite3
from src.config import DATABASE

def verify_database():
    print('=' * 60)
    print('数据库结构验证')
    print('=' * 60)
    
    conn = sqlite3.connect(DATABASE['path'])
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print('数据库表:')
    for table in tables:
        print(f'  - {table[0]}')
    
    # 查看 trending_items 表结构
    print()
    print('trending_items 表结构:')
    cursor.execute('PRAGMA table_info(trending_items)')
    columns = cursor.fetchall()
    for col in columns:
        print(f'  {col[1]} ({col[2]})')
    
    # 查看 daily_stats 表结构
    print()
    print('daily_stats 表结构:')
    cursor.execute('PRAGMA table_info(daily_stats)')
    columns = cursor.fetchall()
    for col in columns:
        print(f'  {col[1]} ({col[2]})')
    
    # 查看 notifications 表结构
    print()
    print('notifications 表结构:')
    cursor.execute('PRAGMA table_info(notifications)')
    columns = cursor.fetchall()
    for col in columns:
        print(f'  {col[1]} ({col[2]})')
    
    conn.close()
    
    print()
    print('=' * 60)
    print('验证完成！')
    print('=' * 60)

if __name__ == '__main__':
    verify_database()
