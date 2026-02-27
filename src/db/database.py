"""
数据库连接管理
"""

import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建表结构
        with self.get_connection() as conn:
            self._create_tables(conn)
            self._create_indexes(conn)
    
    def _create_tables(self, conn: sqlite3.Connection):
        """创建数据表"""
        cursor = conn.cursor()
        
        # 热点数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trending_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                category TEXT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                description TEXT,
                hot_score REAL,
                keywords TEXT,
                extra TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fetched_date DATE GENERATED ALWAYS AS (DATE(fetched_at)) STORED,
                UNIQUE(source, url, fetched_date)
            )
        ''')
        
        # 每日统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                source TEXT NOT NULL,
                total_count INTEGER DEFAULT 0,
                top_keywords TEXT,
                avg_hot_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, source)
            )
        ''')
        
        # 通知记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                content TEXT,
                sent_at TIMESTAMP,
                error_msg TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
    
    def _create_indexes(self, conn: sqlite3.Connection):
        """创建索引"""
        cursor = conn.cursor()
        
        # 热点数据表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trending_source 
            ON trending_items(source)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trending_date 
            ON trending_items(DATE(fetched_at))
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trending_fetched_at 
            ON trending_items(fetched_at)
        ''')
        
        # 每日统计表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_stats_date 
            ON daily_stats(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_stats_source 
            ON daily_stats(source)
        ''')
        
        conn.commit()
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """执行SQL语句"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, parameters)
            return cursor.rowcount
    
    def fetch_one(self, sql: str, parameters: tuple = ()) -> Optional[dict]:
        """查询单条记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, parameters)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def fetch_all(self, sql: str, parameters: tuple = ()) -> list:
        """查询多条记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, parameters)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_last_insert_id(self) -> int:
        """获取最后插入的ID"""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT last_insert_rowid()')
            return cursor.fetchone()[0]
