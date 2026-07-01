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


def detect_trend(closes: List[float], klines: List[Dict] = None) -> Optional[Dict]:
    """基于均线排列法判断趋势状态（五分法），并可选计算 ADX 强度

    判定规则（从强到弱）：
    - strong_bull（强多头）：MA5 > MA10 > MA20 > MA60 完整多头排列
    - weak_bull（弱多头）：价格 > MA20，但均线未完全多头排列
    - sideways（震荡）：均线交织，价格在 MA20 附近
    - weak_bear（弱空头）：价格 < MA20，但均线未完全空头排列
    - strong_bear（强空头）：MA5 < MA10 < MA20 < MA60 完整空头排列

    Args:
        closes: 收盘价列表（升序，至少 60 条）
        klines: 完整 K 线数据（含 high/low/close），提供时计算 ADX

    Returns:
        {
            'trend': 'strong_bull' | 'weak_bull' | 'sideways' | 'weak_bear' | 'strong_bear',
            'ma5': float, 'ma10': float, 'ma20': float, 'ma60': float,
            'price': float,
            'adx': float, 'plus_di': float, 'minus_di': float  # klines 提供时
        }
    """
    if len(closes) < 60:
        # 不足 60 日时退化：仅用 MA5/10/20 判断
        if len(closes) < 30:
            # 不足 30 日但 >= 10 日：仅用 MA5/10 判断短期趋势
            if len(closes) < 10:
                return None
            ma5 = calculate_ma(closes, 5)[-1]
            ma10 = calculate_ma(closes, 10)[-1]
            ma20 = None
            ma60 = None
            if ma5 is None or ma10 is None:
                return None
            price = closes[-1]
            # 短期趋势判断（无 MA20/MA60）
            if ma5 > ma10 and price > ma5:
                trend = 'weak_bull'
            elif ma5 < ma10 and price < ma5:
                trend = 'weak_bear'
            else:
                trend = 'sideways'
            result = {
                'trend': trend,
                'ma5': round(ma5, 2),
                'ma10': round(ma10, 2),
                'price': round(price, 2)
            }
            if klines:
                adx_data = calculate_adx(klines)
                if adx_data:
                    result.update(adx_data)
            return result
        ma5 = calculate_ma(closes, 5)[-1]
        ma10 = calculate_ma(closes, 10)[-1]
        ma20 = calculate_ma(closes, 20)[-1]
        ma60 = None
    else:
        ma5 = calculate_ma(closes, 5)[-1]
        ma10 = calculate_ma(closes, 10)[-1]
        ma20 = calculate_ma(closes, 20)[-1]
        ma60 = calculate_ma(closes, 60)[-1]

    if ma5 is None or ma10 is None or ma20 is None:
        return None

    price = closes[-1]

    # 完整多头排列：MA5 > MA10 > MA20 > MA60
    if ma5 > ma10 > ma20 and (ma60 is None or ma20 > ma60):
        trend = 'strong_bull'
    # 完整空头排列：MA5 < MA10 < MA20 < MA60
    elif ma5 < ma10 < ma20 and (ma60 is None or ma20 < ma60):
        trend = 'strong_bear'
    # 弱多头：价格 > MA20，但未形成完整多头排列
    elif price > ma20 and ma5 > ma10:
        trend = 'weak_bull'
    # 弱空头：价格 < MA20，但未形成完整空头排列
    elif price < ma20 and ma5 < ma10:
        trend = 'weak_bear'
    else:
        trend = 'sideways'

    result = {
        'trend': trend,
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'price': round(price, 2)
    }
    if ma60 is not None:
        result['ma60'] = round(ma60, 2)
    if klines:
        adx_data = calculate_adx(klines)
        if adx_data:
            result.update(adx_data)
    return result


def calculate_adx(klines: List[Dict], period: int = 14) -> Optional[Dict]:
    """计算 ADX 趋势强度指标（Wilder 平滑法）

    ADX 衡量趋势强度（不区分方向）：
    - ADX < 20：无趋势（震荡市，金叉信号可靠性低）
    - ADX 20-25：趋势形成中
    - ADX >= 25：强趋势（金叉信号可信度高）
    - ADX > 50：极强趋势（可能趋缓）

    Args:
        klines: K 线数据列表（升序），每条需含 high/low/close
        period: 计算周期，默认 14

    Returns:
        {'adx': float, 'plus_di': float, 'minus_di': float} or None
    """
    if len(klines) < period * 2 + 1:
        return None

    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    closes = [k['close'] for k in klines]

    # 计算 TR, +DM, -DM
    tr_list, plus_dm_list, minus_dm_list = [], [], []
    for i in range(1, len(klines)):
        h, l = highs[i], lows[i]
        h_prev, l_prev = highs[i - 1], lows[i - 1]
        c_prev = closes[i - 1]

        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        up_move = h - h_prev
        down_move = l_prev - l

        plus_dm = up_move if (up_move > down_move and up_move > 0) else 0
        minus_dm = down_move if (down_move > up_move and down_move > 0) else 0

        tr_list.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    # Wilder 平滑（返回 average 级别，确保 ADX 在 0-100 范围）
    def _wilder_smooth(values: List[float]) -> List[float]:
        result = [sum(values[:period]) / period]
        for i in range(period, len(values)):
            result.append(result[-1] * (period - 1) / period + values[i] / period)
        return result

    tr_smooth = _wilder_smooth(tr_list)
    plus_dm_smooth = _wilder_smooth(plus_dm_list)
    minus_dm_smooth = _wilder_smooth(minus_dm_list)

    # +DI, -DI
    plus_di = [100 * plus_dm_smooth[i] / tr_smooth[i] if tr_smooth[i] > 0 else 0
               for i in range(len(tr_smooth))]
    minus_di = [100 * minus_dm_smooth[i] / tr_smooth[i] if tr_smooth[i] > 0 else 0
                for i in range(len(tr_smooth))]

    # DX
    dx_list = []
    for i in range(len(plus_di)):
        di_sum = plus_di[i] + minus_di[i]
        dx = 100 * abs(plus_di[i] - minus_di[i]) / di_sum if di_sum > 0 else 0
        dx_list.append(dx)

    # ADX = Wilder 平滑 DX
    if len(dx_list) < period:
        return None
    adx_smooth = _wilder_smooth(dx_list)

    return {
        'adx': round(adx_smooth[-1], 2),
        'plus_di': round(plus_di[-1], 2),
        'minus_di': round(minus_di[-1], 2)
    }


# 趋势强度排序映射（用于前端排序）
TREND_RANK = {
    'strong_bull': 5,
    'weak_bull': 4,
    'sideways': 3,
    'weak_bear': 2,
    'strong_bear': 1
}


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
    """重新计算所有指数的金叉信号和趋势状态并缓存到内存

    由定时任务在数据拉取后调用：
    - _fetch_index_data 完成后（每 30 分钟）
    - _fetch_index_kline_data 完成后（每日 16:30 / 18:00）
    - 服务启动时预热

    计算范围：市场指数 + 申万行业指数（不含概念板块，概念板块 K 线按需拉取）

    缓存结构：
    - 有金叉信号或趋势信号的指数：{code: {crossover字段..., 'trend': {...}}}
    - 趋势始终计算（只要有足够K线），金叉信号可能为 None

    Args:
        dao: IndexDAO 实例
        logger: 日志记录器

    Returns:
        缓存的指数数量（有金叉信号或趋势数据的指数数）
    """
    global _cache_last_updated
    try:
        market_indices = dao.get_market_indices(limit=50)
        industry_indices = dao.get_industry_indices(limit=500)
        # 去重：market 和 industry 可能有重复 code（如概念板块同时出现在两个分类中）
        seen_codes = set()
        all_indices = []
        for idx in list(market_indices) + list(industry_indices):
            if idx.code not in seen_codes:
                seen_codes.add(idx.code)
                all_indices.append(idx)

        new_cache: Dict[str, Dict] = {}
        trend_count = 0
        for idx in all_indices:
            code = idx.code
            # 根据 code 判断 K 线数据源
            if code.startswith('80') and len(code) == 6:
                kline_source = 'sw'
            elif code.isdigit() and len(code) == 6:
                kline_source = 'sina'
            else:
                # 概念板块（中文 code）：K 线由同花顺源拉取并缓存
                kline_source = 'ths'

            klines = dao.get_klines(code, days=60, source=kline_source)
            closes = None
            # klines_available 标记是否有完整 K 线（含 high/low，可用于 ADX 计算）
            klines_available = False
            if klines and len(klines) >= 10:
                closes = [k['close'] for k in klines]
                klines_available = True
            else:
                # K 线缓存不足，回退到 index_data 表历史快照（仅有 price，无 high/low）
                history = dao.get_index_by_code(code, limit=60)
                if history and len(history) >= 10:
                    # index_data 按 fetched_at 降序，需反转为升序
                    history = list(reversed(history))
                    closes = [h.price for h in history]

            if closes and len(closes) >= 10:
                crossover = detect_crossover(closes)
                trend = detect_trend(closes, klines=klines if klines_available else None)

                # 有金叉信号或趋势数据任一非空则缓存
                if crossover is not None or trend is not None:
                    entry = crossover if crossover is not None else {}
                    if trend is not None:
                        entry['trend'] = trend
                        trend_count += 1
                    new_cache[code] = entry

        with _cache_lock:
            _crossover_cache.clear()
            _crossover_cache.update(new_cache)
            _cache_last_updated = datetime.now()

        if logger:
            logger.info(
                f"✅ 金叉信号+趋势内存缓存已刷新: {len(new_cache)} 个指数有数据 "
                f"(其中 {trend_count} 个有趋势, 共扫描 {len(all_indices)} 个指数)"
            )
        return len(new_cache)
    except Exception as e:
        if logger:
            logger.error(f"❌ 刷新金叉信号缓存失败: {e}")
        return 0
