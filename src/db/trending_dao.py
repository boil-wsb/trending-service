"""
热点数据访问对象
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Dict
from pathlib import Path

from .database import Database
from .models import TrendingItem, DailyStats


class TrendingDAO:
    """热点数据访问对象"""
    
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
    
    def save_items(self, items: List[TrendingItem]) -> int:
        """
        批量保存热点数据（已存在的会更新）

        Args:
            items: 热点数据列表

        Returns:
            保存的数据条数
        """
        if not items:
            return 0

        import json

        saved_count = 0
        for item in items:
            try:
                # 使用 INSERT OR REPLACE 更新已存在的数据
                self.db.execute('''
                    INSERT OR REPLACE INTO trending_items
                    (source, category, title, url, author, description, hot_score, keywords, extra, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item.source,
                    item.category,
                    item.title,
                    item.url,
                    item.author,
                    item.description,
                    item.hot_score,
                    ','.join(item.keywords) if item.keywords else '',
                    json.dumps(item.extra, ensure_ascii=False) if item.extra else '{}',
                    item.fetched_at or datetime.now()
                ))
                saved_count += 1
            except Exception as e:
                # 记录错误但继续处理其他数据
                continue

        return saved_count

    def refresh_items(self, items: List[TrendingItem]) -> int:
        """
        刷新热点数据 - 先删除旧数据再插入新数据
        用于需要完全重新获取数据的场景

        Args:
            items: 热点数据列表

        Returns:
            保存的数据条数
        """
        if not items:
            return 0

        from datetime import date
        import json

        # 按数据源和日期分组
        from collections import defaultdict
        items_by_source = defaultdict(list)
        for item in items:
            items_by_source[item.source].append(item)

        saved_count = 0
        today = date.today()

        for source, source_items in items_by_source.items():
            try:
                # 删除该数据源今天的旧数据
                self.db.execute('''
                    DELETE FROM trending_items
                    WHERE source = ? AND DATE(fetched_at) = ?
                ''', (source, today.isoformat()))

                # 插入新数据
                for item in source_items:
                    try:
                        self.db.execute('''
                            INSERT INTO trending_items
                            (source, category, title, url, author, description, hot_score, keywords, extra, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            item.source,
                            item.category,
                            item.title,
                            item.url,
                            item.author,
                            item.description,
                            item.hot_score,
                            ','.join(item.keywords) if item.keywords else '',
                            json.dumps(item.extra, ensure_ascii=False) if item.extra else '{}',
                            item.fetched_at or datetime.now()
                        ))
                        saved_count += 1
                    except Exception as e:
                        # 记录错误但继续处理其他数据
                        print(f"保存数据失败: {e}, title={item.title[:30]}")
                        continue
            except Exception as e:
                # 记录错误但继续处理其他数据源
                print(f"处理数据源 {source} 失败: {e}")
                continue

        return saved_count
    
    def get_items(
        self,
        source: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        keyword: Optional[str] = None,
        limit: int = 100
    ) -> List[TrendingItem]:
        """
        查询热点数据
        
        Args:
            source: 数据源筛选
            start_date: 开始日期
            end_date: 结束日期
            keyword: 关键词搜索
            limit: 返回数量限制
            
        Returns:
            热点数据列表
        """
        conditions = []
        params = []
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        
        if start_date:
            conditions.append("DATE(fetched_at) >= ?")
            params.append(start_date.isoformat())
        
        if end_date:
            conditions.append("DATE(fetched_at) <= ?")
            params.append(end_date.isoformat())
        
        if keyword:
            conditions.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f'''
            SELECT * FROM trending_items
            WHERE {where_clause}
            ORDER BY fetched_at DESC
            LIMIT ?
        '''
        params.append(limit)
        
        rows = self.db.fetch_all(sql, tuple(params))
        return [TrendingItem.from_dict(row) for row in rows]
    
    def get_item_by_id(self, item_id: int) -> Optional[TrendingItem]:
        """根据ID获取热点数据"""
        row = self.db.fetch_one(
            'SELECT * FROM trending_items WHERE id = ?',
            (item_id,)
        )
        return TrendingItem.from_dict(row) if row else None
    
    def get_daily_stats(
        self,
        days: int = 7,
        source: Optional[str] = None
    ) -> List[DailyStats]:
        """
        获取每日统计数据
        
        Args:
            days: 最近N天
            source: 数据源筛选
            
        Returns:
            每日统计列表
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        if source:
            rows = self.db.fetch_all('''
                SELECT * FROM daily_stats
                WHERE date >= ? AND date <= ? AND source = ?
                ORDER BY date DESC
            ''', (start_date.isoformat(), end_date.isoformat(), source))
        else:
            rows = self.db.fetch_all('''
                SELECT * FROM daily_stats
                WHERE date >= ? AND date <= ?
                ORDER BY date DESC
            ''', (start_date.isoformat(), end_date.isoformat()))
        
        return [DailyStats.from_dict(row) for row in rows]
    
    def save_daily_stats(self, stats: DailyStats) -> bool:
        """保存每日统计"""
        try:
            self.db.execute('''
                INSERT OR REPLACE INTO daily_stats
                (date, source, total_count, top_keywords, avg_hot_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                stats.date.isoformat(),
                stats.source,
                stats.total_count,
                str(stats.top_keywords),
                stats.avg_hot_score
            ))
            return True
        except Exception as e:
            return False
    
    def get_trending_keywords(
        self,
        days: int = 7,
        top_n: int = 20
    ) -> List[Dict[str, any]]:
        """
        获取热门关键词统计
        
        Args:
            days: 统计天数
            top_n: 返回前N个
            
        Returns:
            关键词统计列表
        """
        start_date = date.today() - timedelta(days=days)
        
        # 获取所有关键词
        rows = self.db.fetch_all('''
            SELECT keywords FROM trending_items
            WHERE DATE(fetched_at) >= ? AND keywords IS NOT NULL AND keywords != ''
        ''', (start_date.isoformat(),))
        
        # 统计词频
        keyword_counts = {}
        for row in rows:
            keywords_str = row.get('keywords', '')
            if keywords_str:
                keywords = keywords_str.split(',')
                for kw in keywords:
                    kw = kw.strip()
                    if kw:
                        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        # 排序并返回前N个
        sorted_keywords = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        return [
            {'keyword': kw, 'count': count}
            for kw, count in sorted_keywords
        ]
    
    def delete_old_data(self, days: int = 30) -> int:
        """
        清理过期数据
        
        Args:
            days: 保留最近N天的数据
            
        Returns:
            删除的数据条数
        """
        cutoff_date = date.today() - timedelta(days=days)
        
        # 删除旧的热点数据
        deleted_items = self.db.execute(
            'DELETE FROM trending_items WHERE DATE(fetched_at) < ?',
            (cutoff_date.isoformat(),)
        )
        
        # 删除旧的统计数据
        deleted_stats = self.db.execute(
            'DELETE FROM daily_stats WHERE date < ?',
            (cutoff_date.isoformat(),)
        )
        
        return deleted_items + deleted_stats
    
    def get_sources(self) -> List[str]:
        """获取所有数据源列表"""
        rows = self.db.fetch_all(
            'SELECT DISTINCT source FROM trending_items ORDER BY source'
        )
        return [row['source'] for row in rows]
    
    def get_count(
        self,
        source: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> int:
        """获取数据总数"""
        conditions = []
        params = []
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        
        if start_date:
            conditions.append("DATE(fetched_at) >= ?")
            params.append(start_date.isoformat())
        
        if end_date:
            conditions.append("DATE(fetched_at) <= ?")
            params.append(end_date.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        row = self.db.fetch_one(
            f'SELECT COUNT(*) as count FROM trending_items WHERE {where_clause}',
            tuple(params)
        )
        return row['count'] if row else 0
    
    def get_hourly_distribution(
        self,
        days: int = 1,
        source: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """
        获取按小时分布的数据统计
        
        Args:
            days: 统计最近N天
            source: 数据源筛选
            
        Returns:
            每小时的数据量和平均热度列表
        """
        start_date = datetime.now() - timedelta(days=days)
        
        conditions = ["fetched_at >= ?"]
        params = [start_date.isoformat()]
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        
        where_clause = " AND ".join(conditions)
        
        rows = self.db.fetch_all(f'''
            SELECT 
                CAST(strftime('%H', fetched_at) AS INTEGER) as hour,
                COUNT(*) as count,
                AVG(hot_score) as avg_hot_score,
                SUM(hot_score) as total_hot_score
            FROM trending_items
            WHERE {where_clause}
            GROUP BY hour
            ORDER BY hour
        ''', tuple(params))
        
        # 转换为24小时格式，没有数据的小时填充0
        result = []
        hour_map = {row['hour']: row for row in rows}
        
        for hour in range(24):
            if hour in hour_map:
                result.append({
                    'hour': hour,
                    'count': hour_map[hour]['count'],
                    'avg_hot_score': round(hour_map[hour]['avg_hot_score'] or 0, 2),
                    'total_hot_score': round(hour_map[hour]['total_hot_score'] or 0, 2)
                })
            else:
                result.append({
                    'hour': hour,
                    'count': 0,
                    'avg_hot_score': 0,
                    'total_hot_score': 0
                })
        
        return result
    
    def get_trending_by_hour(
        self,
        hours: int = 6
    ) -> List[Dict[str, any]]:
        """
        获取最近N小时的趋势数据
        
        Args:
            hours: 最近N小时
            
        Returns:
            每小时的统计数据
        """
        start_time = datetime.now() - timedelta(hours=hours)
        
        rows = self.db.fetch_all('''
            SELECT 
                strftime('%Y-%m-%d %H:00', fetched_at) as time_slot,
                COUNT(*) as count,
                AVG(hot_score) as avg_hot_score
            FROM trending_items
            WHERE fetched_at >= ?
            GROUP BY time_slot
            ORDER BY time_slot
        ''', (start_time.isoformat(),))
        
        return [
            {
                'time': row['time_slot'],
                'count': row['count'],
                'avg_hot_score': round(row['avg_hot_score'] or 0, 2)
            }
            for row in rows
        ]
