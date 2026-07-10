"""
北向资金数据 Fetcher — 沪深港通每日净流入
通过 AKShare 获取，返回标准化 dict。
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

logger = logging.getLogger("index_northbound")


def _safe_float(v, default=0.0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        return float(v)
    except Exception:
        return default


def fetch_northbound_flow(days: int = 30) -> dict:
    """获取北向资金每日净流入数据

    Args:
        days: 查询近 N 日数据

    Returns:
        {
            'dates': ['2026-06-10', ...],
            'total_net_flow': [12.5, -3.2, ...],  # 北向合计净流入（亿元）
            'sh_net_flow': [8.2, -1.5, ...],      # 沪股通净流入（亿元）
            'sz_net_flow': [4.3, -1.7, ...],      # 深股通净流入（亿元）
            'latest': {
                'date': '2026-07-10',
                'total': 12.5,
                'sh': 8.2,
                'sz': 4.3,
            },
            'summary': {
                'total_5d': 35.2,       # 近5日累计净流入
                'total_20d': -15.8,     # 近20日累计净流入
                'avg_daily': 1.2,       # 日均净流入
            }
        }
    """
    if not HAS_AKSHARE:
        logger.warning("akshare not installed")
        return _empty_result()

    try:
        # 分别获取北上/沪股通/深股通数据
        df_total = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        df_sh = ak.stock_hsgt_north_net_flow_in_em(symbol="沪股通")
        df_sz = ak.stock_hsgt_north_net_flow_in_em(symbol="深股通")

        # 统一处理：取最近 N 日，按日期升序
        dates = []
        total_flow = []
        sh_flow = []
        sz_flow = []

        if df_total is not None and len(df_total) > 0:
            df_total = df_total.tail(days)
            for _, row in df_total.iterrows():
                d = row.get('date', '')
                # 日期格式可能为 '2026-07-10' 或 Timestamp
                if hasattr(d, 'strftime'):
                    d = d.strftime('%Y-%m-%d')
                else:
                    d = str(d)
                dates.append(d[:10])
                total_flow.append(round(_safe_float(row.get('value')) / 10000, 2))  # 万元→亿元

        if df_sh is not None and len(df_sh) > 0:
            df_sh = df_sh.tail(days)
            for _, row in df_sh.iterrows():
                sh_flow.append(round(_safe_float(row.get('value')) / 10000, 2))

        if df_sz is not None and len(df_sz) > 0:
            df_sz = df_sz.tail(days)
            for _, row in df_sz.iterrows():
                sz_flow.append(round(_safe_float(row.get('value')) / 10000, 2))

        # 以 dates 为基准对齐，单源缺失填充 None 而非截断全部
        while len(sh_flow) < len(dates):
            sh_flow.insert(0, None)
        while len(sz_flow) < len(dates):
            sz_flow.insert(0, None)
        # 如果 sh_flow 比 dates 长（不应发生），截断
        sh_flow = sh_flow[-len(dates):] if len(sh_flow) > len(dates) else sh_flow
        sz_flow = sz_flow[-len(dates):] if len(sz_flow) > len(dates) else sz_flow

        if not dates:
            return _empty_result()

        # 最新数据
        latest = {
            'date': dates[-1],
            'total': total_flow[-1] if total_flow else 0,
            'sh': sh_flow[-1] if sh_flow else 0,
            'sz': sz_flow[-1] if sz_flow else 0,
        }

        # 汇总统计
        total_5d = round(sum(total_flow[-5:]), 2) if len(total_flow) >= 5 else round(sum(total_flow), 2)
        total_20d = round(sum(total_flow[-20:]), 2) if len(total_flow) >= 20 else round(sum(total_flow), 2)
        avg_daily = round(sum(total_flow) / len(total_flow), 2) if total_flow else 0

        return {
            'dates': dates,
            'total_net_flow': total_flow,
            'sh_net_flow': sh_flow,
            'sz_net_flow': sz_flow,
            'latest': latest,
            'summary': {
                'total_5d': total_5d,
                'total_20d': total_20d,
                'avg_daily': avg_daily,
            }
        }
    except Exception as e:
        logger.error(f"获取北向资金数据失败: {e}")
        return _empty_result()


def _empty_result():
    return {
        'dates': [],
        'total_net_flow': [],
        'sh_net_flow': [],
        'sz_net_flow': [],
        'latest': {'date': '', 'total': 0, 'sh': 0, 'sz': 0},
        'summary': {'total_5d': 0, 'total_20d': 0, 'avg_daily': 0}
    }
