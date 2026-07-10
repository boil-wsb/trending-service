"""
市场情绪数据 Fetcher — 涨跌停统计
通过 AKShare 获取涨停/跌停/炸板数据，返回标准化 dict。
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, List

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None

logger = logging.getLogger("index_sentiment")


def _safe_int(v, default=0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v, default=0.0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        return float(v)
    except Exception:
        return default


def fetch_limit_up_stats(date_str: Optional[str] = None) -> dict:
    """获取涨跌停统计数据

    Args:
        date_str: 日期字符串 'YYYYMMDD'，默认今天

    Returns:
        {
            'date': '2026-07-10',
            'limit_up_count': 45,      # 涨停家数
            'limit_down_count': 3,     # 跌停家数
            'broken_limit_count': 8,   # 炸板家数
            'broken_rate': 15.1,       # 炸板率 = 炸板数 / (涨停数 + 炸板数) * 100
            'max_consecutive': 5,      # 最高连板数
            'consecutive_tiers': [     # 连板梯队
                {'tier': 5, 'count': 1, 'stocks': [{'code': '...', 'name': '...', 'reason': '...'}]},
                {'tier': 4, 'count': 2, 'stocks': [...]},
                ...
            ],
            'limit_up_top': [...],     # 涨停代表个股（按连板数降序）
            'sentiment_score': 65.0,   # 情绪温度计 0-100
        }
    """
    if not HAS_AKSHARE:
        logger.warning("akshare not installed")
        return _empty_result(date_str)

    if not date_str:
        date_str = datetime.now().strftime('%Y%m%d')

    try:
        # 1. 涨停板池
        df_zt = ak.stock_zt_pool_em(date=date_str)
        limit_up_list = []
        if df_zt is not None and len(df_zt) > 0:
            for _, row in df_zt.iterrows():
                limit_up_list.append({
                    'code': str(row.get('代码', '')),
                    'name': str(row.get('名称', '')),
                    'change_pct': _safe_float(row.get('涨跌幅')),
                    'amount': _safe_float(row.get('成交额')),
                    'consecutive': _safe_int(row.get('连板数'), 1),
                    'first_limit_time': str(row.get('首次封板时间', '')),
                    'open_count': _safe_int(row.get('炸板次数')),
                    'reason': str(row.get('涨停原因', ''))[:100],
                })

        limit_up_count = len(limit_up_list)

        # 2. 跌停板池
        limit_down_count = 0
        try:
            df_dt = ak.stock_zt_pool_dtgc_em(date=date_str)
            if df_dt is not None:
                limit_down_count = len(df_dt)
        except Exception as e:
            logger.warning(f"获取跌停板池失败: {e}")

        # 3. 炸板池
        broken_count = 0
        try:
            df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
            if df_zb is not None:
                broken_count = len(df_zb)
        except Exception as e:
            logger.warning(f"获取炸板池失败: {e}")

        # 4. 炸板率
        total_attempt = limit_up_count + broken_count
        broken_rate = round(broken_count / total_attempt * 100, 1) if total_attempt > 0 else 0

        # 5. 连板梯队
        consecutive_map = {}
        for stock in limit_up_list:
            tier = stock['consecutive']
            if tier not in consecutive_map:
                consecutive_map[tier] = []
            consecutive_map[tier].append(stock)

        consecutive_tiers = []
        for tier in sorted(consecutive_map.keys(), reverse=True):
            stocks = consecutive_map[tier]
            consecutive_tiers.append({
                'tier': tier,
                'count': len(stocks),
                'stocks': [{'code': s['code'], 'name': s['name'], 'reason': s['reason']} for s in stocks[:5]]
            })

        max_consecutive = max([s['consecutive'] for s in limit_up_list], default=0)

        # 6. 涨停代表个股（按连板数降序，取前10）
        limit_up_top = sorted(limit_up_list, key=lambda x: x['consecutive'], reverse=True)[:10]

        # 7. 情绪温度计（0-100）
        # 综合涨停家数 + 连板高度 + 炸板率
        # 涨停家数得分：0家=0, 30家=50, 80家=80, 150家=100
        count_score = min(100, limit_up_count / 150 * 100) if limit_up_count > 0 else 0
        # 连板高度得分：0板=0, 3板=40, 5板=60, 8板=80, 10板=100
        consec_score = min(100, max_consecutive / 10 * 100) if max_consecutive > 0 else 0
        # 炸板率扣分：炸板率越高情绪越差
        broken_penalty = broken_rate * 0.3
        sentiment_score = round(max(0, min(100, count_score * 0.4 + consec_score * 0.4 - broken_penalty + 10)), 1)

        return {
            'date': f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}',
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'broken_limit_count': broken_count,
            'broken_rate': broken_rate,
            'max_consecutive': max_consecutive,
            'consecutive_tiers': consecutive_tiers,
            'limit_up_top': limit_up_top,
            'sentiment_score': sentiment_score,
        }
    except Exception as e:
        logger.error(f"获取涨跌停统计失败: {e}")
        return _empty_result(date_str)


def _empty_result(date_str):
    d = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}' if date_str and len(date_str) == 8 else datetime.now().strftime('%Y-%m-%d')
    return {
        'date': d,
        'limit_up_count': 0,
        'limit_down_count': 0,
        'broken_limit_count': 0,
        'broken_rate': 0,
        'max_consecutive': 0,
        'consecutive_tiers': [],
        'limit_up_top': [],
        'sentiment_score': 0,
    }
