"""
指数行情数据获取器
获取 A 股市场指数（AKShare 新浪源）+ 申万行业指数（AKShare）

注意：不继承 BaseFetcher，因为 BaseFetcher 返回 TrendingItem 不适用于指数数据。
"""

import sys
from typing import List, Dict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES
from src.utils import get_logger
from src.db.models import IndexData


class IndexFetcher:
    """指数行情数据获取器"""

    name = "index"

    # 主要 A 股市场指数
    # sina_code: 新浪/腾讯数据源代码（sh/sz 前缀）
    # secid: 东方财富代码（保留用于兼容，沪市 1.代码，深市 0.代码）
    MARKET_INDICES = [
        {'code': '000001', 'name': '上证指数', 'sina_code': 'sh000001', 'secid': '1.000001'},
        {'code': '399001', 'name': '深证成指', 'sina_code': 'sz399001', 'secid': '0.399001'},
        {'code': '000300', 'name': '沪深300', 'sina_code': 'sh000300', 'secid': '1.000300'},
        {'code': '399006', 'name': '创业板指', 'sina_code': 'sz399006', 'secid': '0.399006'},
        {'code': '000688', 'name': '科创50', 'sina_code': 'sh000688', 'secid': '1.000688'},
        {'code': '000016', 'name': '上证50', 'sina_code': 'sh000016', 'secid': '1.000016'},
        {'code': '000905', 'name': '中证500', 'sina_code': 'sh000905', 'secid': '1.000905'},
        {'code': '399303', 'name': '国证2000', 'sina_code': 'sz399303', 'secid': '0.399303'},
    ]

    def __init__(self, config: Dict = None, logger=None):
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {})

    def fetch(self) -> List[IndexData]:
        """
        获取所有指数数据（市场指数 + 行业指数 + 概念板块）

        Returns:
            List[IndexData]: 指数数据列表
        """
        all_indices: List[IndexData] = []

        # 获取市场指数
        try:
            market_indices = self.fetch_market_indices()
            all_indices.extend(market_indices)
            self.logger.info(f"获取市场指数完成: {len(market_indices)} 条")
        except Exception as e:
            self.logger.error(f"获取市场指数失败: {e}")

        # 获取行业指数
        try:
            industry_indices = self.fetch_industry_indices()
            all_indices.extend(industry_indices)
            self.logger.info(f"获取行业指数完成: {len(industry_indices)} 条")
        except Exception as e:
            self.logger.error(f"获取行业指数失败: {e}")

        # 获取概念板块（合并到行业指数中展示）
        try:
            concept_indices = self.fetch_concept_indices()
            all_indices.extend(concept_indices)
            self.logger.info(f"获取概念板块完成: {len(concept_indices)} 条")
        except Exception as e:
            self.logger.error(f"获取概念板块失败: {e}")

        self.logger.info(f"指数数据获取完成: 共 {len(all_indices)} 条")
        return all_indices

    def fetch_market_indices(self) -> List[IndexData]:
        """
        获取 A 股市场指数实时行情（AKShare 新浪数据源）

        使用 ak.stock_zh_index_spot_sina() 获取所有 A 股指数实时行情，
        从中筛选出主要市场指数。新浪源比东方财富 push2 接口更稳定。

        Returns:
            List[IndexData]: 市场指数数据列表
        """
        self.logger.info("开始获取 A 股市场指数...")
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取市场指数。请运行: pip install akshare")
            return []

        try:
            df = ak.stock_zh_index_spot_sina()
            if df is None or df.empty:
                self.logger.warning("AKShare 返回空数据")
                return []

            # 构建目标代码映射
            target_codes = {item['sina_code']: item for item in self.MARKET_INDICES}

            # AKShare stock_zh_index_spot_sina 返回字段：
            # 代码、名称、最新价、涨跌额、涨跌幅、昨收、今开、最高、最低、成交量、成交额
            results: List[IndexData] = []
            now = datetime.now()

            for _, row in df.iterrows():
                sina_code = str(row.get('代码', ''))
                if sina_code not in target_codes:
                    continue

                item = target_codes[sina_code]
                try:
                    index = IndexData(
                        code=item['code'],
                        name=item['name'],
                        category='market',
                        price=float(row.get('最新价', 0) or 0),
                        change=float(row.get('涨跌额', 0) or 0),
                        change_pct=float(row.get('涨跌幅', 0) or 0),
                        high=float(row.get('最高', 0) or 0),
                        low=float(row.get('最低', 0) or 0),
                        open=float(row.get('今开', 0) or 0),
                        pre_close=float(row.get('昨收', 0) or 0),
                        volume=int(float(row.get('成交量', 0) or 0)),
                        amount=float(row.get('成交额', 0) or 0),
                        turnover_rate=0.0,
                        source='sina',
                        fetched_at=now,
                    )
                    results.append(index)
                    self.logger.debug(f"获取指数 {item['name']}: {index.price} ({index.change_pct}%)")
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析市场指数 {sina_code} 数据失败: {e}")
                    continue

            return results

        except Exception as e:
            self.logger.error(f"AKShare 获取市场指数失败: {e}")
            return []

    def fetch_industry_indices(self) -> List[IndexData]:
        """
        获取申万一级行业指数实时行情（AKShare）

        AKShare 延迟导入，避免影响启动速度。
        使用 index_realtime_sw() 获取申万行业指数实时行情。

        Returns:
            List[IndexData]: 行业指数数据列表
        """
        self.logger.info("开始获取申万一级行业指数...")
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取申万行业指数。请运行: pip install akshare")
            return []

        try:
            df = ak.index_realtime_sw()
            if df is None or df.empty:
                self.logger.warning("AKShare 返回空数据")
                return []

            results: List[IndexData] = []
            now = datetime.now()

            # AKShare index_realtime_sw 返回字段：
            # 指数代码、指数名称、昨收盘、今开盘、最新价、成交额、成交量、最高价、最低价
            for _, row in df.iterrows():
                try:
                    price = float(row.get('最新价', 0) or 0)
                    pre_close = float(row.get('昨收盘', 0) or 0)
                    change = round(price - pre_close, 2) if pre_close else 0.0
                    change_pct = round((change / pre_close) * 100, 2) if pre_close else 0.0

                    # 代码去掉 .SI 后缀（如有）
                    code = str(row.get('指数代码', '')).replace('.SI', '')

                    index = IndexData(
                        code=code,
                        name=str(row.get('指数名称', '')),
                        category='industry',
                        price=price,
                        change=change,
                        change_pct=change_pct,
                        high=float(row.get('最高价', 0) or 0),
                        low=float(row.get('最低价', 0) or 0),
                        open=float(row.get('今开盘', 0) or 0),
                        pre_close=pre_close,
                        volume=int(float(row.get('成交量', 0) or 0)),
                        amount=float(row.get('成交额', 0) or 0),
                        turnover_rate=0.0,
                        source='akshare',
                        fetched_at=now,
                    )
                    results.append(index)
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析行业指数数据失败: {e}, row: {row.to_dict()}")
                    continue

            return results

        except Exception as e:
            self.logger.error(f"AKShare 获取申万行业指数失败: {e}")
            return []

    def fetch_concept_indices(self) -> List[IndexData]:
        """
        获取 A 股概念板块实时行情（AKShare 同花顺数据源）

        使用 ak.stock_fund_flow_concept(symbol='即时') 获取概念板块实时行情。
        包含 CPO、PCB、CRO概念等 385+ 个概念板块。
        数据源是同花顺（q.10jqka.com.cn），不依赖东方财富 push2。

        概念板块合并到行业指数中展示（category='industry'），source='ths'。

        Returns:
            List[IndexData]: 概念板块数据列表
        """
        self.logger.info("开始获取概念板块行情...")
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取概念板块。请运行: pip install akshare")
            return []

        try:
            df = ak.stock_fund_flow_concept(symbol='即时')
            if df is None or df.empty:
                self.logger.warning("AKShare 概念板块返回空数据")
                return []

            results: List[IndexData] = []
            now = datetime.now()

            # AKShare stock_fund_flow_concept 返回字段：
            # 序号、行业、行业指数、行业-涨跌幅、流入资金、流出资金、净额、公司家数、领涨股、领涨股-涨跌幅、当前价
            for _, row in df.iterrows():
                try:
                    name = str(row.get('行业', '')).strip()
                    if not name:
                        continue

                    price = float(row.get('行业指数', 0) or 0)
                    change_pct = float(row.get('行业-涨跌幅', 0) or 0)
                    current_price = float(row.get('当前价', 0) or 0)

                    # 使用当前价作为 price 的备选（部分概念板块行业指数为 0）
                    if price == 0 and current_price > 0:
                        price = current_price

                    # 代码使用概念名称（概念板块无标准代码）
                    code = name

                    index = IndexData(
                        code=code,
                        name=name,
                        category='industry',  # 合并到行业指数展示
                        price=price,
                        change=round(price * change_pct / 100, 2) if price else 0.0,
                        change_pct=change_pct,
                        high=0.0,  # 概念板块无最高价
                        low=0.0,   # 概念板块无最低价
                        open=0.0,  # 概念板块无开盘价
                        pre_close=round(price * (1 - change_pct / 100), 2) if price and change_pct else 0.0,
                        volume=0,
                        amount=float(row.get('净额', 0) or 0),  # 净额作为成交额参考
                        turnover_rate=0.0,
                        source='ths',
                        fetched_at=now,
                    )
                    results.append(index)
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析概念板块数据失败: {e}, row: {row.to_dict()}")
                    continue

            return results

        except Exception as e:
            self.logger.error(f"AKShare 获取概念板块失败: {e}")
            return []

    def fetch_kline(self, code: str, days: int = 30) -> List[Dict]:
        """
        获取指数历史 K 线数据（根据代码类型自动选择数据源）

        数据源选择逻辑：
        - 申万行业指数（code 以 80 开头，6 位数字）：使用 ak.index_hist_sw()，含成交量
        - 市场指数（code 是 6 位数字）：使用 ak.stock_zh_index_daily()（新浪源），含成交量
        - 概念板块（code 是中文名称）：使用 ak.stock_board_concept_index_ths()，含成交量

        Args:
            code: 指数代码 (如 000001 上证指数、801030 申万行业、共封装光学(CPO) 概念板块)
            days: 获取天数

        Returns:
            List[Dict]: K 线数据列表，每条包含 date/open/close/high/low/volume/amount/change_pct
        """
        # 判断指数类型并选择数据源
        if code.startswith('80') and len(code) == 6:
            # 申万行业指数
            return self._fetch_kline_sw(code, days)
        elif code.isdigit() and len(code) == 6:
            # 市场指数
            return self._fetch_kline_sina(code, days)
        else:
            # 概念板块（code 是中文名称）
            return self._fetch_kline_concept(code, days)

    def _fetch_kline_sina(self, code: str, days: int = 30) -> List[Dict]:
        """获取市场指数 K 线（新浪源，含成交量）"""
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取 K 线数据")
            return []

        sina_symbol = self._code_to_sina_symbol(code)
        if not sina_symbol:
            self.logger.error(f"无法识别指数代码: {code}")
            return []

        try:
            df = ak.stock_zh_index_daily(symbol=sina_symbol)
            if df is None or df.empty:
                self.logger.warning(f"K 线数据为空: {code}")
                return []

            # 新浪源返回字段：date, open, high, low, close, volume
            results: List[Dict] = []
            prev_close = None

            for _, row in df.iterrows():
                try:
                    close = float(row.get('close', 0) or 0)
                    if prev_close and prev_close != 0:
                        change_pct = round((close - prev_close) / prev_close * 100, 4)
                        change = round(close - prev_close, 4)
                    else:
                        change_pct = 0.0
                        change = 0.0

                    results.append({
                        'date': str(row.get('date', '')),
                        'open': float(row.get('open', 0) or 0),
                        'close': close,
                        'high': float(row.get('high', 0) or 0),
                        'low': float(row.get('low', 0) or 0),
                        'volume': int(float(row.get('volume', 0) or 0)),
                        'amount': 0.0,  # 新浪源不提供成交额
                        'change_pct': change_pct,
                        'change': change,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析 K 线数据失败: {e}")
                    continue

            return results[-days:] if len(results) > days else results

        except Exception as e:
            self.logger.error(f"新浪源获取 K 线数据失败: {e}")
            return []

    def _fetch_kline_sw(self, code: str, days: int = 30) -> List[Dict]:
        """获取申万行业指数 K 线（申万宏源源，含成交量）"""
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取 K 线数据")
            return []

        try:
            df = ak.index_hist_sw(symbol=code, period='day')
            if df is None or df.empty:
                self.logger.warning(f"申万 K 线数据为空: {code}")
                return []

            # 申万源返回字段：代码、日期、收盘、开盘、最高、最低、成交量、成交额
            results: List[Dict] = []
            prev_close = None

            for _, row in df.iterrows():
                try:
                    close = float(row.get('收盘', 0) or 0)
                    if prev_close and prev_close != 0:
                        change_pct = round((close - prev_close) / prev_close * 100, 4)
                        change = round(close - prev_close, 4)
                    else:
                        change_pct = 0.0
                        change = 0.0

                    results.append({
                        'date': str(row.get('日期', '')),
                        'open': float(row.get('开盘', 0) or 0),
                        'close': close,
                        'high': float(row.get('最高', 0) or 0),
                        'low': float(row.get('最低', 0) or 0),
                        'volume': int(float(row.get('成交量', 0) or 0)),
                        'amount': float(row.get('成交额', 0) or 0),
                        'change_pct': change_pct,
                        'change': change,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析申万 K 线数据失败: {e}")
                    continue

            return results[-days:] if len(results) > days else results

        except Exception as e:
            self.logger.error(f"申万源获取 K 线数据失败: {e}")
            return []

    def _fetch_kline_concept(self, name: str, days: int = 30) -> List[Dict]:
        """获取概念板块 K 线（同花顺源，含成交量）

        Args:
            name: 概念板块名称（如 "共封装光学(CPO)"、"PCB概念"）
            days: 获取天数
        """
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取 K 线数据")
            return []

        try:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

            df = ak.stock_board_concept_index_ths(symbol=name, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                self.logger.warning(f"概念板块 K 线数据为空: {name}")
                return []

            # 同花顺源返回字段：日期、开盘价、最高价、最低价、收盘价、成交量、成交额
            results: List[Dict] = []
            prev_close = None

            for _, row in df.iterrows():
                try:
                    close = float(row.get('收盘价', 0) or 0)
                    if prev_close and prev_close != 0:
                        change_pct = round((close - prev_close) / prev_close * 100, 4)
                        change = round(close - prev_close, 4)
                    else:
                        change_pct = 0.0
                        change = 0.0

                    date_val = row.get('日期', '')
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)

                    results.append({
                        'date': date_str,
                        'open': float(row.get('开盘价', 0) or 0),
                        'close': close,
                        'high': float(row.get('最高价', 0) or 0),
                        'low': float(row.get('最低价', 0) or 0),
                        'volume': int(float(row.get('成交量', 0) or 0)),
                        'amount': float(row.get('成交额', 0) or 0),
                        'change_pct': change_pct,
                        'change': change,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析概念板块 K 线数据失败: {e}")
                    continue

            return results[-days:] if len(results) > days else results

        except Exception as e:
            self.logger.error(f"同花顺源获取概念板块 K 线失败: {e}")
            return []

    def _code_to_sina_symbol(self, code: str) -> str:
        """根据指数代码转换为新浪/腾讯源代码（sh/sz 前缀）"""
        # 深证系列指数（399 开头）
        if code.startswith('399'):
            return f'sz{code}'
        # 上证系列指数、中证系列指数
        return f'sh{code}'

    def fetch_and_cache_all_klines(self, db_path, days: int = 365) -> int:
        """
        批量获取所有指数的 K 线数据并缓存到数据库

        覆盖范围：
        - 市场指数（MARKET_INDICES）：source='sina'
        - 申万行业指数（从数据库读取代码列表）：source='sw'

        概念板块（同花顺源）K 线按需拉取，不参与批量缓存（数量多且名称动态变化）。

        Args:
            db_path: 数据库路径
            days: 获取天数

        Returns:
            总缓存条数
        """
        from src.db.index_dao import IndexDAO

        dao = IndexDAO(db_path)
        total_saved = 0

        # ===== 1. 缓存市场指数 K 线（新浪源） =====
        self.logger.info(f"开始批量缓存市场指数 K 线数据（{len(self.MARKET_INDICES)} 个指数）...")

        for item in self.MARKET_INDICES:
            code = item['code']
            name = item['name']
            try:
                klines = self.fetch_kline(code, days=days)
                if klines:
                    saved = dao.save_klines(code, klines, source='sina')
                    total_saved += saved
                    self.logger.info(f"  ✅ 市场指数 {name}({code}): 缓存 {saved} 条")
                else:
                    self.logger.warning(f"  ⚠️  市场指数 {name}({code}): K 线数据为空")
            except Exception as e:
                self.logger.error(f"  ❌ 市场指数 {name}({code}) 缓存失败: {e}")

        # ===== 2. 缓存申万行业指数 K 线（申万宏源源） =====
        try:
            industry_indices = dao.get_industry_indices(limit=500)
            # 过滤出申万行业指数（code 以 80 开头，6 位数字）
            sw_codes = [
                (idx.code, idx.name)
                for idx in industry_indices
                if idx.code.startswith('80') and len(idx.code) == 6 and idx.code.isdigit()
            ]
            self.logger.info(f"开始批量缓存申万行业指数 K 线数据（{len(sw_codes)} 个指数）...")

            for code, name in sw_codes:
                try:
                    klines = self.fetch_kline(code, days=days)
                    if klines:
                        saved = dao.save_klines(code, klines, source='sw')
                        total_saved += saved
                        self.logger.info(f"  ✅ 申万行业 {name}({code}): 缓存 {saved} 条")
                    else:
                        self.logger.warning(f"  ⚠️  申万行业 {name}({code}): K 线数据为空")
                except Exception as e:
                    self.logger.error(f"  ❌ 申万行业 {name}({code}) 缓存失败: {e}")
        except Exception as e:
            self.logger.error(f"读取申万行业指数列表失败，跳过该部分缓存: {e}")

        self.logger.info(f"K 线数据批量缓存完成: 共 {total_saved} 条")
        return total_saved

    def save_to_db(self, db_path) -> int:
        """
        获取指数数据并保存到数据库

        Args:
            db_path: 数据库路径

        Returns:
            保存的数据条数
        """
        from src.db.index_dao import IndexDAO

        indices = self.fetch()
        if not indices:
            self.logger.warning("未获取到指数数据")
            return 0

        dao = IndexDAO(db_path)
        saved = dao.save_indices(indices)
        self.logger.info(f"指数数据保存完成: {saved} 条")
        return saved
