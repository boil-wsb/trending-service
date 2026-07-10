"""
指数行情数据 Fetcher — 主力资金
通过 AKShare 获取，带重试，返回标准化 dict 列表。
"""

import logging
import math
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None


logger = logging.getLogger("index_fund_flow")


def _retry_akshare(func, *args, retries=1, delay=1.0, **kwargs):
    """带重试的 akshare 调用，默认只重试 1 次（避免 API 超时卡住）"""
    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < retries:
                logger.warning("akshare call failed (%s/%s): %s, retry in %ss..." % (attempt+1, retries, e, delay))
                time.sleep(delay)
            else:
                logger.error("akshare call failed (retried %s times): %s" % (retries, e))
                raise


def _safe_float(v, multiplier=1.0):
    """安全转 float，NaN/None 返回 None"""
    if v is None:
        return None
    try:
        f = float(v) * multiplier
        return None if math.isnan(f) else f
    except Exception:
        return None


# -------------------------------------------
# 1. 主力资金行业净流入排行
# -------------------------------------------


def fetch_sector_fund_flow(indicator="今日"):
    """获取行业主力资金净流入排行，使用 stock_fund_flow_industry
    返回值的单位：元（前端会 /1e8 显示为亿）
    增加流入比(inflow_ratio)和平均每家净流入(per_company)指标

    Args:
        indicator: 周期，可选 '今日'/'5日'/'10日'（映射到 AKShare symbol）
    """
    if not HAS_AKSHARE:
        logger.warning("akshare not installed")
        return []

    # AKShare stock_fund_flow_industry 支持的 symbol：
    # "即时"(默认)、"3日排行"、"5日排行"、"10日排行"、"20日排行"
    # 前端传入 "今日"/"5日"/"10日" 需要映射
    symbol_map = {"今日": "即时", "5日": "5日排行", "10日": "10日排行"}
    ak_symbol = symbol_map.get(indicator, "即时")

    try:
        df = _retry_akshare(ak.stock_fund_flow_industry, symbol=ak_symbol)
        result = []
        for _, row in df.iterrows():
            name = str(row.get("行业", "")).strip()
            net = _safe_float(row.get("净额"), multiplier=1e8) or 0.0
            inflow = _safe_float(row.get("流入资金"), multiplier=1e8) or 0.0
            outflow = _safe_float(row.get("流出资金"), multiplier=1e8) or 0.0
            # 涨跌幅列名不同："即时"模式为"行业-涨跌幅"(数值)，
            # "5日排行"等模式为"阶段涨跌幅"(字符串"3.60%")
            pct_raw = row.get("行业-涨跌幅")
            if pct_raw is None or (isinstance(pct_raw, float) and math.isnan(pct_raw)):
                pct_raw = row.get("阶段涨跌幅")
            pct = _safe_float(str(pct_raw).strip("%") if pct_raw is not None else "0") or 0.0
            try:
                company_cnt = int(row.get("公司家数", 0) or 0)
            except (ValueError, TypeError):
                company_cnt = 0
            total_flow = inflow + outflow
            inflow_ratio = (inflow / total_flow * 100) if total_flow > 0 else 50.0
            if pct > 0 and net > 0:
                divergence = 1
            elif pct > 0 and net < 0:
                divergence = 2
            elif pct < 0 and net > 0:
                divergence = 3
            else:
                divergence = 4
            result.append({
                "name": name,
                "main_in_flow": net,
                "inflow": inflow,
                "outflow": outflow,
                "change_pct": pct,
                "inflow_ratio": inflow_ratio,
                "per_company": net / company_cnt if company_cnt > 0 else 0,
                "company_cnt": company_cnt,
                "divergence": divergence,
            })
        result.sort(key=lambda x: x["main_in_flow"], reverse=True)
        return result
    except Exception as e:
        logger.error("获取行业资金流失败: %s" % e)
        return []
