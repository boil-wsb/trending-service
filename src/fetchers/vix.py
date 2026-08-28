"""
VIX / VXN 波动率指数 Fetcher — 恐慌指数
数据源：Yahoo Finance（^VIX 标普500波动率、^VXN 纳斯达克100波动率）
说明：AKShare 无 VIX/VXN 接口，Yahoo 是唯一免费直连源；网络间歇失败需重试。
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("index_vix")

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval=1d"
_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def _fetch_yahoo(symbol: str, range_: str = '1y', retries: int = 3) -> List[tuple]:
    """从 Yahoo Finance 拉取单指数日频序列（容错重试）

    Args:
        symbol: 证券代码，如 '^VIX' / '^VXN'
        range_: 时间范围，如 '1y'
        retries: 失败重试次数

    Returns:
        [(timestamp, close), ...]，已过滤 None 收盘价
    """
    url = _YAHOO_URL.format(symbol=symbol, range_=range_)
    for attempt in range(1, retries + 1):
        try:
            if HAS_REQUESTS:
                r = requests.get(url, headers=_HEADERS, timeout=15)
                r.raise_for_status()
                data = r.json()
            else:
                import json
                import urllib.request
                req = urllib.request.Request(url, headers=_HEADERS)
                data = json.loads(urllib.request.urlopen(req, timeout=15).read())
            ch = data['chart']['result'][0]
            ts = ch['timestamp']
            q = ch['indicators']['quote'][0]['close']
            pts = [(t, v) for t, v in zip(ts, q) if v is not None]
            logger.info(f"Yahoo {symbol} 拉取成功 points={len(pts)} attempt={attempt}")
            return pts
        except Exception as e:
            logger.warning(f"Yahoo {symbol} 第{attempt}次拉取失败 err={str(e)[:80]}")
    return []


def _pts_to_map(pts: List[tuple]) -> Dict[str, Optional[float]]:
    """时间戳序列 -> {日期: 收盘} 映射（Yahoo 时间为 UTC）"""
    m = {}
    for t, v in pts:
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime('%Y-%m-%d')
        m[d] = round(v, 2)
    return m


def fetch_vix_vxn_history(days: int = 365, max_rounds: int = 4) -> List[Dict]:
    """拉取近 N 日 VIX/VXN 日频数据（两指数按日期对齐合并）

    Yahoo 对 ^VIX / ^VXN 是独立请求且间歇性失败（网络波动），
    采用交替重试：每轮分别尝试两个符号，直到两者都有数据或达到轮次上限。

    Args:
        days: 返回天数上限（默认近一年）
        max_rounds: 交替重试轮次上限（每轮每个符号内部再重试 3 次）

    Returns:
        [{'date': '2026-08-27', 'vix': 14.51, 'vxn': 22.30}, ...]（升序）
        某日单指数缺失时对应字段为 None。
    """
    vix_map: Dict[str, Optional[float]] = {}
    vxn_map: Dict[str, Optional[float]] = {}
    for _ in range(max_rounds):
        if not vix_map:
            vix_map = _pts_to_map(_fetch_yahoo('^VIX', '1y'))
        if not vxn_map:
            vxn_map = _pts_to_map(_fetch_yahoo('^VXN', '1y'))
        if vix_map and vxn_map:
            break
    if not vix_map and not vxn_map:
        return []
    dates = sorted(set(vix_map) | set(vxn_map))
    records = [
        {'date': d, 'vix': vix_map.get(d), 'vxn': vxn_map.get(d)}
        for d in dates[-days:]
    ]
    logger.info(f"VIX/VXN 历史拉取完成 total={len(records)} vix_days={len(vix_map)} vxn_days={len(vxn_map)}")
    return records


def backfill_vix_vxn(days: int = 365, db_path=None, logger_=None) -> dict:
    """拉取并保存近 N 日 VIX/VXN 到数据库

    Args:
        days: 天数（默认近一年）
        db_path: 数据库路径；为 None 则不落库（仅拉取）

    Returns:
        {'total': 拉取条数, 'saved': 落库条数}
    """
    log = logger_ or logger
    records = fetch_vix_vxn_history(days)
    saved = 0
    if records and db_path:
        try:
            from src.db.index_dao import IndexDAO
            dao = IndexDAO(db_path)
            saved = dao.save_vix_vxn(records)
        except Exception as e:
            log.warning(f"保存 VIX/VXN 到数据库失败: {e}")
    log.info(f"VIX/VXN backfill 完成 total={len(records)} saved={saved}")
    return {'total': len(records), 'saved': saved}
