"""统一符号模型 - 借鉴 stock-sdk normalizeSymbol 设计

将散落在 server.py / index.py / crossover.py 三处的符号判断逻辑收敛到单一入口。

设计要点:
1. Exchange(交易所) 与 DataSource(数据源) 分离,职责清晰
2. normalize_symbol() 单一入口,按优先级链解析
3. to_kline_source() 根据 asset_type 决定 K 线数据源
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AssetType(Enum):
    """资产类型"""
    MARKET_INDEX = 'market_index'       # 市场指数(000001/399001 等)
    INDUSTRY_INDEX = 'industry_index'   # 申万行业指数(80 开头)
    CONCEPT_BOARD = 'concept_board'     # 概念板块(中文名)
    STOCK = 'stock'                      # 个股(预留)


class Exchange(Enum):
    """交易所(真正的交易场所)"""
    SSE = 'SSE'    # 上交所
    SZSE = 'SZSE'  # 深交所
    BSE = 'BSE'    # 北交所
    SW = 'SW'      # 申万指数体系(非传统交易所,但指数归属明确)


class DataSource(Enum):
    """K 线数据源(可跨交易所)"""
    SINA = 'sina'        # 新浪/腾讯
    AKSHARE = 'akshare'  # AKShare 通用
    SW = 'sw'            # 申万指数专用接口
    THS = 'ths'          # 同花顺


@dataclass
class NormalizedSymbol:
    """规范化后的符号表示(系统内部唯一标识)"""
    code: str                              # 纯代码(无前缀)
    asset_type: AssetType                  # 资产类型
    exchange: Optional[Exchange]           # 交易所(概念板块为 None)
    raw_input: str                         # 原始输入(便于调试与日志)
    sina_symbol: Optional[str] = None      # 新浪/腾讯格式(sh600519)


def normalize_symbol(code: str) -> NormalizedSymbol:
    """
    统一符号解析 - 单一入口

    解析规则(命中即停):
    1. 带 sh/sz/bj 前缀 → 解析交易所,推断为市场指数或股票
    2. 带 .SH/.SZ/.BJ 后缀 → 转换为前缀形式后递归解析
    3. 申万行业指数:80 开头 6 位纯数字
    4. 市场指数:6 位纯数字(000001/399001 等)
    5. 概念板块:非纯数字(中文名)

    Args:
        code: 原始代码,支持 sh600519 / 600519.SH / 801766 / CPO概念 等格式

    Returns:
        NormalizedSymbol 规范化符号

    Raises:
        ValueError: 代码为空或无法解析
    """
    if not code or not code.strip():
        raise ValueError('符号代码不能为空')

    raw = code
    code = code.strip()

    # 规则1:带 sh/sz/bj 前缀
    lower = code.lower()
    if lower.startswith(('sh', 'sz', 'bj')):
        prefix = lower[:2]
        pure_code = code[2:]
        exchange = {'sh': Exchange.SSE, 'sz': Exchange.SZSE, 'bj': Exchange.BSE}.get(prefix)
        return NormalizedSymbol(
            code=pure_code,
            asset_type=AssetType.MARKET_INDEX,
            exchange=exchange,
            raw_input=raw,
            sina_symbol=f"{prefix}{pure_code}",
        )

    # 规则2:带 .SH/.SZ/.BJ 后缀
    if '.' in code and not code.replace('.', '').isdigit():
        parts = code.split('.', 1)
        if len(parts) == 2 and parts[1].upper() in ('SH', 'SZ', 'BJ'):
            return normalize_symbol(f"{parts[1].lower()}{parts[0]}")

    # 规则3:申万行业指数(80 开头 6 位纯数字)
    if code.startswith('80') and len(code) == 6 and code.isdigit():
        return NormalizedSymbol(
            code=code,
            asset_type=AssetType.INDUSTRY_INDEX,
            exchange=Exchange.SW,
            raw_input=raw,
        )

    # 规则4:市场指数(6 位纯数字)
    if code.isdigit() and len(code) == 6:
        # 0/3 开头 → 深交所;5/6/9 开头 → 上交所
        if code.startswith(('0', '3')):
            exchange = Exchange.SZSE
            sina_symbol = f"sz{code}"
        else:
            exchange = Exchange.SSE
            sina_symbol = f"sh{code}"
        return NormalizedSymbol(
            code=code,
            asset_type=AssetType.MARKET_INDEX,
            exchange=exchange,
            raw_input=raw,
            sina_symbol=sina_symbol,
        )

    # 规则5:概念板块(中文名/非纯数字)
    return NormalizedSymbol(
        code=code,
        asset_type=AssetType.CONCEPT_BOARD,
        exchange=None,
        raw_input=raw,
    )


def to_kline_source(sym: NormalizedSymbol) -> str:
    """
    根据规范化符号决定 K 线数据源

    Args:
        sym: normalize_symbol 返回的规范化符号

    Returns:
        数据源标识字符串: 'sw' / 'sina' / 'ths'
    """
    if sym.asset_type == AssetType.INDUSTRY_INDEX:
        return DataSource.SW.value
    elif sym.asset_type == AssetType.MARKET_INDEX:
        return DataSource.SINA.value
    else:
        return DataSource.THS.value
