"""
指数行情数据访问对象
"""

from datetime import datetime, date
from typing import List, Optional, Dict
from pathlib import Path

from .database import Database
from .models import IndexData


class IndexDAO:
    """指数行情数据访问对象"""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)

    def save_index(self, index: IndexData) -> int:
        """
        保存单条指数数据（upsert 逻辑）

        基于 code + source + fetched_date 去重：
        - 如果记录不存在，则插入新记录
        - 如果记录已存在，则更新行情字段

        Returns:
            保存的数据 id
        """
        fetched_at = index.fetched_at or datetime.now()
        fetched_date = fetched_at.date().isoformat()

        existing = self.db.fetch_one('''
            SELECT id FROM index_data
            WHERE code = ? AND source = ? AND fetched_date = ?
        ''', (index.code, index.source, fetched_date))

        if existing:
            self.db.execute('''
                UPDATE index_data SET
                    name = ?,
                    category = ?,
                    price = ?,
                    change = ?,
                    change_pct = ?,
                    high = ?,
                    low = ?,
                    open = ?,
                    pre_close = ?,
                    volume = ?,
                    amount = ?,
                    turnover_rate = ?,
                    fetched_at = ?
                WHERE id = ?
            ''', (
                index.name,
                index.category,
                index.price,
                index.change,
                index.change_pct,
                index.high,
                index.low,
                index.open,
                index.pre_close,
                index.volume,
                index.amount,
                index.turnover_rate,
                fetched_at,
                existing['id']
            ))
            return existing['id']
        else:
            self.db.execute('''
                INSERT INTO index_data (
                    code, name, category, price, change, change_pct,
                    high, low, open, pre_close, volume, amount,
                    turnover_rate, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                index.code,
                index.name,
                index.category,
                index.price,
                index.change,
                index.change_pct,
                index.high,
                index.low,
                index.open,
                index.pre_close,
                index.volume,
                index.amount,
                index.turnover_rate,
                index.source,
                fetched_at
            ))
            return self.db.get_last_insert_id()

    def save_indices(self, indices: List[IndexData]) -> int:
        """
        批量保存指数数据

        Returns:
            保存的数据条数
        """
        if not indices:
            return 0

        saved_count = 0
        for index in indices:
            try:
                self.save_index(index)
                saved_count += 1
            except Exception as e:
                raise e

        return saved_count

    def _row_to_index(self, row: Dict) -> IndexData:
        """将数据库行转换为 IndexData 对象"""
        fetched_at = row.get('fetched_at')
        if isinstance(fetched_at, str):
            try:
                fetched_at = datetime.fromisoformat(fetched_at)
            except ValueError:
                fetched_at = datetime.now()

        return IndexData(
            id=row.get('id'),
            code=row.get('code', ''),
            name=row.get('name', ''),
            category=row.get('category', 'market'),
            price=row.get('price', 0.0),
            change=row.get('change', 0.0),
            change_pct=row.get('change_pct', 0.0),
            high=row.get('high', 0.0),
            low=row.get('low', 0.0),
            open=row.get('open', 0.0),
            pre_close=row.get('pre_close', 0.0),
            volume=row.get('volume', 0),
            amount=row.get('amount', 0.0),
            turnover_rate=row.get('turnover_rate', 0.0),
            source=row.get('source', 'eastmoney'),
            fetched_at=fetched_at or datetime.now()
        )

    def _get_latest_date(self) -> Optional[str]:
        """获取最新数据日期 (YYYY-MM-DD)"""
        row = self.db.fetch_one('''
            SELECT DISTINCT fetched_date FROM index_data
            ORDER BY fetched_date DESC
            LIMIT 1
        ''')
        return row['fetched_date'] if row else None

    def get_latest(self, category: Optional[str] = None, limit: int = 100) -> List[IndexData]:
        """
        获取最新日期的指数数据

        Args:
            category: 分类筛选 (market/industry)，None 表示全部
            limit: 返回数量上限

        Returns:
            指数数据列表
        """
        latest_date = self._get_latest_date()
        if not latest_date:
            return []

        params: list = [latest_date]
        sql = '''
            SELECT * FROM index_data
            WHERE fetched_date = ?
        '''
        if category:
            sql += ' AND category = ?'
            params.append(category)
        sql += ' ORDER BY change_pct DESC LIMIT ?'
        params.append(limit)

        rows = self.db.fetch_all(sql, tuple(params))
        return [self._row_to_index(row) for row in rows]

    def get_market_indices(self, limit: int = 50) -> List[IndexData]:
        """获取最新日期的市场指数（category='market'）"""
        return self.get_latest(category='market', limit=limit)

    def get_industry_indices(self, limit: int = 50) -> List[IndexData]:
        """获取最新日期的行业指数（category='industry'）"""
        return self.get_latest(category='industry', limit=limit)

    def get_industry_indices_with_changes(self, limit: int = 200) -> List[IndexData]:
        """
        获取最新日期的行业指数，并计算 3日/7日 涨跌幅

        优先从 index_kline 表（K线缓存）获取历史收盘价计算涨跌幅，
        因为 K 线缓存通常有更多历史数据（每日缓存 365 天）。
        如果 K 线缓存不足，则回退到 index_data 表的每日快照。

        Args:
            limit: 返回数量上限

        Returns:
            带有 change_pct_3d 和 change_pct_7d 的指数数据列表
        """
        # 1. 获取最新日期的行业指数
        indices = self.get_industry_indices(limit=limit)
        if not indices:
            return indices

        # 2. 尝试从 K 线缓存计算多日涨跌幅
        # 获取所有行业指数的代码列表
        codes = [idx.code for idx in indices]

        # 查询每个指数最近 8 个交易日的收盘价
        # 使用窗口函数一次性获取所有数据
        try:
            # 先获取最近 8 个交易日
            date_rows = self.db.fetch_all('''
                SELECT DISTINCT date FROM index_kline
                ORDER BY date DESC LIMIT 8
            ''')
            kline_dates = [r['date'] for r in date_rows]

            if len(kline_dates) >= 4:
                # 批量查询所有指数在这些日期的收盘价
                # date_3d_ago 是第 4 个日期（索引 3），date_7d_ago 是第 8 个日期（索引 7）
                date_3d_ago = kline_dates[3]
                date_7d_ago = kline_dates[7] if len(kline_dates) >= 8 else None

                # 查询 3 日前的收盘价
                placeholders = ','.join('?' * len(codes))
                prices_3d = {}
                if date_3d_ago:
                    rows_3d = self.db.fetch_all(
                        f'SELECT code, close FROM index_kline WHERE date = ? AND code IN ({placeholders})',
                        (date_3d_ago, *codes)
                    )
                    for r in rows_3d:
                        prices_3d[r['code']] = r['close']

                # 查询 7 日前的收盘价
                prices_7d = {}
                if date_7d_ago:
                    rows_7d = self.db.fetch_all(
                        f'SELECT code, close FROM index_kline WHERE date = ? AND code IN ({placeholders})',
                        (date_7d_ago, *codes)
                    )
                    for r in rows_7d:
                        prices_7d[r['code']] = r['close']

                # 计算涨跌幅
                for idx in indices:
                    # 3日涨跌幅
                    close_3d = prices_3d.get(idx.code)
                    if close_3d and close_3d > 0:
                        idx.change_pct_3d = round((idx.price - close_3d) / close_3d * 100, 2)
                    else:
                        idx.change_pct_3d = None

                    # 7日涨跌幅
                    close_7d = prices_7d.get(idx.code)
                    if close_7d and close_7d > 0:
                        idx.change_pct_7d = round((idx.price - close_7d) / close_7d * 100, 2)
                    else:
                        idx.change_pct_7d = None

                return indices
        except Exception:
            pass

        # 3. K 线缓存不足，回退到 index_data 表的每日快照
        date_rows = self.db.fetch_all('''
            SELECT DISTINCT fetched_date FROM index_data
            WHERE category = 'industry'
            ORDER BY fetched_date DESC
            LIMIT 8
        ''')
        dates = [r['fetched_date'] for r in date_rows]

        if len(dates) < 4:
            return indices

        date_3d_ago = dates[3]
        date_7d_ago = dates[7] if len(dates) >= 8 else None

        # 批量查询 3 日前的价格
        prices_3d = {}
        rows_3d = self.db.fetch_all('''
            SELECT code, price FROM index_data
            WHERE fetched_date = ? AND category = 'industry'
        ''', (date_3d_ago,))
        for r in rows_3d:
            prices_3d[r['code']] = r['price']

        # 批量查询 7 日前的价格
        prices_7d = {}
        if date_7d_ago:
            rows_7d = self.db.fetch_all('''
                SELECT code, price FROM index_data
                WHERE fetched_date = ? AND category = 'industry'
            ''', (date_7d_ago,))
            for r in rows_7d:
                prices_7d[r['code']] = r['price']

        # 计算涨跌幅
        for idx in indices:
            price_3d = prices_3d.get(idx.code)
            if price_3d and price_3d > 0:
                idx.change_pct_3d = round((idx.price - price_3d) / price_3d * 100, 2)
            else:
                idx.change_pct_3d = None

            price_7d = prices_7d.get(idx.code)
            if price_7d and price_7d > 0:
                idx.change_pct_7d = round((idx.price - price_7d) / price_7d * 100, 2)
            else:
                idx.change_pct_7d = None

        return indices

    def get_index_by_code(self, code: str, limit: int = 30) -> List[IndexData]:
        """
        按指数代码获取历史数据

        Args:
            code: 指数代码
            limit: 返回数量上限

        Returns:
            历史指数数据列表（按时间倒序）
        """
        rows = self.db.fetch_all('''
            SELECT * FROM index_data
            WHERE code = ?
            ORDER BY fetched_at DESC
            LIMIT ?
        ''', (code, limit))
        return [self._row_to_index(row) for row in rows]

    # ===== K 线数据缓存方法 =====

    def save_klines(self, code: str, klines: List[Dict], source: str = 'tx') -> int:
        """
        保存指数 K 线数据到数据库（upsert 逻辑）

        Args:
            code: 指数代码
            klines: K 线数据列表，每条包含 date/open/close/high/low/volume/amount/change/change_pct
            source: 数据源标识

        Returns:
            保存的数据条数
        """
        if not klines:
            return 0

        saved = 0
        from datetime import datetime
        now = datetime.now().isoformat()

        for k in klines:
            try:
                date_str = str(k.get('date', ''))
                if not date_str:
                    continue

                existing = self.db.fetch_one(
                    'SELECT id FROM index_kline WHERE code = ? AND date = ? AND source = ?',
                    (code, date_str, source)
                )

                if existing:
                    self.db.execute('''
                        UPDATE index_kline SET
                            open = ?, close = ?, high = ?, low = ?,
                            volume = ?, amount = ?, change = ?, change_pct = ?,
                            updated_at = ?
                        WHERE id = ?
                    ''', (
                        float(k.get('open', 0) or 0),
                        float(k.get('close', 0) or 0),
                        float(k.get('high', 0) or 0),
                        float(k.get('low', 0) or 0),
                        int(float(k.get('volume', 0) or 0)),
                        float(k.get('amount', 0) or 0),
                        float(k.get('change', 0) or 0),
                        float(k.get('change_pct', 0) or 0),
                        now,
                        existing['id']
                    ))
                else:
                    self.db.execute('''
                        INSERT INTO index_kline (
                            code, date, open, close, high, low,
                            volume, amount, change, change_pct, source, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        code, date_str,
                        float(k.get('open', 0) or 0),
                        float(k.get('close', 0) or 0),
                        float(k.get('high', 0) or 0),
                        float(k.get('low', 0) or 0),
                        int(float(k.get('volume', 0) or 0)),
                        float(k.get('amount', 0) or 0),
                        float(k.get('change', 0) or 0),
                        float(k.get('change_pct', 0) or 0),
                        source, now
                    ))
                saved += 1
            except (ValueError, KeyError, TypeError) as e:
                continue

        return saved

    def get_klines(self, code: str, days: int = 30, source: str = 'tx') -> List[Dict]:
        """
        从数据库获取指数 K 线缓存数据

        Args:
            code: 指数代码
            days: 返回最近 N 天的数据
            source: 数据源标识

        Returns:
            K 线数据列表（按日期升序），每条包含 date/open/close/high/low/volume/amount/change/change_pct
        """
        rows = self.db.fetch_all('''
            SELECT date, open, close, high, low, volume, amount, change, change_pct
            FROM index_kline
            WHERE code = ? AND source = ?
            ORDER BY date DESC
            LIMIT ?
        ''', (code, source, days))

        if not rows:
            return []

        # 转换为字典列表并按日期升序排列（前端图表需要）
        result = []
        for row in reversed(rows):  # 反转为升序
            result.append({
                'date': row['date'],
                'open': row['open'],
                'close': row['close'],
                'high': row['high'],
                'low': row['low'],
                'volume': row['volume'],
                'amount': row['amount'],
                'change': row['change'],
                'change_pct': row['change_pct'],
            })
        return result

    def get_kline_latest_date(self, code: str, source: str = 'tx') -> Optional[str]:
        """获取 K 线缓存的最新日期"""
        row = self.db.fetch_one(
            'SELECT MAX(date) as latest FROM index_kline WHERE code = ? AND source = ?',
            (code, source)
        )
        return row['latest'] if row and row['latest'] else None
