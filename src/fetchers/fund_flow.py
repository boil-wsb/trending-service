"""
指数行情数据 Fetcher — 主力资金 / 风格轮动 / 北向资金
通过 AKShare 获取，带重试，返回标准化 dict 列表。
"""

import logging
import time
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


# -------------------------------------------
# 1. 主力资金行业净流入排行
# -------------------------------------------


def fetch_sector_fund_flow(indicator="今日"):
    """获取行业主力资金净流入排行，使用 stock_fund_flow_industry
    返回值的单位：元（前端会 /1e8 显示为亿）
    增加流入比(inflow_ratio)和平均每家净流入(per_company)指标
    """
    if not HAS_AKSHARE:
        logger.warning("akshare not installed")
        return []
    try:
        df = _retry_akshare(ak.stock_fund_flow_industry)
        result = []
        for _, row in df.iterrows():
            name = str(row.get("行业", "")).strip()
            net = float(row.get("净额", 0) or 0) * 100000000
            inflow = float(row.get("流入资金", 0) or 0) * 100000000
            outflow = float(row.get("流出资金", 0) or 0) * 100000000
            pct = float(row.get("行业-涨跌幅", 0) or 0)
            company_cnt = int(row.get("公司家数", 0) or 0)
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


# -------------------------------------------
# 2. 风格轮动强弱
# -------------------------------------------

# 沪深300风格指数（可在 stock_zh_index_spot_em 中查到）
# 注：国证风格指数(100032等)在 akshare 1.18 与 pandas 2.x 存在兼容问题，
# 暂用沪深300风格指数替代
STYLE_INDEX_NAMES = {
    "300价值": "000919",
    "300成长": "000918",
    "300信息": "000915",
    "300通信": "000916",
    "300公用": "000917",
    "300金融": "000914",
}


def fetch_style_index_realtime():
    """获取风格指数实时行情（从 stock_zh_index_spot_em 过滤沪深300风格指数）
    返回: [ {name, code, price, change_pct}, ... ]
    """
    if not HAS_AKSHARE:
        return []
    try:
        logger.info("fetch_style_index_realtime: calling stock_zh_index_spot_em")
        df = _retry_akshare(ak.stock_zh_index_spot_em)
        logger.info("fetch_style_index_realtime: got df with %d rows" % len(df))
        result = []
        for name, code in STYLE_INDEX_NAMES.items():
            match = df[df["代码"] == code]
            if not match.empty:
                row = match.iloc[0]
                result.append({
                    "name": name,
                    "code": code,
                    "price": float(row.get("最新价", 0) or 0),
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                })
        logger.info("fetch_style_index_realtime: returning %d items" % len(result))
        return result
    except Exception as e:
        logger.warning("获取风格指数实时行情失败: %s" % e)
        return []


def fetch_style_index_kline(days=30):
    """获取风格指数 K 线数据
    注：akshare stock_zh_index_hist_csindex 在 pandas 2.x 上存在兼容问题，
    暂返回空 dict，前端需做降级处理（只显示实时涨跌幅）
    """
    return {}


# -------------------------------------------
# 3. 北向资金
# -------------------------------------------


def fetch_northbound_summary():
    """获取北向资金当日汇总，使用 stock_hsgt_fund_flow_summary_em"""
    if not HAS_AKSHARE:
        return None
    try:
        df = _retry_akshare(ak.stock_hsgt_fund_flow_summary_em)
        nr = df[df["资金方向"] == "北向"]
        if nr.empty:
            return None
        sh = nr[nr["板块"] == "沪股通"]
        sz = nr[nr["板块"] == "深股通"]

        def _v(r, col):
            if r.empty:
                return 0.0
            v = r.iloc[0].get(col, 0)
            try:
                val = float(v or 0)
                return val * 100000000
            except Exception:
                return 0.0

        return {
            "date": str(sh.iloc[0].get("交易日", "")) if not sh.empty else "",
            "north_in_flow": _v(sh, "资金净流入") + _v(sz, "资金净流入"),
            "sh_in_flow": _v(sh, "资金净流入"),
            "sz_in_flow": _v(sz, "资金净流入"),
        }
    except Exception as e:
        logger.error("获取北向资金汇总失败: %s" % e)
        return None


def fetch_northbound_history(days=30):
    """获取北向资金历史流向（stock_hsgt_hist_em）
    使用 当日成交净买额 作为主要流向指标（当日资金流入 近期为 NaN）
    返回值的单位：元（前端会 /1e8 显示为亿）
    """
    if not HAS_AKSHARE:
        return []
    try:
        df = _retry_akshare(ak.stock_hsgt_hist_em)
        if df.empty:
            return []
        df = df.tail(days)
        result = []
        for _, row in df.iterrows():
            flow = row.get("当日资金流入")
            try:
                flow_val = float(flow) if flow is not None else None
                if flow_val is None or flow_val != flow_val:
                    flow_val = float(row.get("当日成交净买额", 0) or 0)
            except Exception:
                flow_val = 0.0
            flow_yuan = flow_val * 100000000 if flow_val else 0.0
            trade_net = float(row.get("当日成交净买额", 0) or 0) * 100000000
            result.append({
                "date": str(row.get("日期", "")),
                "north_in_flow": flow_yuan,
                "trade_net": trade_net,
                "hs300": float(row.get("沪深300", 0) or 0),
                "hs300_pct": float(row.get("沪深300-涨跌幅", 0) or 0),
            })
        return result
    except Exception as e:
        logger.error("获取北向资金历史失败: %s" % e)
        return []


def fetch_northbound_streak(days=30):
    """计算北向资金连续流入/流出天数"""
    history = fetch_northbound_history(days)
    if not history:
        return {"streak_type": "unknown", "streak_days": 0, "recent_flows": []}
    streak_type = None
    streak_days = 0
    recent = []
    for item in reversed(history):
        flow = item.get("north_in_flow", 0)
        if flow is None:
            break
        if streak_type is None:
            streak_type = "in" if flow > 0 else ("out" if flow < 0 else "flat")
            streak_days = 1
        else:
            cur_type = "in" if flow > 0 else ("out" if flow < 0 else "flat")
            if cur_type == streak_type and cur_type != "flat":
                streak_days += 1
            else:
                break
        recent.append({"date": item["date"], "flow": flow})
    return {
        "streak_type": streak_type or "unknown",
        "streak_days": streak_days,
        "recent_flows": recent,
    }
