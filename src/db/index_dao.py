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

        amount/market_cap 特殊处理：
        新值为 0 时保留旧值（接口返回 0 通常是缺失值，非真 0；
        避免概念板块 ths 源反爬失败时 em 源 amount=0 覆盖已合并的数据）。

        Returns:
            保存的数据 id
        """
        fetched_at = index.fetched_at or datetime.now()

        # 使用 UPSERT (ON CONFLICT) 原子操作，消除竞态条件
        self.db.execute('''
            INSERT INTO index_data (
                code, name, category, price, change, change_pct,
                high, low, open, pre_close, volume, amount,
                turnover_rate, market_cap, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, source, fetched_date) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                price = excluded.price,
                change = excluded.change,
                change_pct = excluded.change_pct,
                high = excluded.high,
                low = excluded.low,
                open = excluded.open,
                pre_close = excluded.pre_close,
                volume = excluded.volume,
                amount = CASE WHEN excluded.amount != 0 THEN excluded.amount ELSE index_data.amount END,
                turnover_rate = excluded.turnover_rate,
                market_cap = CASE WHEN excluded.market_cap > 0 THEN excluded.market_cap ELSE index_data.market_cap END,
                fetched_at = excluded.fetched_at
        ''', (
            index.code, index.name, index.category, index.price, index.change,
            index.change_pct, index.high, index.low, index.open, index.pre_close,
            index.volume, index.amount, index.turnover_rate, index.market_cap,
            index.source, fetched_at
        ))

        # 获取记录 ID（UPSERT 后查询，使用同一 fetched_date）
        fetched_date = fetched_at.date().isoformat()
        row = self.db.fetch_one(
            'SELECT id FROM index_data WHERE code = ? AND source = ? AND fetched_date = ?',
            (index.code, index.source, fetched_date)
        )
        return row['id'] if row else 0

    def save_indices(self, indices: List[IndexData]) -> int:
        """
        批量保存指数数据（单连接批量事务）

        关键修复：原实现循环调用 save_index，每条记录 2 次 connect/close
        （execute + fetch_one），在 Windows 多线程下高频创建/销毁 SQLite
        连接触发 C 扩展 access violation（Windows fatal exception）。
        改为单连接批量事务，connect/close 从 2N 降到 1，彻底消除段错误。

        Returns:
            保存的数据条数
        """
        if not indices:
            return 0

        upsert_sql = '''
            INSERT INTO index_data (
                code, name, category, price, change, change_pct,
                high, low, open, pre_close, volume, amount,
                turnover_rate, market_cap, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, source, fetched_date) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                price = excluded.price,
                change = excluded.change,
                change_pct = excluded.change_pct,
                high = excluded.high,
                low = excluded.low,
                open = excluded.open,
                pre_close = excluded.pre_close,
                volume = excluded.volume,
                amount = CASE WHEN excluded.amount != 0 THEN excluded.amount ELSE index_data.amount END,
                turnover_rate = excluded.turnover_rate,
                market_cap = CASE WHEN excluded.market_cap > 0 THEN excluded.market_cap ELSE index_data.market_cap END,
                fetched_at = excluded.fetched_at
        '''
        select_sql = 'SELECT id FROM index_data WHERE code = ? AND source = ? AND fetched_date = ?'

        saved_count = 0
        # 单连接批量事务：connect/close 仅 1 次，彻底避免高频连接导致的段错误
        with self.db.transaction() as conn:
            for index in indices:
                fetched_at = index.fetched_at or datetime.now()
                conn.execute(upsert_sql, (
                    index.code, index.name, index.category, index.price, index.change,
                    index.change_pct, index.high, index.low, index.open, index.pre_close,
                    index.volume, index.amount, index.turnover_rate, index.market_cap,
                    index.source, fetched_at
                ))
                saved_count += 1

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
            market_cap=row.get('market_cap', 0.0),
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

        取每个 code 的最新一条记录（按 fetched_at 降序），避免：
        1. 某个数据源当天抓取失败时该类指数整体消失
           （如申万行业指数 akshare 源接口异常时仍可显示昨日数据）
        2. 同一概念板块在 em/ths 两个源都有数据时重复显示

        Args:
            category: 分类筛选 (market/industry)，None 表示全部
            limit: 返回数量上限

        Returns:
            指数数据列表
        """
        params: list = []
        sql = '''
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY code ORDER BY fetched_at DESC
                ) as rn
                FROM index_data
                WHERE 1=1
            '''
        if category:
            sql += ' AND category = ?'
            params.append(category)
        sql += ') WHERE rn = 1 ORDER BY change_pct DESC LIMIT ?'
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

        先查询全部行业指数（不 limit），计算多日涨跌幅，按今日涨跌幅降序排序后再 limit。
        优先从 index_kline 表（K线缓存）获取历史收盘价计算涨跌幅，
        如果 K 线缓存不足，则回退到 index_data 表的每日快照。

        Args:
            limit: 返回数量上限（排序后截取）

        Returns:
            带有 change_pct_3d 和 change_pct_7d 的指数数据列表
        """
        # 1. 获取最新日期的全部行业指数（不限制数量，先查全部再排序后截取）
        indices = self.get_industry_indices(limit=10000)
        if not indices:
            return indices

        # 2. 尝试从 K 线缓存计算多日涨跌幅
        # 获取所有行业指数的代码列表
        codes = [idx.code for idx in indices]

        # 查询每个指数最近 8 个交易日的收盘价
        # 按 source 匹配，避免不同数据源价格尺度不一致导致涨跌幅异常
        try:
            # 先获取最近 8 个交易日
            date_rows = self.db.fetch_all('''
                SELECT DISTINCT date FROM index_kline
                ORDER BY date DESC LIMIT 8
            ''')
            kline_dates = [r['date'] for r in date_rows]

            if len(kline_dates) >= 4:
                # date_3d_ago 是第 4 个日期（索引 3），date_7d_ago 是第 8 个日期（索引 7）
                date_3d_ago = kline_dates[3]
                date_7d_ago = kline_dates[7] if len(kline_dates) >= 8 else None

                placeholders = ','.join('?' * len(codes))

                # 查询 3 日前的收盘价（带 source，构建 (code, source) -> close 映射）
                prices_3d = {}
                if date_3d_ago:
                    rows_3d = self.db.fetch_all(
                        f'SELECT code, close, source FROM index_kline WHERE date = ? AND code IN ({placeholders})',
                        (date_3d_ago, *codes)
                    )
                    for r in rows_3d:
                        prices_3d[(r['code'], r['source'])] = r['close']

                # 查询 7 日前的收盘价
                prices_7d = {}
                if date_7d_ago:
                    rows_7d = self.db.fetch_all(
                        f'SELECT code, close, source FROM index_kline WHERE date = ? AND code IN ({placeholders})',
                        (date_7d_ago, *codes)
                    )
                    for r in rows_7d:
                        prices_7d[(r['code'], r['source'])] = r['close']

                # 按 (code, source) 匹配计算涨跌幅，确保同一数据源价格对比
                for idx in indices:
                    close_3d = prices_3d.get((idx.code, idx.source))
                    if close_3d and close_3d > 0:
                        idx.change_pct_3d = round((idx.price - close_3d) / close_3d * 100, 2)
                    else:
                        idx.change_pct_3d = None

                    close_7d = prices_7d.get((idx.code, idx.source))
                    if close_7d and close_7d > 0:
                        idx.change_pct_7d = round((idx.price - close_7d) / close_7d * 100, 2)
                    else:
                        idx.change_pct_7d = None

                # K 线未匹配到的 code（如概念板块 em 源无 ths K 线），从 index_data 补缺
                missing_3d = [idx for idx in indices if idx.change_pct_3d is None and date_3d_ago]
                missing_7d = [idx for idx in indices if idx.change_pct_7d is None and date_7d_ago]
                if missing_3d or missing_7d:
                    if missing_3d:
                        mc = [idx.code for idx in missing_3d]
                        ph = ','.join('?' * len(mc))
                        rows = self.db.fetch_all(
                            f'SELECT code, price, source FROM index_data WHERE fetched_date = ? AND code IN ({ph})',
                            (date_3d_ago, *mc)
                        )
                        data_3d = {(r['code'], r['source']): r['price'] for r in rows}
                    else:
                        data_3d = {}
                    if missing_7d:
                        mc = [idx.code for idx in missing_7d]
                        ph = ','.join('?' * len(mc))
                        rows = self.db.fetch_all(
                            f'SELECT code, price, source FROM index_data WHERE fetched_date = ? AND code IN ({ph})',
                            (date_7d_ago, *mc)
                        )
                        data_7d = {(r['code'], r['source']): r['price'] for r in rows}
                    else:
                        data_7d = {}
                    for idx in missing_3d:
                        p = data_3d.get((idx.code, idx.source))
                        if p and p > 0:
                            idx.change_pct_3d = round((idx.price - p) / p * 100, 2)
                    for idx in missing_7d:
                        p = data_7d.get((idx.code, idx.source))
                        if p and p > 0:
                            idx.change_pct_7d = round((idx.price - p) / p * 100, 2)

                # 合理性检查：|涨跌幅| > 30% 视为数据源不匹配，置 null
                for idx in indices:
                    if idx.change_pct_3d is not None and abs(idx.change_pct_3d) > 30:
                        idx.change_pct_3d = None
                    if idx.change_pct_7d is not None and abs(idx.change_pct_7d) > 30:
                        idx.change_pct_7d = None

                # 先排序后 limit（按今日涨跌幅降序）
                indices.sort(key=lambda x: x.change_pct, reverse=True)
                return indices[:limit]
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

        # 批量查询 3 日前的价格（带 source，构建 (code, source) -> price 映射）
        prices_3d = {}
        rows_3d = self.db.fetch_all('''
            SELECT code, price, source FROM index_data
            WHERE fetched_date = ? AND category = 'industry'
        ''', (date_3d_ago,))
        for r in rows_3d:
            prices_3d[(r['code'], r['source'])] = r['price']

        # 批量查询 7 日前的价格
        prices_7d = {}
        if date_7d_ago:
            rows_7d = self.db.fetch_all('''
                SELECT code, price, source FROM index_data
                WHERE fetched_date = ? AND category = 'industry'
            ''', (date_7d_ago,))
            for r in rows_7d:
                prices_7d[(r['code'], r['source'])] = r['price']

        # 按 (code, source) 匹配计算涨跌幅
        for idx in indices:
            price_3d = prices_3d.get((idx.code, idx.source))
            if price_3d and price_3d > 0:
                idx.change_pct_3d = round((idx.price - price_3d) / price_3d * 100, 2)
            else:
                idx.change_pct_3d = None

            price_7d = prices_7d.get((idx.code, idx.source))
            if price_7d and price_7d > 0:
                idx.change_pct_7d = round((idx.price - price_7d) / price_7d * 100, 2)
            else:
                idx.change_pct_7d = None

        # 合理性检查：|涨跌幅| > 30% 视为数据源不匹配，置 null
        for idx in indices:
            if idx.change_pct_3d is not None and abs(idx.change_pct_3d) > 30:
                idx.change_pct_3d = None
            if idx.change_pct_7d is not None and abs(idx.change_pct_7d) > 30:
                idx.change_pct_7d = None

        # 先排序后 limit（按今日涨跌幅降序）
        indices.sort(key=lambda x: x.change_pct, reverse=True)
        return indices[:limit]

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

    def get_market_overview_comparison(self) -> dict:
        """
        获取市场总览的历史对比数据

        计算指标：
        - amount_vs_yesterday: 今日市场指数成交额总额 vs 昨日的变化百分比
        - amount_vs_5d_avg: 今日市场指数成交额总额 vs 近5日日均的变化百分比
        - rise_count_vs_yesterday: 今日行业上涨家数 - 昨日上涨家数

        边界处理：
        - 历史数据不足（少于2日）时返回 has_history=False 且各指标为 None
        - 除零保护：昨日总额或5日日均为0时跳过对应指标（置为 None）

        Returns:
            dict: {
                'has_history': bool,
                'amount_vs_yesterday': float or None,
                'amount_vs_5d_avg': float or None,
                'rise_count_vs_yesterday': int or None
            }
        """
        # 1. 查询最近6日的市场指数成交额汇总（按 fetched_date 分组）
        market_rows = self.db.fetch_all('''
            SELECT fetched_date, SUM(amount) as total_amount
            FROM index_data
            WHERE category = 'market'
            GROUP BY fetched_date
            ORDER BY fetched_date DESC
            LIMIT 6
        ''')

        # 历史数据不足（少于2日）
        if len(market_rows) < 2:
            return {
                'has_history': False,
                'amount_vs_yesterday': None,
                'amount_vs_5d_avg': None,
                'rise_count_vs_yesterday': None
            }

        today_amount = market_rows[0]['total_amount'] or 0
        yesterday_amount = market_rows[1]['total_amount'] or 0
        today_date = market_rows[0]['fetched_date']
        yesterday_date = market_rows[1]['fetched_date']

        # 2. 计算 amount_vs_yesterday（今日 vs 昨日）
        amount_vs_yesterday = None
        if yesterday_amount > 0:
            amount_vs_yesterday = round(
                (today_amount - yesterday_amount) / yesterday_amount * 100, 1
            )

        # 3. 计算 amount_vs_5d_avg（今日 vs 近5日日均，排除今日）
        # 取最近6日中第2-6日的数据（索引1到5）计算日均
        amount_vs_5d_avg = None
        five_day_amounts = [r['total_amount'] or 0 for r in market_rows[1:6]]
        if five_day_amounts:
            five_day_avg = sum(five_day_amounts) / len(five_day_amounts)
            if five_day_avg > 0:
                amount_vs_5d_avg = round(
                    (today_amount - five_day_avg) / five_day_avg * 100, 1
                )

        # 4. 查询今日和昨日的行业指数涨跌数据，计算上涨家数变化
        industry_rows = self.db.fetch_all('''
            SELECT fetched_date, change_pct
            FROM index_data
            WHERE category = 'industry'
            AND fetched_date IN (?, ?)
        ''', (today_date, yesterday_date))

        today_rise_count = 0
        yesterday_rise_count = 0
        for row in industry_rows:
            change_pct = row['change_pct']
            if change_pct is None:
                continue
            row_date = row['fetched_date']
            if row_date == today_date and change_pct > 0:
                today_rise_count += 1
            elif row_date == yesterday_date and change_pct > 0:
                yesterday_rise_count += 1

        rise_count_vs_yesterday = today_rise_count - yesterday_rise_count

        return {
            'has_history': True,
            'amount_vs_yesterday': amount_vs_yesterday,
            'amount_vs_5d_avg': amount_vs_5d_avg,
            'rise_count_vs_yesterday': rise_count_vs_yesterday
        }

    def get_data_quality(self) -> dict:
        """
        获取最新日期的数据完整性质量指标

        校验维度：
        - 行业指数（category='industry' AND source='akshare'）amount>0 的比例
        - 概念板块（category='industry' AND source IN ('em','ths')）market_cap>0 的比例
        - 概念板块 amount!=0 的比例（概念板块资金净额可能为负，非 0 即视为有数据）

        Returns:
            dict: {
                'industry_amount_filled': float,   # 行业指数 amount 填充率 (0~1)
                'concept_market_cap_filled': float, # 概念板块 market_cap 填充率 (0~1)
                'concept_amount_filled': float,    # 概念板块 amount 填充率 (0~1)
                'industry_total': int,             # 行业指数总数
                'concept_total': int,              # 概念板块总数
                'has_data': bool                   # 是否有数据
            }
        """
        latest_date = self._get_latest_date()
        if not latest_date:
            return {
                'has_data': False,
                'industry_amount_filled': 0.0,
                'concept_market_cap_filled': 0.0,
                'concept_amount_filled': 0.0,
                'industry_total': 0,
                'concept_total': 0,
            }

        # 行业指数（申万，akshare 源）amount>0 比例
        industry_row = self.db.fetch_one('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as filled
            FROM index_data
            WHERE category = 'industry' AND source = 'akshare' AND fetched_date = ?
        ''', (latest_date,))

        industry_total = (industry_row['total'] or 0) if industry_row else 0
        industry_filled = (industry_row['filled'] or 0) if industry_row else 0
        industry_amount_filled = round(industry_filled / industry_total, 4) if industry_total > 0 else 0.0

        # 概念板块（em/ths 源）market_cap>0 和 amount!=0 比例
        concept_row = self.db.fetch_one('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN market_cap > 0 THEN 1 ELSE 0 END) as market_cap_filled,
                SUM(CASE WHEN amount != 0 THEN 1 ELSE 0 END) as amount_filled
            FROM index_data
            WHERE category = 'industry' AND source IN ('em','ths') AND fetched_date = ?
        ''', (latest_date,))

        concept_total = (concept_row['total'] or 0) if concept_row else 0
        concept_market_cap_filled_count = (concept_row['market_cap_filled'] or 0) if concept_row else 0
        concept_amount_filled_count = (concept_row['amount_filled'] or 0) if concept_row else 0
        concept_market_cap_filled = round(concept_market_cap_filled_count / concept_total, 4) if concept_total > 0 else 0.0
        concept_amount_filled = round(concept_amount_filled_count / concept_total, 4) if concept_total > 0 else 0.0

        return {
            'has_data': True,
            'industry_amount_filled': industry_amount_filled,
            'concept_market_cap_filled': concept_market_cap_filled,
            'concept_amount_filled': concept_amount_filled,
            'industry_total': industry_total,
            'concept_total': concept_total,
        }

    # ===== K 线数据缓存方法 =====

    def save_klines(self, code: str, klines: List[Dict], source: str = 'tx') -> int:
        """
        保存指数 K 线数据到数据库（单连接批量事务，upsert 逻辑）

        关键修复：原实现循环调用 self.db.execute，每条 K 线一次 connect/close。
        K 线缓存共 58520 条 × 2 次 connect/close = 11 万次连接操作，
        在 Windows 多线程下必然触发 SQLite C 扩展 access violation。
        改为单连接批量事务 + executemany，彻底消除段错误。

        Args:
            code: 指数代码
            klines: K 线数据列表，每条包含 date/open/close/high/low/volume/amount/change/change_pct
            source: 数据源标识

        Returns:
            保存的数据条数
        """
        if not klines:
            return 0

        from datetime import datetime
        import logging
        logger = logging.getLogger(__name__)
        now = datetime.now().isoformat()

        upsert_sql = '''
            INSERT INTO index_kline (
                code, date, open, close, high, low,
                volume, amount, change, change_pct, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date, source) DO UPDATE SET
                open = excluded.open,
                close = excluded.close,
                high = excluded.high,
                low = excluded.low,
                volume = excluded.volume,
                amount = excluded.amount,
                change = excluded.change,
                change_pct = excluded.change_pct,
                updated_at = excluded.updated_at
        '''

        batch = []
        for k in klines:
            try:
                date_str = str(k.get('date', ''))
                if not date_str:
                    continue
                batch.append((
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
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"跳过无效K线数据 code={code} date={k.get('date')}: {e}")
                continue

        if not batch:
            return 0

        # 单连接批量事务：connect/close 仅 1 次，executemany 比逐条 execute 快 10 倍
        with self.db.transaction() as conn:
            conn.executemany(upsert_sql, batch)

        return len(batch)

    def save_today_klines_batch(self, records: List[Dict]) -> int:
        """
        批量保存当日 K 线（多条 code / 多 source，单连接 executemany）

        用于盘中把指数实时快照写为当日 K 线（UPSERT code+date+source）：
        - 盘中每次定时拉取指数行情成功后调用，逐步用最新快照覆盖当日 K 线
        - 与正式 K 线（16:30/18:00 缓存）共用 (code, date, source) 唯一键，
          保证正式 K 线到达时自然覆盖盘中临时记录，不会残留脏数据

        Args:
            records: 每条含 code/source/date/open/close/high/low/volume/amount/change/change_pct

        Returns:
            写入的数据条数
        """
        if not records:
            return 0

        import logging
        from datetime import datetime
        logger = logging.getLogger(__name__)
        now = datetime.now().isoformat()

        upsert_sql = '''
            INSERT INTO index_kline (
                code, date, open, close, high, low,
                volume, amount, change, change_pct, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, date, source) DO UPDATE SET
                open = excluded.open,
                close = excluded.close,
                high = excluded.high,
                low = excluded.low,
                volume = excluded.volume,
                amount = excluded.amount,
                change = excluded.change,
                change_pct = excluded.change_pct,
                updated_at = excluded.updated_at
        '''

        batch = []
        for r in records:
            try:
                code = str(r.get('code', ''))
                date_str = str(r.get('date', ''))
                source = str(r.get('source', ''))
                if not code or not date_str or not source:
                    continue
                batch.append((
                    code, date_str,
                    float(r.get('open', 0) or 0),
                    float(r.get('close', 0) or 0),
                    float(r.get('high', 0) or 0),
                    float(r.get('low', 0) or 0),
                    int(float(r.get('volume', 0) or 0)),
                    float(r.get('amount', 0) or 0),
                    float(r.get('change', 0) or 0),
                    float(r.get('change_pct', 0) or 0),
                    source, now
                ))
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"跳过无效当日K线数据: {e}")
                continue

        if not batch:
            return 0

        # 单连接批量事务：connect/close 仅 1 次，避免高频连接触发段错误
        with self.db.transaction() as conn:
            conn.executemany(upsert_sql, batch)

        return len(batch)

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

    def get_5d_avg_amount(self, codes: list) -> dict:
        """查询指定 codes 的 5 日平均成交额和今日成交额（来自 index_kline 表）

        用于多因子动量模型中的量价动量子因子：amount_change_rate。
        从 index_kline 表查询最近 6 个交易日，最近 1 日为 today_amount，
        前 5 日求平均为 avg_5d_amount，change_rate = (today - avg) / avg * 100。

        Args:
            codes: 指数代码列表

        Returns:
            dict: code -> {'today_amount': float, 'avg_5d_amount': float or None, 'change_rate': float or None}
            数据不足 6 日或前 5 日记录不全时 change_rate 为 None
        """
        if not codes:
            return {}
        result = {}
        try:
            # 获取最近 6 个交易日
            date_rows = self.db.fetch_all('''
                SELECT DISTINCT date FROM index_kline
                ORDER BY date DESC LIMIT 6
            ''')
            if not date_rows:
                return {}
            kline_dates = [r['date'] for r in date_rows]
            today_date = kline_dates[0]
            past_5_dates = kline_dates[1:6]
            placeholders = ','.join('?' * len(codes))

            # 查询今日成交额
            today_rows = self.db.fetch_all(
                f'SELECT code, amount FROM index_kline WHERE date = ? AND code IN ({placeholders})',
                (today_date, *codes)
            )
            today_map = {r['code']: r['amount'] for r in today_rows}

            # 前 5 日不足时无法计算 change_rate，但仍返回今日成交额
            if len(past_5_dates) < 5:
                for code in codes:
                    amt = today_map.get(code)
                    result[code] = {
                        'today_amount': amt or 0,
                        'avg_5d_amount': None,
                        'change_rate': None,
                    }
                return result

            # 批量查询前 5 日成交额，按 code 聚合
            past_placeholders = ','.join('?' * len(past_5_dates))
            past_rows = self.db.fetch_all(
                f'''SELECT code, SUM(amount) as total_amount, COUNT(*) as cnt
                    FROM index_kline
                    WHERE date IN ({past_placeholders}) AND code IN ({placeholders})
                    GROUP BY code''',
                (*past_5_dates, *codes)
            )
            past_map = {r['code']: (r['total_amount'], r['cnt']) for r in past_rows}

            for code in codes:
                today_amount = today_map.get(code)
                if today_amount is None or today_amount == 0:
                    result[code] = {
                        'today_amount': today_amount or 0,
                        'avg_5d_amount': None,
                        'change_rate': None,
                    }
                    continue
                past = past_map.get(code)
                if not past or past[1] < 5 or past[0] == 0:
                    result[code] = {
                        'today_amount': today_amount,
                        'avg_5d_amount': None,
                        'change_rate': None,
                    }
                    continue
                avg_5d = past[0] / past[1]
                change_rate = round((today_amount - avg_5d) / avg_5d * 100, 2)
                result[code] = {
                    'today_amount': today_amount,
                    'avg_5d_amount': avg_5d,
                    'change_rate': change_rate,
                }
            return result
        except Exception:
            return {}

    def get_rotation_history(self, days: int = 30) -> dict:
        """查询近 N 日每日行业指数排名（用于前端 bump chart）

        取最近 N 个不同 fetched_date，对每个日期的全部行业指数按 change_pct 降序排名
        （第 1 名涨跌幅最高）。只返回在最近一日有数据的板块，避免已退市板块干扰。
        某板块在某日无数据时，该日排名用 None 表示（前端 Chart.js spanGaps 跳过）。

        Args:
            days: 查询近 N 日

        Returns:
            {
                'dates': ['2026-06-10', ...],      # 升序（旧→新）
                'sectors': [
                    {'code': ..., 'name': ..., 'ranks': [rank1, rank2, ...]},
                    ...
                ]
            }
        """
        # 1. 获取最近 N 个不同 fetched_date
        date_rows = self.db.fetch_all('''
            SELECT DISTINCT fetched_date FROM index_data
            WHERE category = 'industry'
            ORDER BY fetched_date DESC
            LIMIT ?
        ''', (days,))
        if not date_rows:
            return {'dates': [], 'sectors': []}

        # 按时间升序排列（左旧右新，便于图表绘制）
        dates = [r['fetched_date'] for r in date_rows]
        dates.reverse()

        # 2. 一次性查询这些日期的全部行业指数数据
        placeholders = ','.join('?' * len(dates))
        rows = self.db.fetch_all(
            f'''SELECT code, name, change_pct, fetched_date
                FROM index_data
                WHERE category = 'industry' AND fetched_date IN ({placeholders})''',
            tuple(dates)
        )

        # 3. 按日期分组
        date_data = {d: [] for d in dates}
        for row in rows:
            d = row['fetched_date']
            if d in date_data:
                date_data[d].append((row['code'], row['name'], row['change_pct']))

        # 4. 每日按 change_pct 降序排名（None 视为最差）
        date_rank = {}
        for d in dates:
            items_d = sorted(
                date_data[d],
                key=lambda x: x[2] if x[2] is not None else float('-inf'),
                reverse=True
            )
            date_rank[d] = {code: i + 1 for i, (code, _, _) in enumerate(items_d)}

        # 5. 只保留最近一日有数据的板块
        latest_date = dates[-1]
        latest_items = date_data[latest_date]
        latest_codes = {code for code, _, _ in latest_items}

        # 用最近一日的 name 作为板块名称
        name_map = {code: name for code, name, _ in latest_items}

        sectors = []
        for code in latest_codes:
            ranks = [date_rank[d].get(code) for d in dates]
            sectors.append({
                'code': code,
                'name': name_map.get(code, code),
                'ranks': ranks
            })

        return {'dates': dates, 'sectors': sectors}

    # ===== 市场情绪涨跌停统计 =====

    def save_sentiment_stats(self, stats: dict):
        """保存涨跌停统计到数据库"""
        import json
        self.db.execute('''
            INSERT OR REPLACE INTO limit_up_stats
            (date, limit_up_count, limit_down_count, broken_limit_count, broken_rate,
             max_consecutive, sentiment_score, consecutive_tiers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stats['date'],
            stats['limit_up_count'],
            stats['limit_down_count'],
            stats['broken_limit_count'],
            stats['broken_rate'],
            stats['max_consecutive'],
            stats['sentiment_score'],
            json.dumps(stats.get('consecutive_tiers', []), ensure_ascii=False)
        ))

    def get_sentiment_history(self, days: int = 30) -> list:
        """查询近 N 日涨跌停统计历史"""
        rows = self.db.fetch_all('''
            SELECT date, limit_up_count, limit_down_count, broken_limit_count,
                   broken_rate, max_consecutive, sentiment_score
            FROM limit_up_stats
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))
        return [dict(r) for r in rows]

    # ===== 北向资金（沪深港通） =====

    def save_northbound_flow(self, data: dict):
        """保存北向资金数据到数据库"""
        dates = data.get('dates', [])
        sh = data.get('sh_net_flow', [])
        sz = data.get('sz_net_flow', [])
        total = data.get('total_net_flow', [])
        for i, d in enumerate(dates):
            self.db.execute('''
                INSERT OR REPLACE INTO northbound_flow
                (date, sh_net_buy, sz_net_buy, total_net_buy)
                VALUES (?, ?, ?, ?)
            ''', (d, sh[i] if i < len(sh) else 0, sz[i] if i < len(sz) else 0, total[i] if i < len(total) else 0))

    def get_northbound_history(self, days: int = 30) -> list:
        """查询近 N 日北向资金历史"""
        rows = self.db.fetch_all('''
            SELECT date, sh_net_buy, sz_net_buy, total_net_buy
            FROM northbound_flow
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))
        return [dict(r) for r in rows]
