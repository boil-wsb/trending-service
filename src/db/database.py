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
            # 启用 WAL 模式：多线程并发读写时不再触发 SQLite C 扩展 access violation
            # （曾出现 Windows fatal exception: access violation 于频繁 connect/close 场景）
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')  # WAL 下 NORMAL 已足够安全，减少 fsync
            conn.execute('PRAGMA busy_timeout=5000')   # 写锁等待 5 秒，避免 SQLITE_BUSY
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

        # 指数行情数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'market',
                price REAL DEFAULT 0,
                change REAL DEFAULT 0,
                change_pct REAL DEFAULT 0,
                high REAL DEFAULT 0,
                low REAL DEFAULT 0,
                open REAL DEFAULT 0,
                pre_close REAL DEFAULT 0,
                volume INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                turnover_rate REAL DEFAULT 0,
                source TEXT DEFAULT 'eastmoney',
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fetched_date DATE GENERATED ALWAYS AS (DATE(fetched_at)) STORED,
                UNIQUE(code, source, fetched_date)
            )
        ''')

        # 指数K线历史数据表（每日缓存）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_kline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL DEFAULT 0,
                close REAL DEFAULT 0,
                high REAL DEFAULT 0,
                low REAL DEFAULT 0,
                volume INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                change REAL DEFAULT 0,
                change_pct REAL DEFAULT 0,
                source TEXT DEFAULT 'tx',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, date, source)
            )
        ''')

        # 迁移：为 index_data 表添加 market_cap 列（概念板块总市值，单位：元）
        try:
            cursor.execute("SELECT market_cap FROM index_data LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE index_data ADD COLUMN market_cap REAL DEFAULT 0.0")

        # 市场情绪涨跌停统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS limit_up_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                limit_up_count INTEGER DEFAULT 0,
                limit_down_count INTEGER DEFAULT 0,
                broken_limit_count INTEGER DEFAULT 0,
                broken_rate REAL DEFAULT 0,
                max_consecutive INTEGER DEFAULT 0,
                sentiment_score REAL DEFAULT 0,
                consecutive_tiers TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')

        # 北向资金每日净流入表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS northbound_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                sh_net_buy REAL DEFAULT 0,
                sz_net_buy REAL DEFAULT 0,
                total_net_buy REAL DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')

        # VIX / VXN 波动率指数表（恐慌指数，近一年日频）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vix_vxn (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                vix REAL DEFAULT NULL,
                vxn REAL DEFAULT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
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
        # 跨日去重查询加速：extra.hn_id 是同一帖子跨日最稳定的标识
        # （历史数据已证实同 hn_id 会出现标题被编辑的情况，故 title 不可作为稳定键）
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trending_hn_id
            ON trending_items(json_extract(extra, '$.hn_id'))
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

        # 指数行情数据表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_index_code
            ON index_data(code)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_index_category
            ON index_data(category)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_index_fetched_at
            ON index_data(fetched_at)
        ''')

        # 指数K线数据表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_kline_code
            ON index_kline(code)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_kline_date
            ON index_kline(date)
        ''')

        conn.commit()
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）

        每次 connect/close 频繁调用会在 Windows 多线程下触发 SQLite C 扩展
        access violation。已启用 WAL + busy_timeout 缓解，批量操作请改用
        transaction() 在单连接内完成，避免高频 connect/close。
        """
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        # 每连接设置 PRAGMA（WAL 模式持久化在数据库文件，但其他 PRAGMA 每连接需重设）
        conn.execute('PRAGMA busy_timeout=5000')
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """获取单连接用于批量事务（避免高频 connect/close 触发段错误）

        用法：
            with db.transaction() as conn:
                for item in items:
                    conn.execute(sql, params)
        """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=10000')
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

    def execute_returning_id(self, sql: str, parameters: tuple = ()) -> int:
        """执行 INSERT 并返回新记录的 ID（同一连接内获取 lastrowid）"""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, parameters)
            return cursor.lastrowid

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
