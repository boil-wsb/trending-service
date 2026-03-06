"""
股票数据访问对象
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pathlib import Path

from .database import Database
from .models import StockData


class StockDAO:
    """股票数据访问对象"""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self._init_table()

    def _init_table(self):
        """初始化股票数据表"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS stock_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL DEFAULT 0,
                change REAL DEFAULT 0,
                change_pct REAL DEFAULT 0,
                volume INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                market_cap REAL DEFAULT 0,
                turnover_rate REAL DEFAULT 0,
                source TEXT DEFAULT 'eastmoney',
                fetched_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_stock_code ON stock_data(code)
        ''')

        self.db.execute('''
            CREATE INDEX IF NOT EXISTS idx_stock_fetched_at ON stock_data(fetched_at)
        ''')

    def save_stock(self, stock: StockData) -> int:
        """
        保存单条股票数据

        Args:
            stock: 股票数据对象

        Returns:
            插入的记录ID
        """
        result = self.db.execute('''
            INSERT INTO stock_data (
                code, name, price, change, change_pct, volume, amount,
                market_cap, turnover_rate, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stock.code,
            stock.name,
            stock.price,
            stock.change,
            stock.change_pct,
            stock.volume,
            stock.amount,
            stock.market_cap,
            stock.turnover_rate,
            stock.source,
            stock.fetched_at.isoformat() if stock.fetched_at else datetime.now().isoformat()
        ))
        return result.lastrowid if hasattr(result, 'lastrowid') else 0

    def save_stocks(self, stocks: List[StockData]) -> int:
        """
        批量保存股票数据

        Args:
            stocks: 股票数据列表

        Returns:
            保存的记录数
        """
        if not stocks:
            return 0

        count = 0
        for stock in stocks:
            self.save_stock(stock)
            count += 1
        return count

    def get_gainers(self, limit: int = 10, fetched_at: str = None) -> List[StockData]:
        """
        获取涨幅榜

        Args:
            limit: 返回数量
            fetched_at: 指定日期的记录，默认最新

        Returns:
            涨幅榜数据列表
        """
        if not fetched_at:
            fetched_at = self._get_latest_date()

        if not fetched_at:
            return []

        rows = self.db.fetch_all('''
            SELECT * FROM stock_data
            WHERE fetched_at LIKE ? AND change_pct > 0
            ORDER BY change_pct DESC
            LIMIT ?
        ''', (fetched_at + '%', limit))

        return [self._row_to_stock(row) for row in rows]

    def get_losers(self, limit: int = 10, fetched_at: str = None) -> List[StockData]:
        """
        获取跌幅榜

        Args:
            limit: 返回数量
            fetched_at: 指定日期的记录，默认最新

        Returns:
            跌幅榜数据列表
        """
        if not fetched_at:
            fetched_at = self._get_latest_date()

        if not fetched_at:
            return []

        rows = self.db.fetch_all('''
            SELECT * FROM stock_data
            WHERE fetched_at LIKE ? AND change_pct < 0
            ORDER BY change_pct ASC
            LIMIT ?
        ''', (fetched_at + '%', limit))

        return [self._row_to_stock(row) for row in rows]

    def get_by_volume(self, limit: int = 10, fetched_at: str = None) -> List[StockData]:
        """
        获取成交额榜

        Args:
            limit: 返回数量
            fetched_at: 指定日期的记录，默认最新

        Returns:
            成交额榜数据列表
        """
        if not fetched_at:
            fetched_at = self._get_latest_date()

        if not fetched_at:
            return []

        rows = self.db.fetch_all('''
            SELECT * FROM stock_data
            WHERE fetched_at LIKE ?
            ORDER BY amount DESC
            LIMIT ?
        ''', (fetched_at + '%', limit))

        return [self._row_to_stock(row) for row in rows]

    def get_by_market_cap(self, limit: int = 10, fetched_at: str = None) -> List[StockData]:
        """
        获取市值榜

        Args:
            limit: 返回数量
            fetched_at: 指定日期的记录，默认最新

        Returns:
            市值榜数据列表
        """
        if not fetched_at:
            fetched_at = self._get_latest_date()

        if not fetched_at:
            return []

        rows = self.db.fetch_all('''
            SELECT * FROM stock_data
            WHERE fetched_at LIKE ? AND market_cap > 0
            ORDER BY market_cap DESC
            LIMIT ?
        ''', (fetched_at + '%', limit))

        return [self._row_to_stock(row) for row in rows]

    def get_stock_by_code(self, code: str, fetched_at: str = None) -> Optional[StockData]:
        """
        根据代码获取股票数据

        Args:
            code: 股票代码
            fetched_at: 指定日期的记录，默认最新

        Returns:
            股票数据或None
        """
        if not fetched_at:
            fetched_at = self._get_latest_date()

        if not fetched_at:
            return None

        row = self.db.fetch_one('''
            SELECT * FROM stock_data
            WHERE code = ? AND fetched_at LIKE ?
            ORDER BY fetched_at DESC
            LIMIT 1
        ''', (code, fetched_at + '%'))

        return self._row_to_stock(row) if row else None

    def get_latest(self, limit: int = 100) -> List[StockData]:
        """
        获取最新一批股票数据

        Args:
            limit: 返回数量

        Returns:
            股票数据列表
        """
        fetched_at = self._get_latest_date()
        if not fetched_at:
            return []

        rows = self.db.fetch_all('''
            SELECT * FROM stock_data
            WHERE fetched_at LIKE ?
            LIMIT ?
        ''', (fetched_at + '%', limit))

        return [self._row_to_stock(row) for row in rows]

    def get_stock_detail(self, code: str) -> Optional[Dict]:
        """
        获取个股详情

        Args:
            code: 股票代码

        Returns:
            股票详情字典或None
        """
        stock = self.get_stock_by_code(code)
        if not stock:
            return None

        return {
            'code': stock.code,
            'name': stock.name,
            'price': stock.price,
            'change': stock.change,
            'change_pct': stock.change_pct,
            'volume': stock.volume,
            'amount': stock.amount,
            'market_cap': stock.market_cap,
            'turnover_rate': stock.turnover_rate,
            'fetched_at': stock.fetched_at.strftime('%Y-%m-%d %H:%M:%S') if stock.fetched_at else None
        }

    def _get_latest_date(self) -> Optional[str]:
        """
        获取最新数据的日期

        Returns:
            日期字符串 (YYYY-MM-DD) 或 None
        """
        row = self.db.fetch_one('''
            SELECT fetched_at FROM stock_data
            ORDER BY fetched_at DESC
            LIMIT 1
        ''')
        if row and row.get('fetched_at'):
            return row['fetched_at'][:10]
        return None

    def get_market_summary(self) -> Dict:
        """
        获取市场整体概况

        Returns:
            市场概况数据
        """
        fetched_at = self._get_latest_date()
        if not fetched_at:
            return {
                'total_stocks': 0,
                'gainers_count': 0,
                'losers_count': 0,
                'flat_count': 0,
                'total_volume': 0,
                'total_amount': 0.0,
                'gainers_rate': 0.0,
                'fetched_at': None
            }

        # 获取最新数据的总数
        total_result = self.db.fetch_one('''
            SELECT COUNT(*) as count, SUM(volume) as total_volume, SUM(amount) as total_amount
            FROM stock_data
            WHERE fetched_at LIKE ?
        ''', (fetched_at + '%',))

        total_stocks = total_result['count'] if total_result else 0
        total_volume = total_result['total_volume'] if total_result and total_result['total_volume'] else 0
        total_amount = total_result['total_amount'] if total_result and total_result['total_amount'] else 0.0

        # 获取上涨数量
        gainers_result = self.db.fetch_one('''
            SELECT COUNT(*) as count FROM stock_data
            WHERE fetched_at LIKE ? AND change_pct > 0
        ''', (fetched_at + '%',))
        gainers_count = gainers_result['count'] if gainers_result else 0

        # 获取下跌数量
        losers_result = self.db.fetch_one('''
            SELECT COUNT(*) as count FROM stock_data
            WHERE fetched_at LIKE ? AND change_pct < 0
        ''', (fetched_at + '%',))
        losers_count = losers_result['count'] if losers_result else 0

        # 获取平盘数量
        flat_result = self.db.fetch_one('''
            SELECT COUNT(*) as count FROM stock_data
            WHERE fetched_at LIKE ? AND change_pct = 0
        ''', (fetched_at + '%',))
        flat_count = flat_result['count'] if flat_result else 0

        return {
            'total_stocks': total_stocks,
            'gainers_count': gainers_count,
            'losers_count': losers_count,
            'flat_count': flat_count,
            'total_volume': total_volume,
            'total_amount': round(total_amount, 2),
            'gainers_rate': round(gainers_count / total_stocks * 100, 2) if total_stocks > 0 else 0.0,
            'fetched_at': fetched_at
        }

    def _row_to_stock(self, row: Dict) -> StockData:
        """将数据库行转换为StockData对象"""
        if not row:
            return None

        fetched_at = row.get('fetched_at')
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)

        return StockData(
            id=row.get('id'),
            code=row.get('code', ''),
            name=row.get('name', ''),
            price=row.get('price', 0.0),
            change=row.get('change', 0.0),
            change_pct=row.get('change_pct', 0.0),
            volume=row.get('volume', 0),
            amount=row.get('amount', 0.0),
            market_cap=row.get('market_cap', 0.0),
            turnover_rate=row.get('turnover_rate', 0.0),
            source=row.get('source', 'eastmoney'),
            fetched_at=fetched_at
        )
