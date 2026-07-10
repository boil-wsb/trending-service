"""
指数行情数据获取器
获取 A 股市场指数（AKShare 新浪源）+ 申万行业指数（AKShare）

注意：不继承 BaseFetcher，因为 BaseFetcher 返回 TrendingItem 不适用于指数数据。
"""

import sys
import math
from typing import List, Dict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES
from src.utils import get_logger
from src.utils.symbol import normalize_symbol, to_kline_source, AssetType
from src.db.models import IndexData


def _safe_float(v, default=0.0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        f = float(v)
        return default if math.isnan(f) else f
    except Exception:
        return default


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
        获取所有指数数据（市场指数 + 行业指数 + 概念板块白名单）

        概念板块按 config.yaml 的 data_sources.index.concept_watchlist 白名单
        抓取（东财源 494 个中筛选），留空则不抓取。

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

        # 获取概念板块（按 config.yaml 白名单筛选）
        watchlist = self.config.get('concept_watchlist', []) if self.config else []
        if watchlist:
            try:
                concept_indices = self.fetch_concept_indices(watchlist)
                all_indices.extend(concept_indices)
                self.logger.info(f"获取概念板块完成: {len(concept_indices)} 条 (白名单 {len(watchlist)} 项)")
            except Exception as e:
                self.logger.error(f"获取概念板块失败: {e}")
        else:
            self.logger.debug("概念板块白名单为空，跳过概念板块抓取")

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
                        price=_safe_float(row.get('最新价', 0)),
                        change=_safe_float(row.get('涨跌额', 0)),
                        change_pct=_safe_float(row.get('涨跌幅', 0)),
                        high=_safe_float(row.get('最高', 0)),
                        low=_safe_float(row.get('最低', 0)),
                        open=_safe_float(row.get('今开', 0)),
                        pre_close=_safe_float(row.get('昨收', 0)),
                        volume=int(_safe_float(row.get('成交量', 0))),
                        amount=_safe_float(row.get('成交额', 0)),
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
                    price = _safe_float(row.get('最新价', 0))
                    pre_close = _safe_float(row.get('昨收盘', 0))
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
                        high=_safe_float(row.get('最高价', 0)),
                        low=_safe_float(row.get('最低价', 0)),
                        open=_safe_float(row.get('今开盘', 0)),
                        pre_close=pre_close,
                        volume=int(_safe_float(row.get('成交量', 0))),
                        amount=_safe_float(row.get('成交额', 0)),
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

    def fetch_concept_indices(self, watchlist: List[str] = None) -> List[IndexData]:
        """
        获取 A 股概念板块实时行情

        主数据源：ak.stock_board_concept_name_em()（东方财富，稳定，494+ 板块）。
        备用数据源：ak.stock_fund_flow_concept(symbol='即时')（同花顺，含资金净额）。

        同花顺源在某些时段会因反爬返回 None 导致
        "'NoneType' object has no attribute 'text'" 错误，故改为东方财富优先、
        同花顺兜底，并对主源做 2 次重试。

        概念板块合并到行业指数中展示（category='industry'），source='em'/'ths'。

        Args:
            watchlist: 概念板块名称白名单（关键词包含匹配，大小写不敏感）。
                       为空或 None 则返回全部概念板块。

        Returns:
            List[IndexData]: 概念板块数据列表
        """
        self.logger.info(f"开始获取概念板块行情... (白名单: {len(watchlist) if watchlist else 0} 项)")
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取概念板块。请运行: pip install akshare")
            return []

        # 1) 主源：东方财富 stock_board_concept_name_em（含 market_cap）
        em_results = self._fetch_concept_via_em(ak)
        if em_results:
            em_results = self._filter_concept_by_watchlist(em_results, watchlist)
            self.logger.info(f"概念板块（东方财富源）获取成功: {len(em_results)} 条")

        # 2) 备用源：同花顺 stock_fund_flow_concept（含 amount/资金净额）
        ths_results = self._fetch_concept_via_ths(ak)
        if ths_results:
            ths_results = self._filter_concept_by_watchlist(ths_results, watchlist)
            self.logger.info(f"概念板块（同花顺源）获取成功: {len(ths_results)} 条")

        # 3) 合并：em 提供 market_cap，ths 提供 amount，同 code 时合并
        if em_results and ths_results:
            merged = self._merge_concept_sources(em_results, ths_results)
            self.logger.info(f"概念板块合并完成: {len(merged)} 条 (em={len(em_results)}, ths={len(ths_results)})")
            return merged
        elif em_results:
            return em_results
        elif ths_results:
            return ths_results
        else:
            self.logger.warning("所有概念板块数据源均未返回数据")
            return []

    # 概念板块白名单别名映射
    # key=白名单项, value=数据源中可能的别名列表
    CONCEPT_ALIASES = {
        "新能源车": ["新能源汽车"],
        "储能概念": ["储能"],
        "燃料电池概念": ["燃料电池"],
        "半导体概念": ["半导体"],
        "AI芯片": ["AI芯片概念"],
        "算力概念": ["算力", "数据中心", "云计算"],
        "CPO概念": ["CPO", "共封装光学"],
        "国产芯片": ["国产替代", "芯片"],
        "AIGC概念": ["AIGC", "生成式AI"],
        "AIPC": ["AI PC", "AI电脑"],
        "创新药": ["创新药产业链", "创新药研发", "生物医药"],
    }

    def _filter_concept_by_watchlist(self, indices: List[IndexData], watchlist: List[str]) -> List[IndexData]:
        """按白名单关键词过滤概念板块（名称包含匹配，大小写不敏感）。

        匹配规则：
        1. 白名单项是数据源名称的子串 → 匹配
        2. 数据源名称是白名单项的子串 → 匹配
        3. 去掉"概念"后缀后再做子串匹配 → 匹配
        4. 别名映射表中的别名匹配 → 匹配

        watchlist 为空或 None 时返回全部。
        """
        if not watchlist:
            return indices
        matched = []
        for idx in indices:
            name_lower = idx.name.lower()
            name_no_suffix = name_lower.replace("概念", "").strip()
            for w in watchlist:
                w_lower = w.lower()
                w_no_suffix = w_lower.replace("概念", "").strip()
                # 规则1: 白名单项是名称的子串
                if w_lower in name_lower:
                    matched.append(idx)
                    break
                # 规则2: 去掉"概念"后缀后匹配
                if w_no_suffix and w_no_suffix in name_no_suffix:
                    matched.append(idx)
                    break
                # 规则3: 别名映射
                aliases = self.CONCEPT_ALIASES.get(w, [])
                if any(a.lower() in name_lower for a in aliases):
                    matched.append(idx)
                    break
        if len(matched) < len(indices):
            self.logger.debug(f"概念板块白名单过滤: {len(indices)} -> {len(matched)}")
        return matched

    def _fetch_concept_via_em(self, ak_module) -> List[IndexData]:
        """通过东方财富 stock_board_concept_name_em 获取概念板块（带重试）。

        优化措施：
        - 3 次重试，间隔递增（2s/4s）
        - 每次重试前设置随机 User-Agent，降低被反爬概率
        """
        import time
        import random
        max_retries = 3
        now = datetime.now()
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        ]
        for attempt in range(1, max_retries + 1):
            try:
                df = ak_module.stock_board_concept_name_em()
                if df is None or df.empty:
                    self.logger.warning(f"东方财富概念板块返回空数据 (尝试 {attempt}/{max_retries})")
                    continue

                results: List[IndexData] = []
                # 字段：排名、板块名称、板块代码、最新价、涨跌额、涨跌幅、
                #       总市值、换手率、上涨家数、下跌家数、领涨股票、领涨股票-涨跌幅
                for _, row in df.iterrows():
                    try:
                        name = str(row.get('板块名称', '')).strip()
                        if not name:
                            continue
                        price = _safe_float(row.get('最新价', 0))
                        change_pct = _safe_float(row.get('涨跌幅', 0))
                        change = _safe_float(row.get('涨跌额', 0))
                        turnover_rate = _safe_float(row.get('换手率', 0))
                        market_cap = _safe_float(row.get('总市值', 0))

                        # 代码使用概念名称（概念板块无统一数字代码）
                        code = name

                        index = IndexData(
                            code=code,
                            name=name,
                            category='industry',  # 合并到行业指数展示
                            price=price,
                            change=change,
                            change_pct=change_pct,
                            high=0.0,  # 概念板块无最高价
                            low=0.0,   # 概念板块无最低价
                            open=0.0,  # 概念板块无开盘价
                            pre_close=round(price - change, 2) if price else 0.0,
                            volume=0,
                            amount=0.0,
                            turnover_rate=turnover_rate,
                            market_cap=market_cap,
                            source='em',
                            fetched_at=now,
                        )
                        results.append(index)
                    except (ValueError, KeyError, TypeError) as e:
                        self.logger.warning(f"解析概念板块数据失败: {e}, row: {row.to_dict()}")
                        continue
                return results
            except Exception as e:
                self.logger.warning(f"东方财富源获取概念板块失败 (尝试 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)  # 递增间隔: 2s, 4s
        return []

    def _merge_concept_sources(self, em_results: List[IndexData], ths_results: List[IndexData]) -> List[IndexData]:
        """合并东方财富和同花顺概念板块数据。

        合并策略：
        - em 源提供：market_cap、turnover_rate（东方财富特有）
        - ths 源提供：amount（资金净额，同花顺特有）
        - 同 code 时：以 em 为基础，补齐 ths 的 amount；source 标记为 'em'（主源）
        - 仅 ths 有的：尝试用名称归一化匹配 em（去括号/后缀），匹配则补齐 market_cap
        - 仍无法匹配的 ths 记录：保留，source='ths'，market_cap=0

        Returns:
            合并后的概念板块列表
        """
        import re

        def normalize_name(name: str) -> str:
            """归一化概念板块名称：去括号内容、去常见后缀、统一大小写"""
            # 去括号及内容：共封装光学(CPO) → 共封装光学
            s = re.sub(r'[（(].*?[)）]', '', name)
            # 去常见后缀
            for suffix in ['概念', '板块', '指数']:
                if s.endswith(suffix):
                    s = s[:-len(suffix)]
            return s.strip().lower()

        # 以 code 为 key 建立索引
        em_map = {idx.code: idx for idx in em_results}
        ths_map = {idx.code: idx for idx in ths_results}

        # 以归一化名称建立 em/ths 索引（用于跨源名称匹配）
        em_name_map = {}
        for idx in em_results:
            norm = normalize_name(idx.name)
            if norm not in em_name_map:
                em_name_map[norm] = idx
        ths_name_map = {}
        for idx in ths_results:
            norm = normalize_name(idx.name)
            if norm not in ths_name_map:
                ths_name_map[norm] = idx

        def find_ths_by_name(em_idx: IndexData):
            """先按 code 精确匹配，再按归一化名称匹配，再按子串包含匹配"""
            # 1) code 精确匹配
            ths_idx = ths_map.get(em_idx.code)
            if ths_idx:
                return ths_idx
            # 2) 归一化名称匹配
            norm = normalize_name(em_idx.name)
            ths_idx = ths_name_map.get(norm)
            if ths_idx:
                return ths_idx
            # 3) 子串包含匹配（双向）：新能源车 ↔ 新能源汽车
            for ths_name, ths_item in ths_name_map.items():
                if len(norm) >= 3 and len(ths_name) >= 3:
                    if norm in ths_name or ths_name in norm:
                        return ths_item
            return None

        def find_em_by_name(ths_idx: IndexData):
            """先按归一化名称匹配，再按子串包含匹配"""
            norm = normalize_name(ths_idx.name)
            # 1) 归一化名称匹配
            em_match = em_name_map.get(norm)
            if em_match:
                return em_match
            # 2) 子串包含匹配（双向）
            for em_name, em_item in em_name_map.items():
                if len(norm) >= 3 and len(em_name) >= 3:
                    if norm in em_name or em_name in norm:
                        return em_item
            return None

        merged: List[IndexData] = []
        merged_codes = set()
        amount_filled_count = 0

        # 1) em 有的：补齐 ths 的 amount（先按 code 精确匹配，再按名称匹配）
        for code, em_idx in em_map.items():
            ths_idx = find_ths_by_name(em_idx)
            if ths_idx and ths_idx.amount:
                em_idx.amount = ths_idx.amount
                amount_filled_count += 1
            merged.append(em_idx)
            merged_codes.add(code)

        # 2) 仅 ths 有的：尝试用名称匹配 em，补齐 market_cap
        ths_only_count = 0
        ths_matched_count = 0
        for code, ths_idx in ths_map.items():
            if code in merged_codes:
                continue
            ths_only_count += 1
            em_match = find_em_by_name(ths_idx)
            if em_match and em_match.market_cap:
                ths_idx.market_cap = em_match.market_cap
                if not ths_idx.turnover_rate:
                    ths_idx.turnover_rate = em_match.turnover_rate
                ths_matched_count += 1
            merged.append(ths_idx)

        if ths_only_count > 0:
            self.logger.info(
                f"概念板块合并：ths 独有 {ths_only_count} 个，"
                f"名称匹配补齐 market_cap {ths_matched_count} 个，"
                f"未匹配 {ths_only_count - ths_matched_count} 个"
            )
        self.logger.info(
            f"概念板块合并：em 记录补齐 amount {amount_filled_count}/{len(em_results)} 个"
        )

        return merged

    def _fetch_concept_via_ths(self, ak_module) -> List[IndexData]:
        """通过同花顺 stock_fund_flow_concept 获取概念板块（备用源，带重试）。

        同花顺源在某些时段会因反爬返回 None 导致
        "'NoneType' object has no attribute 'text'" 错误，故增加 3 次重试，
        间隔递增（2s/4s），每次重试前设置随机 User-Agent。
        """
        import time
        import random
        max_retries = 3
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        ]
        now = datetime.now()
        for attempt in range(1, max_retries + 1):
            try:
                df = ak_module.stock_fund_flow_concept(symbol='即时')
                if df is None or df.empty:
                    self.logger.warning(f"同花顺概念板块返回空数据 (尝试 {attempt}/{max_retries})")
                    if attempt < max_retries:
                        time.sleep(2 * attempt)
                        continue
                    return []

                results: List[IndexData] = []
                # 字段：序号、行业、行业指数、行业-涨跌幅、流入资金、流出资金、
                #       净额、公司家数、领涨股、领涨股-涨跌幅、当前价
                for _, row in df.iterrows():
                    try:
                        name = str(row.get('行业', '')).strip()
                        if not name:
                            continue
                        price = _safe_float(row.get('行业指数', 0))
                        change_pct = _safe_float(row.get('行业-涨跌幅', 0))
                        current_price = _safe_float(row.get('当前价', 0))
                        if price == 0 and current_price > 0:
                            price = current_price

                        code = name  # 概念板块无标准代码
                        index = IndexData(
                            code=code,
                            name=name,
                            category='industry',
                            price=price,
                            change=round(price * change_pct / 100, 2) if price else 0.0,
                            change_pct=change_pct,
                            high=0.0,
                            low=0.0,
                            open=0.0,
                            pre_close=round(price * (1 - change_pct / 100), 2) if price else 0.0,
                            volume=0,
                            amount=_safe_float(row.get('净额', 0)),  # 净额作为成交额参考
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
                self.logger.error(f"同花顺源获取概念板块失败 (尝试 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                else:
                    return []
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
        # 判断指数类型并选择数据源（统一走 normalize_symbol 解析）
        sym = normalize_symbol(code)
        if sym.asset_type == AssetType.INDUSTRY_INDEX:
            # 申万行业指数
            return self._fetch_kline_sw(code, days)
        elif sym.asset_type == AssetType.MARKET_INDEX:
            # 市场指数
            return self._fetch_kline_sina(code, days)
        else:
            # 概念板块（code 是中文名称）
            return self._fetch_kline_concept(code, days)

    def _fetch_kline_sina(self, code: str, days: int = 30) -> List[Dict]:
        """获取市场指数 K 线（新浪源优先，东方财富兜底，含成交量）"""
        try:
            import akshare as ak
        except ImportError:
            self.logger.error("AKShare 未安装，无法获取 K 线数据")
            return []

        sina_symbol = self._code_to_sina_symbol(code)
        if not sina_symbol:
            self.logger.error(f"无法识别指数代码: {code}")
            return []

        # 1) 先尝试新浪源
        results = self._fetch_kline_via_sina(ak, sina_symbol, code, days)
        if results:
            return results

        # 2) 新浪源失败或为空，回退到东方财富源
        self.logger.info(f"新浪源 K 线为空，尝试东方财富源: {code}")
        results = self._fetch_kline_via_em(ak, code, days)
        return results

    def _fetch_kline_via_sina(self, ak_module, sina_symbol: str, code: str, days: int) -> List[Dict]:
        """新浪源获取 K 线"""
        try:
            df = ak_module.stock_zh_index_daily(symbol=sina_symbol)
            if df is None or df.empty:
                return []

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

                    date_val = row.get('date', '')
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)

                    results.append({
                        'date': date_str,
                        'open': float(row.get('open', 0) or 0),
                        'close': close,
                        'high': float(row.get('high', 0) or 0),
                        'low': float(row.get('low', 0) or 0),
                        'volume': int(float(row.get('volume', 0) or 0)),
                        'amount': 0.0,
                        'change_pct': change_pct,
                        'change': change,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析 K 线数据失败: {e}")
                    continue

            return results[-days:] if len(results) > days else results
        except Exception as e:
            self.logger.warning(f"新浪源获取 K 线失败: {e}")
            return []

    def _fetch_kline_via_em(self, ak_module, code: str, days: int) -> List[Dict]:
        """东方财富源获取 K 线（stock_zh_index_daily_em）
        symbol 格式：sh000001 / sz399001
        """
        try:
            em_symbol = self._code_to_sina_symbol(code)  # 复用 sh/sz 前缀逻辑
            df = ak_module.stock_zh_index_daily_em(symbol=em_symbol)
            if df is None or df.empty:
                return []

            # 东方财富源返回字段：date, open, high, low, close, volume, amount
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

                    date_val = row.get('date', '')
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)

                    results.append({
                        'date': date_str,
                        'open': float(row.get('open', 0) or 0),
                        'close': close,
                        'high': float(row.get('high', 0) or 0),
                        'low': float(row.get('low', 0) or 0),
                        'volume': int(float(row.get('volume', 0) or 0)),
                        'amount': float(row.get('amount', 0) or 0),
                        'change_pct': change_pct,
                        'change': change,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"解析东方财富 K 线失败: {e}")
                    continue

            return results[-days:] if len(results) > days else results
        except Exception as e:
            self.logger.warning(f"东方财富源获取 K 线失败: {e}")
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

            # 尝试用原始 name 获取，失败后遍历 CONCEPT_ALIASES 中的别名
            # 同花顺源的概念名称可能与白名单名不一致（如白名单"CPO概念"，同花顺叫"共封装光学(CPO)"）
            candidates = [name]
            aliases = self.CONCEPT_ALIASES.get(name, [])
            # 去掉"概念"后缀的变体也加入候选
            if name.endswith('概念'):
                candidates.append(name[:-2])
            candidates.extend(aliases)

            df = None
            tried_names = []
            for sym in candidates:
                try:
                    tried_names.append(sym)
                    df = ak.stock_board_concept_index_ths(symbol=sym, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue

            if df is None or df.empty:
                self.logger.warning(f"概念板块 K 线数据为空: {name}（已尝试: {tried_names}）")
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

    @staticmethod
    def aggregate_kline(daily_klines: List[Dict], period: str) -> List[Dict]:
        """将日K数据聚合为周K/月K

        聚合规则：
        - open=首日open, close=末日close, high=max(high), low=min(low), volume=sum(volume)
        - 周K：按自然周（周一到周日）聚合
        - 月K：按自然月聚合
        - 每组的代表日期取该组最后一个交易日的日期

        Args:
            daily_klines: 日K数据列表（按日期升序），每条含 date/open/close/high/low/volume/amount
            period: 'week' 或 'month'，其他值原样返回

        Returns:
            聚合后的K线数据列表（含重新计算的 change_pct/change）
        """
        if not daily_klines or period not in ('week', 'month'):
            return daily_klines

        from datetime import datetime

        def _period_key(date_str):
            """根据周期返回分组键"""
            try:
                dt = datetime.strptime(str(date_str), '%Y-%m-%d')
            except (ValueError, TypeError):
                return None
            if period == 'week':
                # isocalendar 返回 (ISO年, 周数, 周几)；用前两项作为分组键
                iso = dt.isocalendar()
                return (iso[0], iso[1])
            else:  # month
                return (dt.year, dt.month)

        # 按周期分组（保持原始升序）
        groups = []  # [(key, [klines])]
        current_key = None
        current_group = []
        for k in daily_klines:
            key = _period_key(k.get('date', ''))
            if key is None:
                continue
            if key != current_key:
                if current_group:
                    groups.append((current_key, current_group))
                current_key = key
                current_group = [k]
            else:
                current_group.append(k)
        if current_group:
            groups.append((current_key, current_group))

        # 聚合每组数据
        result = []
        prev_close = None
        for _key, group in groups:
            first = group[0]
            last = group[-1]
            open_val = first['open']
            close_val = last['close']
            high_val = max(k['high'] for k in group)
            low_val = min(k['low'] for k in group)
            volume_val = sum(k.get('volume', 0) for k in group)
            amount_val = sum(k.get('amount', 0) for k in group)

            if prev_close and prev_close != 0:
                change_pct = round((close_val - prev_close) / prev_close * 100, 4)
                change = round(close_val - prev_close, 4)
            else:
                change_pct = 0.0
                change = 0.0

            result.append({
                'date': last['date'],
                'open': open_val,
                'close': close_val,
                'high': high_val,
                'low': low_val,
                'volume': volume_val,
                'amount': amount_val,
                'change_pct': change_pct,
                'change': change,
            })
            prev_close = close_val

        return result

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
        - 概念板块（config.yaml concept_watchlist 白名单）：source='ths'

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
            industry_indices = dao.get_industry_indices(limit=10000)
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

        # ===== 3. 缓存概念板块 K 线（同花顺源，按 config 白名单） =====
        try:
            watchlist = self.config.get('concept_watchlist', []) if self.config else []
            if watchlist:
                self.logger.info(f"开始批量缓存概念板块 K 线数据（白名单 {len(watchlist)} 项）...")
                concept_saved = 0
                concept_failed = 0
                for name in watchlist:
                    try:
                        # 概念板块 code 即为名称（中文）
                        klines = self._fetch_kline_concept(name, days=days)
                        if klines:
                            saved = dao.save_klines(name, klines, source='ths')
                            total_saved += saved
                            concept_saved += 1
                        else:
                            self.logger.warning(f"  ⚠️  概念板块 {name}: K 线数据为空")
                    except Exception as e:
                        concept_failed += 1
                        self.logger.error(f"  ❌ 概念板块 {name} 缓存失败: {e}")
                self.logger.info(
                    f"概念板块 K 线缓存完成: 成功 {concept_saved} 个, 失败 {concept_failed} 个"
                )
            else:
                self.logger.debug("概念板块白名单为空，跳过概念板块 K 线缓存")
        except Exception as e:
            self.logger.error(f"缓存概念板块 K 线失败: {e}")

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
