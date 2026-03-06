"""
A股市场数据获取器
使用东方财富免费接口获取A股行情数据
"""

import sys
import requests
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils import get_logger
from .base import BaseFetcher


@dataclass
class StockItem:
    """股票数据格式"""
    code: str = ""
    name: str = ""
    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    amount: float = 0.0
    market_cap: float = 0.0
    pe: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    pre_close: float = 0.0
    turnover_rate: float = 0.0
    source: str = "eastmoney"
    fetched_at: datetime = field(default_factory=datetime.now)


class StockFetcher(BaseFetcher):
    """A股市场数据获取器"""

    name = "stock"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.base_url = "http://push2.eastmoney.com/api/qt/clist/get"

    def fetch(self) -> List[StockItem]:
        """
        获取A股市场数据（支持分页获取所有数据）

        Returns:
            List[StockItem]: 股票数据列表
        """
        import time

        all_stocks = []
        page_size = 100  # API每页最大返回100条
        page_no = 1
        max_pages = 60  # 最多获取60页，约6000只股票
        max_retries = 3  # 每页最大重试次数

        try:
            while page_no <= max_pages:
                params = {
                    'pn': page_no,
                    'pz': page_size,
                    'po': 1,
                    'np': 1,
                    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                    'fltt': 2,
                    'invt': 2,
                    'fid': 'f12',
                    'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                    'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f37,f38,f39,f40,f41,f42,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f62,f115,f140,f141'
                }

                # 重试机制
                stocks_page = []
                for retry in range(max_retries):
                    try:
                        response = self.session.get(self.base_url, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()

                        if data.get('data') and data['data'].get('diff'):
                            stocks_page = data['data']['diff']
                        break
                    except Exception as e:
                        if retry < max_retries - 1:
                            if self.logger:
                                self.logger.warning(f"第{page_no}页获取失败，第{retry+1}次重试: {e}")
                            time.sleep(0.5)  # 等待后重试
                        else:
                            if self.logger:
                                self.logger.error(f"第{page_no}页获取失败，已达最大重试次数: {e}")
                            break

                if not stocks_page:
                    break

                for item in stocks_page:
                    stock = self._parse_stock(item)
                    if stock:
                        all_stocks.append(stock)

                # 如果本页数据不足page_size，说明已经获取完所有数据
                if len(stocks_page) < page_size:
                    break

                # 添加短暂延迟，避免请求过快
                time.sleep(0.1)
                page_no += 1

            if self.logger:
                self.logger.info(f"股票数据: 获取 {len(all_stocks)} 条")

            return all_stocks

        except Exception as e:
            if self.logger:
                self.logger.error(f"获取股票数据失败: {e}")
            return []

    def _parse_stock(self, item: Dict) -> Optional[StockItem]:
        """解析单条股票数据"""
        try:
            code = str(item.get('f12', ''))
            if not code:
                return None

            return StockItem(
                code=code,
                name=item.get('f14', ''),
                price=self._safe_float(item.get('f2')),
                change=self._safe_float(item.get('f4')),
                change_pct=self._safe_float(item.get('f3')),
                volume=self._safe_int(item.get('f5')),
                amount=self._safe_float(item.get('f6')),
                market_cap=self._safe_float(item.get('f20')),
                pe=self._safe_float(item.get('f12')),
                high=self._safe_float(item.get('f15')),
                low=self._safe_float(item.get('f16')),
                open=self._safe_float(item.get('f17')),
                pre_close=self._safe_float(item.get('f18')),
                turnover_rate=self._safe_float(item.get('f8')),
                fetched_at=datetime.now()
            )
        except Exception:
            return None

    def _safe_float(self, value) -> float:
        """安全转换为浮点数"""
        if value is None or value == '-' or value == '':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _safe_int(self, value) -> int:
        """安全转换为整数"""
        if value is None or value == '-' or value == '':
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0

    def fetch_gainers(self, limit: int = 10) -> List[StockItem]:
        """
        获取涨幅榜

        Args:
            limit: 返回数量

        Returns:
            List[StockItem]: 涨幅榜数据
        """
        all_stocks = self.fetch()
        gainers = [s for s in all_stocks if s.change_pct > 0]
        gainers.sort(key=lambda x: x.change_pct, reverse=True)
        return gainers[:limit]

    def fetch_losers(self, limit: int = 10) -> List[StockItem]:
        """
        获取跌幅榜

        Args:
            limit: 返回数量

        Returns:
            List[StockItem]: 跌幅榜数据
        """
        all_stocks = self.fetch()
        losers = [s for s in all_stocks if s.change_pct < 0]
        losers.sort(key=lambda x: x.change_pct)
        return losers[:limit]

    def fetch_by_volume(self, limit: int = 10) -> List[StockItem]:
        """
        获取成交额榜

        Args:
            limit: 返回数量

        Returns:
            List[StockItem]: 成交额榜数据
        """
        all_stocks = self.fetch()
        all_stocks.sort(key=lambda x: x.amount, reverse=True)
        return all_stocks[:limit]

    def fetch_by_market_cap(self, limit: int = 10) -> List[StockItem]:
        """
        获取市值榜

        Args:
            limit: 返回数量

        Returns:
            List[StockItem]: 市值榜数据
        """
        all_stocks = self.fetch()
        valid_stocks = [s for s in all_stocks if s.market_cap > 0]
        valid_stocks.sort(key=lambda x: x.market_cap, reverse=True)
        return valid_stocks[:limit]

    def to_dict(self, stock: StockItem) -> Dict:
        """转换为字典格式"""
        return {
            'code': stock.code,
            'name': stock.name,
            'price': round(stock.price, 2) if stock.price else 0,
            'change': round(stock.change, 2) if stock.change else 0,
            'change_pct': round(stock.change_pct, 2) if stock.change_pct else 0,
            'volume': stock.volume,
            'amount': round(stock.amount / 100000000, 2) if stock.amount else 0,
            'market_cap': round(stock.market_cap / 100000000, 2) if stock.market_cap else 0,
            'turnover_rate': round(stock.turnover_rate, 2) if stock.turnover_rate else 0,
            'fetched_at': stock.fetched_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    def save_to_db(self, db_path: Path = None) -> int:
        """
        保存股票数据到数据库

        Args:
            db_path: 数据库路径，默认使用config中的路径

        Returns:
            保存的记录数
        """
        if db_path is None:
            from src.config import DATABASE
            db_path = DATABASE['path']

        from src.db.stock_dao import StockDAO
        from src.db.models import StockData as ModelStockData

        dao = StockDAO(db_path)

        stocks = self.fetch()

        # 根据股票代码去重，保留最新的一条
        unique_stocks = {}
        for item in stocks:
            if item.code:
                # 如果已存在相同代码的股票，比较时间保留最新的
                if item.code not in unique_stocks:
                    unique_stocks[item.code] = item
                else:
                    # 保留 fetched_at 更新的数据
                    if item.fetched_at > unique_stocks[item.code].fetched_at:
                        unique_stocks[item.code] = item

        deduplicated_stocks = list(unique_stocks.values())
        removed_count = len(stocks) - len(deduplicated_stocks)

        if removed_count > 0 and self.logger:
            self.logger.info(f"股票数据去重: 移除 {removed_count} 条重复记录")

        stock_models = []
        for item in deduplicated_stocks:
            model = ModelStockData(
                code=item.code,
                name=item.name,
                price=item.price,
                change=item.change,
                change_pct=item.change_pct,
                volume=item.volume,
                amount=item.amount,
                market_cap=item.market_cap,
                turnover_rate=item.turnover_rate,
                source=item.source,
                fetched_at=item.fetched_at
            )
            stock_models.append(model)

        count = dao.save_stocks(stock_models)

        if self.logger:
            self.logger.info(f"已保存 {count} 条股票数据到数据库")

        return count

    def fetch_kline(self, code: str, days: int = 30) -> List[Dict]:
        """
        获取个股K线数据

        Args:
            code: 股票代码 (如 000001)
            days: 获取天数

        Returns:
            K线数据列表 [{date, open, high, low, close, volume}]
        """
        try:
            secid = f"1.{code}" if code.startswith('6') else f"0.{code}"
            url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': secid,
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': 101,
                'fqt': 1,
                'end': '20500101',
                'lmt': days
            }

            response = self.session.get(url, params=params, timeout=10)
            data = response.json()

            klines = []
            if data.get('data') and data['data'].get('klines'):
                for kline in data['data']['klines']:
                    parts = kline.split(',')
                    klines.append({
                        'date': parts[0],
                        'open': float(parts[1]),
                        'close': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'volume': int(parts[5]),
                        'amount': float(parts[6]) if len(parts) > 6 else 0
                    })

            return klines

        except Exception as e:
            if self.logger:
                self.logger.error(f"获取K线数据失败: {e}")
            return []

    def fetch_stock_detail(self, code: str) -> Optional[Dict]:
        """
        获取个股详情

        Args:
            code: 股票代码

        Returns:
            股票详情字典
        """
        all_stocks = self.fetch()
        for stock in all_stocks:
            if stock.code == code:
                return {
                    'code': stock.code,
                    'name': stock.name,
                    'price': stock.price,
                    'change': stock.change,
                    'change_pct': stock.change_pct,
                    'open': stock.open,
                    'high': stock.high,
                    'low': stock.low,
                    'pre_close': stock.pre_close,
                    'volume': stock.volume,
                    'amount': stock.amount,
                    'market_cap': stock.market_cap,
                    'turnover_rate': stock.turnover_rate,
                    'kline': self.fetch_kline(code, 30),
                    'fetched_at': stock.fetched_at.strftime('%Y-%m-%d %H:%M:%S')
                }
        return None

    def get_market_summary(self) -> Dict:
        """
        获取市场整体概况

        Returns:
            市场概况数据
        """
        all_stocks = self.fetch()

        gainers = [s for s in all_stocks if s.change_pct > 0]
        losers = [s for s in all_stocks if s.change_pct < 0]
        flat = [s for s in all_stocks if s.change_pct == 0]

        total_volume = sum(s.volume for s in all_stocks)
        total_amount = sum(s.amount for s in all_stocks)

        return {
            'total_stocks': len(all_stocks),
            'gainers_count': len(gainers),
            'losers_count': len(losers),
            'flat_count': len(flat),
            'total_volume': total_volume,
            'total_amount': total_amount,
            'gainers_rate': round(len(gainers) / len(all_stocks) * 100, 2) if all_stocks else 0,
            'fetched_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


def main():
    """测试函数"""
    logger = get_logger('stock_fetcher')
    fetcher = StockFetcher(logger=logger)

    print("=== 获取涨幅榜 ===")
    gainers = fetcher.fetch_gainers(5)
    for s in gainers:
        print(f"{s.name}: {s.price} ({s.change_pct:+.2f}%)")

    print("\n=== 获取跌幅榜 ===")
    losers = fetcher.fetch_losers(5)
    for s in losers:
        print(f"{s.name}: {s.price} ({s.change_pct:+.2f}%)")

    print("\n=== 获取成交额榜 ===")
    volume_list = fetcher.fetch_by_volume(5)
    for s in volume_list:
        print(f"{s.name}: {s.amount / 100000000:.2f}亿")


if __name__ == '__main__':
    main()
