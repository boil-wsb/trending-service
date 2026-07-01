"""金叉/死叉检测工具

基于 K 线收盘价数据计算 MACD 和 MA 技术指标，检测金叉状态。

金叉类型：
- MACD 金叉：DIF 上穿 DEA
- MA 金叉：MA5 上穿 MA10

状态分类：
- 'golden'：最新数据已形成金叉
- 'near_golden'：即将金叉（差距 < 价格 1% 且短期线在上行）
- None：无信号
"""

from typing import List, Dict, Optional
import threading
from datetime import datetime


def calculate_ema(data: List[float], period: int) -> List[float]:
    """计算指数移动平均线（EMA）"""
    if not data:
        return []
    result = []
    k = 2 / (period + 1)
    ema = data[0]
    for i, val in enumerate(data):
        if i == 0:
            ema = val
        else:
            ema = val * k + ema * (1 - k)
        result.append(ema)
    return result


def calculate_ma(data: List[float], period: int) -> List[Optional[float]]:
    """计算简单移动平均线（MA），不足 period 时返回 None"""
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(None)
        else:
            total = sum(data[i - period + 1: i + 1])
            result.append(total / period)
    return result


def calculate_macd(closes: List[float]) -> Dict:
    """计算 MACD 指标

    Returns:
        {'dif': [...], 'dea': [...], 'macd': [...]}
    """
    if len(closes) < 26:
        return {'dif': [], 'dea': [], 'macd': []}
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    dea = calculate_ema(dif, 9)
    macd = [(dif[i] - dea[i]) * 2 for i in range(len(closes))]
    return {'dif': dif, 'dea': dea, 'macd': macd}


def detect_crossover(closes: List[float]) -> Optional[Dict]:
    """检测当前金叉状态

    判定规则：
    - MACD 金叉：最后一天 DIF > DEA 且前一天 DIF <= DEA
    - MACD 即将金叉：DIF < DEA 但 |DIF-DEA| < price*1%，且 DIF 连续 2 日上行
    - MA 金叉：最后一天 MA5 > MA10 且前一天 MA5 <= MA10
    - MA 即将金叉：MA5 < MA10 但 |MA5-MA10| < price*1%，且 MA5 连续 2 日上行

    Args:
        closes: 收盘价列表（升序，至少 30 条）

    Returns:
        {
            'macd': 'golden' | 'near_golden' | None,
            'ma': 'golden' | 'near_golden' | None,
            'macd_detail': {'dif': float, 'dea': float, 'gap': float},
            'ma_detail': {'ma5': float, 'ma10': float, 'gap': float}
        }
    """
    if len(closes) < 30:
        return None

    price = closes[-1]
    if price <= 0:
        return None

    threshold = price * 0.01  # 1% 阈值

    result = {
        'macd': None,
        'ma': None,
        'macd_detail': {},
        'ma_detail': {}
    }

    # === MACD 检测 ===
    macd_data = calculate_macd(closes)
    if len(macd_data['dif']) >= 2:
        dif = macd_data['dif']
        dea = macd_data['dea']

        dif_today = dif[-1]
        dea_today = dea[-1]
        dif_yesterday = dif[-2]
        dea_yesterday = dea[-2]
        macd_gap = abs(dif_today - dea_today)

        result['macd_detail'] = {
            'dif': round(dif_today, 4),
            'dea': round(dea_today, 4),
            'gap': round(macd_gap, 4)
        }

        # 金叉：今天 DIF > DEA 且昨天 DIF <= DEA
        if dif_today > dea_today and dif_yesterday <= dea_yesterday:
            result['macd'] = 'golden'
        # 即将金叉：DIF < DEA 但差距 < 1%，且 DIF 连续 2 日上行
        elif dif_today < dea_today and macd_gap < threshold:
            if len(dif) >= 3 and dif[-1] > dif[-2] > dif[-3]:
                result['macd'] = 'near_golden'

    # === MA 检测 ===
    ma5_list = calculate_ma(closes, 5)
    ma10_list = calculate_ma(closes, 10)

    if ma5_list[-1] is not None and ma10_list[-1] is not None and \
       ma5_list[-2] is not None and ma10_list[-2] is not None:
        ma5_today = ma5_list[-1]
        ma10_today = ma10_list[-1]
        ma5_yesterday = ma5_list[-2]
        ma10_yesterday = ma10_list[-2]
        ma_gap = abs(ma5_today - ma10_today)

        result['ma_detail'] = {
            'ma5': round(ma5_today, 2),
            'ma10': round(ma10_today, 2),
            'gap': round(ma_gap, 2)
        }

        # 金叉：今天 MA5 > MA10 且昨天 MA5 <= MA10
        if ma5_today > ma10_today and ma5_yesterday <= ma10_yesterday:
            result['ma'] = 'golden'
        # 即将金叉：MA5 < MA10 但差距 < 1%，且 MA5 连续 2 日上行
        elif ma5_today < ma10_today and ma_gap < threshold:
            if len(ma5_list) >= 3 and ma5_list[-1] is not None and \
               ma5_list[-2] is not None and ma5_list[-3] is not None and \
               ma5_list[-1] > ma5_list[-2] > ma5_list[-3]:
                result['ma'] = 'near_golden'

    # 如果没有任何信号，返回 None
    if result['macd'] is None and result['ma'] is None:
        return None

    return result


def detect_crossover_history(closes: List[float], dates: List[str]) -> List[Dict]:
    """检测所有历史金叉点

    遍历整个 K 线序列，找出所有 MACD 和 MA 金叉发生的日期。

    Args:
        closes: 收盘价列表（升序）
        dates: 对应的日期列表（升序）

    Returns:
        [{'date': '2026-06-20', 'type': 'macd', 'price': 3200.5}, ...]
    """
    if len(closes) < 30 or len(closes) != len(dates):
        return []

    points = []

    # MACD 历史金叉
    macd_data = calculate_macd(closes)
    dif = macd_data['dif']
    dea = macd_data['dea']
    for i in range(1, len(dif)):
        if dif[i] > dea[i] and dif[i - 1] <= dea[i - 1]:
            points.append({
                'date': dates[i],
                'type': 'macd',
                'price': round(closes[i], 2)
            })

    # MA 历史金叉
    ma5_list = calculate_ma(closes, 5)
    ma10_list = calculate_ma(closes, 10)
    for i in range(1, len(ma5_list)):
        if ma5_list[i] is not None and ma10_list[i] is not None and \
           ma5_list[i - 1] is not None and ma10_list[i - 1] is not None:
            if ma5_list[i] > ma10_list[i] and ma5_list[i - 1] <= ma10_list[i - 1]:
                points.append({
                    'date': dates[i],
                    'type': 'ma',
                    'price': round(closes[i], 2)
                })

    return points


# ========== 内存缓存机制（后台预计算，API 直接读取） ==========

# 模块级内存缓存：{code: crossover_result}
_crossover_cache: Dict = {}
_cache_lock = threading.Lock()
_cache_last_updated: Optional[datetime] = None


def get_cached_crossover(code: str) -> Optional[Dict]:
    """从内存缓存读取指数的金叉信号（供 API 调用，O(1) 复杂度）

    缓存由定时任务 refresh_all_crossovers 维护，服务启动时预热。
    """
    with _cache_lock:
        return _crossover_cache.get(code)


def get_cache_last_updated() -> Optional[datetime]:
    """获取缓存最后更新时间"""
    with _cache_lock:
        return _cache_last_updated


def refresh_all_crossovers(dao, logger=None) -> int:
    """重新计算所有指数的金叉信号并缓存到内存

    由定时任务在数据拉取后调用：
    - _fetch_index_data 完成后（每 30 分钟）
    - _fetch_index_kline_data 完成后（每日 16:30 / 18:00）
    - 服务启动时预热

    计算范围：市场指数 + 申万行业指数（不含概念板块，概念板块 K 线按需拉取）

    Args:
        dao: IndexDAO 实例
        logger: 日志记录器

    Returns:
        缓存的指数数量（有信号的指数数）
    """
    global _cache_last_updated
    try:
        market_indices = dao.get_market_indices(limit=50)
        industry_indices = dao.get_industry_indices(limit=500)
        all_indices = list(market_indices) + list(industry_indices)

        new_cache: Dict[str, Dict] = {}
        for idx in all_indices:
            code = idx.code
            # 根据 code 判断 K 线数据源
            if code.startswith('80') and len(code) == 6:
                kline_source = 'sw'
            elif code.isdigit() and len(code) == 6:
                kline_source = 'sina'
            else:
                kline_source = 'em'

            klines = dao.get_klines(code, days=60, source=kline_source)
            if klines and len(klines) >= 30:
                closes = [k['close'] for k in klines]
                crossover = detect_crossover(closes)
                if crossover is not None:
                    new_cache[code] = crossover

        with _cache_lock:
            _crossover_cache.clear()
            _crossover_cache.update(new_cache)
            _cache_last_updated = datetime.now()

        if logger:
            logger.info(
                f"✅ 金叉信号内存缓存已刷新: {len(new_cache)} 个指数有信号 "
                f"(共扫描 {len(all_indices)} 个指数)"
            )
        return len(new_cache)
    except Exception as e:
        if logger:
            logger.error(f"❌ 刷新金叉信号缓存失败: {e}")
        return 0
