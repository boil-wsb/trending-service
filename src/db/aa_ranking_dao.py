#!/usr/bin/env python3
"""
AA 模型排名快照 DAO（持久化缓存）

在 AA 配额烧穿 / 进程重启后仍需展示历史排名，因此把每次成功拉取的排名
持久化到 SQLite，读时「DB 优先、内存 _api_cache 兜底」。

表结构：
    aa_ranking_snapshot (
        category    TEXT NOT NULL,
        limit       INTEGER NOT NULL,
        models_json TEXT NOT NULL,   -- 完整 payload 的 JSON（含 models 列表）
        fetched_at  TEXT NOT NULL,   -- ISO 时间（用于时效判断与跨类别兜底取最新）
        PRIMARY KEY (category, limit)
    )
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from .database import Database


class AARankingDAO:
    """AA 模型排名快照 DAO"""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self._create_table()

    def _create_table(self):
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS aa_ranking_snapshot (
                category    TEXT NOT NULL,
                "limit"     INTEGER NOT NULL,
                models_json TEXT NOT NULL,
                fetched_at  TEXT NOT NULL,
                PRIMARY KEY (category, "limit")
            )
        ''')

    def upsert_snapshot(self, category: str, limit: int, payload: Dict):
        """写入（或覆盖）快照

        Args:
            category: 排名类别（general/code/agentic）
            limit: 展示条数（15/30）
            payload: fetcher 返回的完整 data dict（含 models 列表）
        """
        fetched_at = str(payload.get('fetched_at') or datetime.now().isoformat(timespec='seconds'))
        models_json = json.dumps(payload.get('models') or [], ensure_ascii=False)
        # UPSERT：同 (category, limit) 覆盖旧快照
        self.db.execute('''
            INSERT INTO aa_ranking_snapshot (category, "limit", models_json, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(category, "limit") DO UPDATE SET
                models_json = excluded.models_json,
                fetched_at  = excluded.fetched_at
        ''', (category, limit, models_json, fetched_at))

    def get_snapshot(self, category: str, limit: int) -> Optional[Dict]:
        """读取指定 (category, limit) 的快照 payload（dict 或 None）

        只重建 models 列表字段即可满足前端展示；无额外元信息则补默认。
        """
        row = self.db.fetch_one('''
            SELECT category, "limit", models_json, fetched_at
            FROM aa_ranking_snapshot
            WHERE category = ? AND "limit" = ?
        ''', (category, limit))
        return self._row_to_payload(row)

    def get_latest_by_limit(self, limit: int) -> Optional[Dict]:
        """读取「同 limit 下最近一次」的快照（跨类别兜底，避免切换类别白屏）

        对应原 _api_cache 中「同类 limit 下任意类别取最新」的回退逻辑。
        """
        row = self.db.fetch_one('''
            SELECT category, "limit", models_json, fetched_at
            FROM aa_ranking_snapshot
            WHERE "limit" = ?
            ORDER BY fetched_at DESC
            LIMIT 1
        ''', (limit,))
        return self._row_to_payload(row)

    def _row_to_payload(self, row) -> Optional[Dict]:
        if not row:
            return None
        category = row['category']
        limit = row['limit']
        try:
            models = json.loads(row['models_json'])
        except (TypeError, ValueError):
            models = []
        return {
            'models': models,
            'category': category,
            'ranked_at': None,       # AA 无时间戳
            'fetched_at': row['fetched_at'],
        }