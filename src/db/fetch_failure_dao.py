#!/usr/bin/env python3
"""
数据获取失败记录 DAO

管理数据获取失败的记录和重试状态
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from .database import Database


class FailureStatus(Enum):
    """失败记录状态"""
    PENDING = "pending"      # 等待重试
    SUCCESS = "success"      # 重试成功
    FAILED = "failed"        # 最终失败（超过最大重试次数）


@dataclass
class FetchFailure:
    """数据获取失败记录"""
    id: Optional[int]
    source: str
    error_message: Optional[str]
    retry_count: int
    last_try_at: datetime
    next_retry_at: Optional[datetime]
    status: FailureStatus
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'source': self.source,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'last_try_at': self.last_try_at.isoformat() if self.last_try_at else None,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'status': self.status.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class FetchFailureDAO:
    """数据获取失败记录 DAO"""
    
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self._create_table()
    
    def _create_table(self):
        """创建失败记录表"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS fetch_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source VARCHAR(50) NOT NULL,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                last_try_at TIMESTAMP,
                next_retry_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_failures_source 
            ON fetch_failures(source)
        ''')
        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_failures_status 
            ON fetch_failures(status)
        ''')
        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_failures_next_retry 
            ON fetch_failures(next_retry_at)
        ''')
    
    def save_failure(self, source: str, error_message: Optional[str],
                     retry_count: int = 0, 
                     next_retry_at: Optional[datetime] = None) -> int:
        """
        保存或更新失败记录
        
        Args:
            source: 数据源名称
            error_message: 错误信息
            retry_count: 重试次数
            next_retry_at: 下次重试时间
            
        Returns:
            记录ID
        """
        now = datetime.now()
        
        # 检查是否已存在记录
        existing = self.get_by_source(source)
        
        if existing:
            # 更新现有记录
            self.db.execute('''
                UPDATE fetch_failures
                SET error_message = ?,
                    retry_count = ?,
                    last_try_at = ?,
                    next_retry_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE source = ? AND status = 'pending'
            ''', (
                error_message,
                retry_count,
                now,
                next_retry_at,
                'pending',
                now,
                source
            ))
            return existing.id
        else:
            # 插入新记录
            cursor = self.db.execute('''
                INSERT INTO fetch_failures
                (source, error_message, retry_count, last_try_at, next_retry_at, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                source,
                error_message,
                retry_count,
                now,
                next_retry_at,
                'pending',
                now
            ))
            return cursor.lastrowid
    
    def mark_success(self, source: str) -> bool:
        """
        标记数据源重试成功
        
        Args:
            source: 数据源名称
            
        Returns:
            是否成功更新
        """
        now = datetime.now()
        cursor = self.db.execute('''
            UPDATE fetch_failures
            SET status = 'success',
                updated_at = ?
            WHERE source = ? AND status = 'pending'
        ''', (now, source))
        return cursor.rowcount > 0
    
    def mark_failed(self, source: str) -> bool:
        """
        标记数据源最终失败（超过最大重试次数）
        
        Args:
            source: 数据源名称
            
        Returns:
            是否成功更新
        """
        now = datetime.now()
        cursor = self.db.execute('''
            UPDATE fetch_failures
            SET status = 'failed',
                updated_at = ?
            WHERE source = ? AND status = 'pending'
        ''', (now, source))
        return cursor.rowcount > 0
    
    def get_by_source(self, source: str) -> Optional[FetchFailure]:
        """
        根据数据源名称获取失败记录
        
        Args:
            source: 数据源名称
            
        Returns:
            失败记录，如果不存在则返回None
        """
        row = self.db.fetch_one('''
            SELECT id, source, error_message, retry_count, last_try_at,
                   next_retry_at, status, created_at, updated_at
            FROM fetch_failures
            WHERE source = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (source,))
        
        if row:
            return self._row_to_failure(row)
        return None
    
    def get_pending_failures(self) -> List[FetchFailure]:
        """
        获取所有待重试的失败记录
        
        Returns:
            待重试的失败记录列表
        """
        rows = self.db.fetch_all('''
            SELECT id, source, error_message, retry_count, last_try_at,
                   next_retry_at, status, created_at, updated_at
            FROM fetch_failures
            WHERE status = 'pending'
            ORDER BY next_retry_at ASC
        ''')
        
        return [self._row_to_failure(row) for row in rows]
    
    def get_ready_to_retry(self, limit: int = 10) -> List[FetchFailure]:
        """
        获取已到重试时间的失败记录
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            已到重试时间的失败记录列表
        """
        now = datetime.now()
        rows = self.db.fetch_all('''
            SELECT id, source, error_message, retry_count, last_try_at,
                   next_retry_at, status, created_at, updated_at
            FROM fetch_failures
            WHERE status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY next_retry_at ASC
            LIMIT ?
        ''', (now, limit))
        
        return [self._row_to_failure(row) for row in rows]
    
    def get_all_failures(self, status: Optional[str] = None,
                         limit: int = 100) -> List[FetchFailure]:
        """
        获取所有失败记录
        
        Args:
            status: 状态过滤（可选）
            limit: 返回记录数量限制
            
        Returns:
            失败记录列表
        """
        if status:
            rows = self.db.fetch_all('''
                SELECT id, source, error_message, retry_count, last_try_at,
                       next_retry_at, status, created_at, updated_at
                FROM fetch_failures
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (status, limit))
        else:
            rows = self.db.fetch_all('''
                SELECT id, source, error_message, retry_count, last_try_at,
                       next_retry_at, status, created_at, updated_at
                FROM fetch_failures
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (limit,))
        
        return [self._row_to_failure(row) for row in rows]
    
    def delete_old_failures(self, days: int = 7) -> int:
        """
        删除指定天数之前的失败记录
        
        Args:
            days: 天数
            
        Returns:
            删除的记录数
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        cursor = self.db.execute('''
            DELETE FROM fetch_failures
            WHERE updated_at < ?
        ''', (cutoff_date,))
        return cursor.rowcount
    
    def clear_all(self) -> int:
        """
        清空所有失败记录
        
        Returns:
            删除的记录数
        """
        cursor = self.db.execute('DELETE FROM fetch_failures')
        return cursor.rowcount
    
    def _row_to_failure(self, row: tuple) -> FetchFailure:
        """将数据库行转换为 FetchFailure 对象"""
        return FetchFailure(
            id=row[0],
            source=row[1],
            error_message=row[2],
            retry_count=row[3] or 0,
            last_try_at=row[4],
            next_retry_at=row[5],
            status=FailureStatus(row[6]) if row[6] else FailureStatus.PENDING,
            created_at=row[7],
            updated_at=row[8]
        )
