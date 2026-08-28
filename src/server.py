"""
HTTP服务器模块
使用 Flask 框架提供 Web 服务
"""

import sys
import threading
import time
import json
import hashlib
from collections import deque
from datetime import datetime
from pathlib import Path
from functools import wraps

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, send_from_directory, redirect, Response, request, g
from src.config import SERVER, REPORTS_DIR, ROUTES, DATABASE, ConfigHotReloader
from src.utils import get_logger
from src.utils.symbol import normalize_symbol, to_kline_source
from src.utils.api_error import ApiError, ErrorCode, handle_api_error, api_success


class TTLCache:
    """简单的 TTL 内存缓存（线程安全）"""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry['expire_at']:
                del self._store[key]
                return None
            return entry['value']

    def set(self, key, value, ttl):
        with self._lock:
            self._store[key] = {
                'value': value,
                'expire_at': time.time() + ttl
            }

    def clear(self):
        with self._lock:
            self._store.clear()

    def clear_prefix(self, prefix):
        """清除指定前缀的缓存"""
        with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]


# 全局缓存实例
_api_cache = TTLCache()

# 全局 API 响应时间记录器（线程安全，保留最近 1000 条）
# 每条记录: {endpoint, method, duration_ms, timestamp}
_MAX_RESPONSE_RECORDS = 1000
_response_times = deque(maxlen=_MAX_RESPONSE_RECORDS)
_response_times_lock = threading.Lock()


# 缓存回源锁（防止 dogpile effect）
_cache_locks = {}
_cache_locks_lock = threading.Lock()


def _get_cache_lock(key):
    """获取指定缓存 key 的回源锁"""
    with _cache_locks_lock:
        if key not in _cache_locks:
            _cache_locks[key] = threading.Lock()
        return _cache_locks[key]


class TrendingServer:
    """Trending Service HTTP 服务器 (Flask)"""

    def __init__(self, host: str = None, port: int = None, logger=None):
        self.host = host or SERVER['host']
        self.port = port or SERVER['port']
        self.logger = logger or get_logger('server')
        self.app = self._create_app()
        self.server_thread = None
        self.running = False
        self.config_watcher = ConfigHotReloader(interval=2.0)

        # 启动时预热金叉信号内存缓存（后台预计算，避免影响 API 响应时间）
        try:
            from src.utils.crossover import refresh_all_crossovers
            from src.db.index_dao import IndexDAO
            dao = IndexDAO(DATABASE['path'])
            refresh_all_crossovers(dao, logger=self.logger)
        except Exception as e:
            self.logger.warning(f"启动时预热金叉缓存失败: {e}")

    def _create_app(self) -> Flask:
        """创建 Flask 应用"""
        app = Flask(__name__, 
                    static_folder=str(project_root / 'static'),
                    template_folder=str(project_root / 'templates'))
        
        # 配置日志
        app.logger.handlers = []
        for handler in self.logger.handlers:
            app.logger.addHandler(handler)
        app.logger.setLevel(self.logger.level)

        # 注册路由
        self._register_routes(app)
        
        return app

    def _register_routes(self, app: Flask):
        """注册路由"""

        # ========== 性能监控中间件 ==========

        @app.before_request
        def _record_start_time():
            """记录请求开始时间"""
            g.start_time = time.time()

        @app.after_request
        def _record_response_time(response):
            """记录响应时间并写入结构化日志"""
            try:
                start = getattr(g, 'start_time', None)
                if start is None:
                    return response

                duration_ms = round((time.time() - start) * 1000, 2)
                endpoint = request.path
                method = request.method

                # /api/metrics 自身不计入统计，避免自引用
                if endpoint != '/api/metrics':
                    record = {
                        'endpoint': endpoint,
                        'method': method,
                        'duration_ms': duration_ms,
                        'timestamp': datetime.now().isoformat()
                    }
                    with _response_times_lock:
                        _response_times.append(record)

                # 结构化日志（不含敏感信息如 token）
                self.logger.info(
                    f"module=api_metrics method={method} endpoint={endpoint} "
                    f"status={response.status_code} duration_ms={duration_ms}"
                )
            except Exception as e:
                self.logger.warning(f"记录响应时间失败: {e}")
            return response

        # ========== 指数行情API ==========

        @app.route('/api/index/market')
        def api_index_market():
            """A股市场指数列表（含金叉信号，从内存缓存读取）"""
            try:
                from src.db.index_dao import IndexDAO
                from src.utils.crossover import get_cached_crossover

                dao = IndexDAO(DATABASE['path'])
                indices = dao.get_market_indices(limit=50)

                result = []
                for idx in indices:
                    d = idx.to_dict()
                    # 从内存缓存读取金叉信号（由定时任务后台预计算）
                    d['crossover'] = get_cached_crossover(idx.code)
                    result.append(d)

                # 获取市场总览历史对比数据（vs昨日/近5日均值）
                comparison = dao.get_market_overview_comparison()
                # 获取数据完整性质量指标
                data_quality = dao.get_data_quality()

                return jsonify({
                    'success': True,
                    'data': {
                        'indices': result,
                        'count': len(result),
                        'fetched_at': indices[0].fetched_at.strftime('%Y-%m-%d %H:%M:%S') if indices and indices[0].fetched_at else None,
                        'comparison': comparison,
                        'data_quality': data_quality
                    }
                })
            except Exception as e:
                self.logger.error(f"获取市场指数失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/data-quality')
        def api_index_data_quality():
            """数据完整性质量指标（行业/概念板块字段填充率，60s 缓存）"""
            try:
                from src.db.index_dao import IndexDAO

                # 缓存检查（60s TTL）
                cache_key = "data_quality:all"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                quality = dao.get_data_quality()

                result = jsonify({'success': True, 'data': quality})
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取数据质量指标失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/industry')
        def api_index_industry():
            """申万行业指数列表（含 3日/7日 涨跌幅、金叉信号，60s 缓存）"""
            try:
                from src.db.index_dao import IndexDAO
                from src.utils.crossover import get_cached_crossover, get_cached_drawdown
                from flask import request

                try:
                    limit = min(int(request.args.get('limit', 10000)), 10000)
                except (ValueError, TypeError):
                    limit = 10000

                # 缓存检查（60s TTL）
                cache_key = f"industry:{limit}"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                # 使用带多日涨跌幅的方法（先排序后 limit）
                indices = dao.get_industry_indices_with_changes(limit=limit)

                result_list = []
                for idx in indices:
                    d = idx.to_dict()
                    # 从内存缓存读取金叉信号（由定时任务后台预计算）
                    d['crossover'] = get_cached_crossover(idx.code)
                    # 从内存缓存读取距高点回撤数据
                    d['drawdown'] = get_cached_drawdown(idx.code)
                    result_list.append(d)

                result = jsonify({
                    'success': True,
                    'data': {
                        'indices': result_list,
                        'count': len(result_list),
                        'fetched_at': indices[0].fetched_at.strftime('%Y-%m-%d %H:%M:%S') if indices and indices[0].fetched_at else None
                    }
                })
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取行业指数失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/latest')
        def api_index_latest():
            """最新指数数据（可选 category 参数: market/industry）"""
            try:
                from src.db.index_dao import IndexDAO
                from flask import request

                category = request.args.get('category')
                try:
                    limit = min(int(request.args.get('limit', 50)), 200)
                except (ValueError, TypeError):
                    limit = 50

                dao = IndexDAO(DATABASE['path'])
                indices = dao.get_latest(category=category, limit=limit)

                return jsonify({
                    'success': True,
                    'data': {
                        'indices': [idx.to_dict() for idx in indices],
                        'count': len(indices),
                        'category': category or 'all'
                    }
                })
            except Exception as e:
                self.logger.error(f"获取最新指数数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/detail')
        def api_index_detail():
            """指数历史数据（按代码查询）"""
            try:
                from src.db.index_dao import IndexDAO
                from flask import request

                code = request.args.get('code')
                if not code:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '缺少指数代码参数: code', status_code=400).to_response()), 400

                try:
                    limit = min(int(request.args.get('limit', 30)), 200)
                except (ValueError, TypeError):
                    limit = 30

                dao = IndexDAO(DATABASE['path'])
                indices = dao.get_index_by_code(code, limit=limit)

                if not indices:
                    return jsonify(ApiError(ErrorCode.DATA_NOT_FOUND, f'未找到指数: {code}', status_code=404).to_response()), 404

                return jsonify({
                    'success': True,
                    'data': {
                        'code': code,
                        'name': indices[0].name,
                        'category': indices[0].category,
                        'history': [idx.to_dict() for idx in indices],
                        'count': len(indices)
                    }
                })
            except Exception as e:
                self.logger.error(f"获取指数详情失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/kline')
        def api_index_kline():
            """指数K线数据（优先读数据库缓存，缓存不存在或过期时按指数类型从对应数据源拉取）

            数据源映射：
            - 申万行业指数（code 以 80 开头，6 位数字）：source='sw'
            - 市场指数（code 是 6 位数字）：source='sina'
            - 概念板块（code 是中文名称）：source='ths'
            """
            try:
                from src.fetchers.index import IndexFetcher
                from src.db.index_dao import IndexDAO
                from flask import request
                from datetime import datetime, timedelta

                code = request.args.get('code')
                if not code:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '缺少指数代码参数: code', status_code=400).to_response()), 400

                try:
                    days = min(int(request.args.get('days', 30)), 365)
                except (ValueError, TypeError):
                    days = 30

                # 周期参数：day(日K)/week(周K)/month(月K)，默认 day
                period = request.args.get('period', 'day')
                if period not in ('day', 'week', 'month'):
                    period = 'day'

                # 强制刷新参数：?force=1 跳过缓存直接拉取
                force_refresh = request.args.get('force', '0') == '1'

                # API 内存缓存检查（5min TTL，强制刷新时跳过）
                cache_key = f"kline:{code}:{days}:{period}"
                if not force_refresh:
                    cached = _api_cache.get(cache_key)
                    if cached is not None:
                        return cached

                # 防止缓存击穿（dogpile effect）：同一 cache_key 的并发回源串行化
                lock = _get_cache_lock(cache_key)
                with lock:
                    # 双重检查（可能其他线程已经填充了缓存）；force_refresh 跳过
                    if not force_refresh:
                        cached = _api_cache.get(cache_key)
                        if cached is not None:
                            return cached

                    # 根据指数代码类型确定数据源（统一走 normalize_symbol 解析）
                    sym = normalize_symbol(code)
                    source = to_kline_source(sym)

                    dao = IndexDAO(DATABASE['path'])

                    # 1. 先读数据库缓存（使用对应数据源）
                    if not force_refresh:
                        cached = dao.get_klines(code, days=days, source=source)
                        latest_date = dao.get_kline_latest_date(code, source=source)

                        # 2. 计算预期应该有数据的最近交易日
                        now = datetime.now()
                        today = now.date()
                        weekday = today.weekday()  # 0=Mon, 1=Tue, ..., 5=Sat, 6=Sun

                        def _get_expected_latest_date():
                            """根据当前时间计算应该已有K线数据的最近交易日"""
                            if weekday >= 5:  # 周六或周日
                                # 周末：应该有周五的数据
                                return today - timedelta(days=weekday - 4)
                            elif now.hour < 15:  # 交易日收盘前(15:00前)
                                # 盘中：今天的K线未收盘，应该有前一个交易日的数据
                                if weekday == 0:  # 周一盘中，应该有上周五数据
                                    return today - timedelta(days=3)
                                else:  # 周二~周五盘中，应该有昨天数据
                                    return today - timedelta(days=1)
                            else:  # 交易日收盘后(15:00后)
                                # 收盘后：应该有今天的数据
                                return today

                        expected_latest = _get_expected_latest_date()
                        need_refresh = True
                        if latest_date:
                            try:
                                latest_dt = datetime.strptime(latest_date, '%Y-%m-%d').date()
                                # 如果缓存最新日期 >= 预期日期，说明缓存是最新的，不需要刷新
                                if latest_dt >= expected_latest:
                                    need_refresh = False
                            except ValueError:
                                pass

                        if need_refresh and latest_date:
                            self.logger.debug(
                                f"K线缓存需要刷新: {code}, latest={latest_date}, "
                                f"expected={expected_latest}, today={today}, hour={now.hour}"
                            )

                        # 3. 如果缓存有效，直接返回
                        if cached and not need_refresh:
                            # 按周期聚合日K数据（day 原样返回）
                            kline_data = IndexFetcher.aggregate_kline(cached, period) if period != 'day' else cached
                            # 计算金叉标记点（基于聚合后的数据）
                            from src.utils.crossover import detect_crossover_history
                            closes = [k['close'] for k in kline_data]
                            dates = [k['date'] for k in kline_data]
                            crossover_points = detect_crossover_history(closes, dates)
                            return jsonify({
                                'success': True,
                                'data': {
                                    'code': code,
                                    'kline': kline_data,
                                    'crossover_points': crossover_points,
                                    'count': len(kline_data),
                                    'source': 'cache',
                                    'period': period
                                }
                            })

                    # 4. 缓存不存在或过期或强制刷新，按指数类型从对应数据源拉取
                    fetcher = IndexFetcher(logger=self.logger)
                    kline = fetcher.fetch_kline(code, days=days)

                    # 5. 保存到数据库缓存（始终保存日K原始数据，使用对应数据源标识）
                    if kline:
                        try:
                            dao.save_klines(code, kline, source=source)
                            self.logger.info(f"K线数据已缓存: {code} {len(kline)} 条 (source={source})")
                        except Exception as e:
                            self.logger.warning(f"K线数据缓存失败: {e}")

                    # 6. 按周期聚合日K数据（day 原样返回）
                    kline_data = IndexFetcher.aggregate_kline(kline, period) if period != 'day' else kline

                    # 计算金叉标记点（基于聚合后的数据）
                    from src.utils.crossover import detect_crossover_history
                    closes = [k['close'] for k in kline_data]
                    dates = [k['date'] for k in kline_data]
                    crossover_points = detect_crossover_history(closes, dates)

                    result = jsonify({
                        'success': True,
                        'data': {
                            'code': code,
                            'kline': kline_data,
                            'crossover_points': crossover_points,
                            'count': len(kline_data),
                            'source': source,
                            'period': period
                        }
                    })
                    _api_cache.set(cache_key, result, ttl=300)  # 5min 缓存
                    return result
            except Exception as e:
                self.logger.error(f"获取指数K线失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/rotation')
        def api_index_rotation():
            """行业轮动分析数据（60s 缓存）

            返回行业指数的多周期涨跌幅排名、多因子动量得分（0-100 标准化）、成交额，
            用于前端展示强势/弱势排名表、热力图、轮动趋势。

            多因子动量模型包含 3 类因子：
            - 价格动量（50%）：今日/3日/7日涨跌幅的百分位加权
            - 量价动量（30%）：成交额 5 日变化率 + 换手率的百分位加权
            - 资金动量（20%）：主力净流入额的百分位
            缺失数据用 50（中性）填充，避免惩罚无数据的板块。
            """
            def rank_percentile(values):
                """将原始值列表转为 0-100 百分位

                Args:
                    values: list of (key, value) tuples，value 可为 None
                Returns:
                    dict: key -> percentile(0-100)，None 值映射为 50（中性）
                """
                valid = [(k, v) for k, v in values if v is not None]
                valid.sort(key=lambda x: x[1], reverse=True)
                n = len(valid)
                result = {}
                for k, v in values:
                    if v is None:
                        result[k] = 50.0
                    else:
                        rank = next(i for i, (kk, _) in enumerate(valid) if kk == k)
                        result[k] = round((n - rank) / max(n - 1, 1) * 100, 2)
                return result

            try:
                from src.db.index_dao import IndexDAO

                # 缓存检查（60s TTL）
                cache_key = "rotation:all"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                # 获取全部行业指数（含 3日/7日涨跌幅）
                indices = dao.get_industry_indices_with_changes(limit=10000)
                if not indices:
                    result = jsonify({'success': True, 'data': {'indices': [], 'count': 0, 'alerts': []}})
                    _api_cache.set(cache_key, result, ttl=60)
                    return result

                # 量价动量子因子：5 日均量变化率（来自 index_kline 表）
                avg_amount_data = dao.get_5d_avg_amount([idx.code for idx in indices])

                # 资金动量子因子：主力净流入额（按 name 匹配，失败时用空 dict）
                fund_flow_map = {}
                try:
                    from src.fetchers.fund_flow import fetch_sector_fund_flow
                    ff_data = fetch_sector_fund_flow(indicator='今日')
                    fund_flow_map = {item['name']: item['main_in_flow'] for item in ff_data}
                except Exception as e:
                    self.logger.warning(f"获取 fund-flow 数据失败，资金动量将使用中性值: {e}")

                # 构建 items 列表，收集 6 个子因子原始值
                items = []
                for idx in indices:
                    # amount 单位统一为亿元：
                    #   akshare 源（行业指数）返回万元，需 /10000 转亿元
                    #   ths 源（概念板块资金净额）已是亿元
                    #   em 源（概念板块）已是亿元
                    if idx.amount:
                        amount_val = idx.amount / 10000 if idx.source == 'akshare' else idx.amount
                        amount_val = round(amount_val, 2)
                    else:
                        amount_val = 0
                    # 收集多因子原始值（None 表示无数据，百分位计算时映射为中性 50）
                    raw_today = idx.change_pct
                    raw_3d = idx.change_pct_3d
                    raw_7d = idx.change_pct_7d
                    raw_amount_rate = avg_amount_data.get(idx.code, {}).get('change_rate')
                    raw_turnover = idx.turnover_rate if idx.turnover_rate else None
                    raw_fund = fund_flow_map.get(idx.name)
                    items.append({
                        'code': idx.code,
                        'name': idx.name,
                        'price': round(idx.price, 2),
                        'change_pct': round(idx.change_pct, 2),
                        'change_pct_3d': idx.change_pct_3d,
                        'change_pct_7d': idx.change_pct_7d,
                        'amount': amount_val,
                        'turnover_rate': round(idx.turnover_rate, 2) if idx.turnover_rate else 0,
                        'market_cap': round(idx.market_cap / 100000000, 2) if idx.market_cap else 0,
                        'source': idx.source,
                        '_raw_today': raw_today,
                        '_raw_3d': raw_3d,
                        '_raw_7d': raw_7d,
                        '_raw_amount_rate': raw_amount_rate,
                        '_raw_turnover': raw_turnover,
                        '_raw_fund': raw_fund,
                    })

                # 计算 6 个子因子的百分位（0-100，缺失值=50 中性）
                today_pctile = rank_percentile([(it['code'], it['_raw_today']) for it in items])
                pct_3d_pctile = rank_percentile([(it['code'], it['_raw_3d']) for it in items])
                pct_7d_pctile = rank_percentile([(it['code'], it['_raw_7d']) for it in items])
                amount_pctile = rank_percentile([(it['code'], it['_raw_amount_rate']) for it in items])
                turnover_pctile = rank_percentile([(it['code'], it['_raw_turnover']) for it in items])
                fund_pctile = rank_percentile([(it['code'], it['_raw_fund']) for it in items])

                # 计算总动量得分（0-100）和分项得分
                for it in items:
                    code = it['code']
                    tp = today_pctile[code]
                    d3 = pct_3d_pctile[code]
                    d7 = pct_7d_pctile[code]
                    ap = amount_pctile[code]
                    trp = turnover_pctile[code]
                    fp = fund_pctile[code]
                    price_score = round(tp * 0.20 + d3 * 0.15 + d7 * 0.15, 2)
                    volume_score = round(ap * 0.15 + trp * 0.15, 2)
                    fund_score = round(fp * 0.20, 2)
                    it['momentum'] = round(price_score + volume_score + fund_score, 2)
                    it['momentum_breakdown'] = {
                        'price': price_score,
                        'volume': volume_score,
                        'fund': fund_score,
                        'price_detail': {
                            'today': tp,
                            'd3': d3,
                            'd7': d7,
                        },
                        'volume_detail': {
                            'amount_change_rate': it['_raw_amount_rate'],
                            'amount_pctile': ap,
                            'turnover_pctile': trp,
                        },
                        'fund_detail': {
                            'main_in_flow': it['_raw_fund'],
                            'fund_pctile': fp,
                        }
                    }

                # 删除临时字段，避免泄露到 API 响应
                for it in items:
                    for k in ('_raw_today', '_raw_3d', '_raw_7d',
                              '_raw_amount_rate', '_raw_turnover', '_raw_fund'):
                        it.pop(k, None)

                # 按各周期排名
                for field in ['change_pct', 'change_pct_3d', 'change_pct_7d', 'momentum']:
                    sorted_items = sorted(items, key=lambda x: x.get(field, 0) or 0, reverse=True)
                    for rank, item in enumerate(sorted_items, 1):
                        item[f'rank_{field}'] = rank

                # 按动量得分排序返回
                items.sort(key=lambda x: x['momentum'], reverse=True)

                # 异常轮动检测（4 条规则，按 high > medium > low 排序）
                from src.utils.crossover import get_cached_crossover
                alerts = []
                for item in items:
                    code = item['code']
                    name = item['name']
                    rank_today = item.get('rank_change_pct', 999)
                    rank_7d = item.get('rank_change_pct_7d', 999)
                    change_pct = item.get('change_pct', 0) or 0
                    change_7d = item.get('change_pct_7d', 0) or 0
                    momentum = item.get('momentum', 0) or 0
                    rank_momentum = item.get('rank_momentum', 999)

                    # 规则2: 放量突破（量比 > 2 且涨幅 > 3%）
                    # amount_change_rate 来自 momentum_breakdown.volume_detail
                    breakdown = item.get('momentum_breakdown') or {}
                    vol_detail = breakdown.get('volume_detail') or {}
                    amount_rate = vol_detail.get('amount_change_rate')
                    if amount_rate and amount_rate > 100 and change_pct > 3:
                        amount_ratio = round(amount_rate / 100 + 1, 2)
                        alerts.append({
                            'type': 'volume_breakout',
                            'level': 'high',
                            'code': code, 'name': name,
                            'amount_ratio': amount_ratio,
                            'change_pct': change_pct,
                            'message': f'{name} 放量突破（量比{amount_ratio}，涨{change_pct}%）'
                        })

                    # 规则3: 趋势反转（7日跌 > 5% 但今日涨 > 3%）
                    if change_7d < -5 and change_pct > 3:
                        alerts.append({
                            'type': 'trend_reversal',
                            'level': 'medium',
                            'code': code, 'name': name,
                            'change_7d': change_7d,
                            'change_today': change_pct,
                            'message': f'{name} 趋势反转（7日{change_7d}%，今日+{change_pct}%）'
                        })

                    # 规则4: 金叉确认+动量领跑（MACD/MA金叉 且 动量得分>=70 且 排名TOP20）
                    if rank_momentum and rank_momentum <= 20 and momentum >= 70:
                        cross = get_cached_crossover(code) or {}
                        macd_signal = cross.get('macd')
                        ma_signal = cross.get('ma')
                        golden_type = None
                        if macd_signal == 'golden' and ma_signal == 'golden':
                            golden_type = 'MACD+MA'
                        elif macd_signal == 'golden':
                            golden_type = 'MACD'
                        elif ma_signal == 'golden':
                            golden_type = 'MA'
                        if golden_type:
                            alerts.append({
                                'type': 'golden_cross_momentum',
                                'level': 'medium',
                                'code': code, 'name': name,
                                'momentum': momentum,
                                'rank': rank_momentum,
                                'golden_cross': golden_type,
                                'message': f'{name} {golden_type}金叉+动量领跑（得分{momentum}，排名#{rank_momentum}）'
                            })

                # 按级别排序：high > medium > low
                level_order = {'high': 0, 'medium': 1, 'low': 2}
                alerts.sort(key=lambda a: level_order.get(a['level'], 3))

                result = jsonify({
                    'success': True,
                    'data': {
                        'indices': items,
                        'count': len(items),
                        'top_strong': items[:10],
                        'top_weak': items[-10:][::-1],
                        'alerts': alerts
                    }
                })
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取行业轮动数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/rotation/history')
        def api_index_rotation_history():
            """行业轮动历史排名趋势（5min 缓存）

            查询近 N 日每日板块排名变化，用于前端 bump chart。
            """
            try:
                from src.db.index_dao import IndexDAO

                # 解析 days 参数（默认 30，范围 7-90）
                try:
                    days = int(request.args.get('days', 30))
                except (ValueError, TypeError):
                    days = 30
                days = max(7, min(90, days))

                cache_key = f"rotation:history:{days}"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                history = dao.get_rotation_history(days=days)

                result = jsonify({
                    'success': True,
                    'data': {
                        'dates': history['dates'],
                        'sectors': history['sectors'],
                        'count': len(history['dates'])
                    }
                })
                _api_cache.set(cache_key, result, ttl=300)  # 5min 缓存
                return result
            except Exception as e:
                self.logger.error(f"获取行业轮动历史数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/trigger-fetch', methods=['POST'])
        def api_index_trigger_fetch():
            """手动触发指数数据获取"""
            try:
                from src.fetchers.index import IndexFetcher
                from src.db.index_dao import IndexDAO

                fetcher = IndexFetcher(logger=self.logger)
                count = fetcher.save_to_db(DATABASE['path'])

                # 抓取后数据完整性校验（不影响抓取流程）
                dao = IndexDAO(DATABASE['path'])
                quality = dao.get_data_quality()

                # 兼容旧返回字段：market_cap 填充率
                concept_total = quality.get('concept_total', 0)
                market_cap_rate = round(quality.get('concept_market_cap_filled', 0) * 100, 1)

                self.logger.info(
                    f"手动触发指数数据获取完成: {count} 条, "
                    f"概念板块 market_cap 填充率: {market_cap_rate}%"
                )

                # 任一填充率低于 70% 记录 WARN 日志
                ratios = [
                    quality.get('industry_amount_filled', 0),
                    quality.get('concept_market_cap_filled', 0),
                    quality.get('concept_amount_filled', 0),
                ]
                if quality.get('has_data') and any(r < 0.70 for r in ratios):
                    self.logger.warning(
                        f'module=data_quality '
                        f'industry_amount_filled={quality["industry_amount_filled"]} '
                        f'concept_market_cap_filled={quality["concept_market_cap_filled"]} '
                        f'concept_amount_filled={quality["concept_amount_filled"]} '
                        f'level=WARN msg="数据填充率低于阈值"'
                    )

                return jsonify({
                    'success': True,
                    'data': {
                        'count': count,
                        'market_cap_filled_count': round(quality.get('concept_market_cap_filled', 0) * concept_total),
                        'market_cap_total_count': concept_total,
                        'market_cap_rate': market_cap_rate,
                        'data_quality': quality,
                        'message': f'成功获取 {count} 条指数数据（概念板块总市值填充率 {market_cap_rate}%）'
                    }
                })
            except Exception as e:
                self.logger.error(f"手动触发指数数据获取失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        # ========= 主力资金 / 风格轮动 / 北向资金 API =========

        @app.route('/api/index/fund-flow')
        def api_index_fund_flow():
            """主力资金行业净流入排行（双向条形图数据源）"""
            try:
                from src.fetchers.fund_flow import fetch_sector_fund_flow
                from flask import request

                indicator = request.args.get('indicator', '今日')
                if indicator not in ('今日', '5日', '10日'):
                    indicator = '今日'

                data = fetch_sector_fund_flow(indicator=indicator)
                return jsonify({
                    'success': True,
                    'data': {
                        'indicator': indicator,
                        'items': data,
                        'count': len(data),
                    }
                })
            except Exception as e:
                self.logger.error(f"获取主力资金排行失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/sentiment')
        def api_index_sentiment():
            """市场情绪指标（涨跌停统计，60s 缓存）"""
            try:
                from src.fetchers.sentiment import fetch_limit_up_stats
                from src.db.index_dao import IndexDAO

                cache_key = "sentiment:today"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                # 实时获取今日涨跌停数据
                stats = fetch_limit_up_stats()

                # 保存到数据库（供历史查询）
                if stats['limit_up_count'] > 0 or stats['limit_down_count'] > 0:
                    try:
                        dao = IndexDAO(DATABASE['path'])
                        dao.save_sentiment_stats(stats)
                    except Exception as e:
                        self.logger.warning(f"保存涨跌停统计到数据库失败: {e}")

                # 查询历史数据（近30日）
                try:
                    dao = IndexDAO(DATABASE['path'])
                    history = dao.get_sentiment_history(30)
                except Exception as e:
                    self.logger.warning(f"查询情绪历史数据失败: {e}")
                    history = []

                result = jsonify({
                    'success': True,
                    'data': {
                        'today': stats,
                        'history': history,
                    }
                })
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取市场情绪数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/index/vix-vxn')
        def api_index_vix_vxn():
            """VIX/VXN 波动率指数（近一年，从库读，供情绪板块卡片与折线图）"""
            try:
                from src.db.index_dao import IndexDAO

                dao = IndexDAO(DATABASE['path'])
                history = dao.get_vix_vxn_history(365)
                latest = history[-1] if history else None
                return jsonify({
                    'success': True,
                    'data': {
                        'history': history,
                        'latest': latest,
                        'count': len(history),
                    }
                })
            except Exception as e:
                self.logger.error(f"获取 VIX/VXN 数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/northbound')
        def api_northbound():
            """北向资金每日净流入数据（60s 缓存）"""
            try:
                from src.fetchers.northbound import fetch_northbound_flow
                from src.db.index_dao import IndexDAO

                days = request.args.get('days', '30', type=str)
                try:
                    days = int(days)
                    days = max(7, min(90, days))
                except ValueError:
                    days = 30

                cache_key = f"northbound:{days}"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                data = fetch_northbound_flow(days=days)

                # 保存到数据库
                if data.get('dates'):
                    try:
                        dao = IndexDAO(DATABASE['path'])
                        dao.save_northbound_flow(data)
                    except Exception as e:
                        self.logger.warning(f"保存北向资金数据到数据库失败: {e}")

                result = jsonify({
                    'success': True,
                    'data': data
                })
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取北向资金数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        # ========== 通用API路由 ==========

        @app.route('/')
        def index():
            """首页重定向到报告页面"""
            return redirect(ROUTES['report'])

        @app.route('/report.html')
        def report():
            """报告页面"""
            report_file = REPORTS_DIR / 'report.html'
            
            if not report_file.exists():
                # 返回默认页面
                return self._get_default_html()
            
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                return Response(content, mimetype='text/html; charset=utf-8')
            except Exception as e:
                self.logger.error(f"读取报告文件失败: {e}")
                return f"Error reading report: {e}", 500

        @app.route('/api/<data_type>')
        def api(data_type: str):
            """API 接口"""
            # 安全检查：防止目录遍历
            if '..' in data_type or '/' in data_type:
                return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '无效的数据类型', status_code=400).to_response()), 400

            data_file = REPORTS_DIR / f"{data_type}.json"

            if not data_file.exists():
                return jsonify(ApiError(ErrorCode.DATA_NOT_FOUND, '数据不存在', status_code=404).to_response()), 404

            try:
                import json
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                response = jsonify(data)
                response.headers.add('Access-Control-Allow-Origin', '*')
                return response
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON 解析错误: {e}")
                return jsonify(ApiError(ErrorCode.INTERNAL_ERROR, '数据格式错误', detail=str(e), status_code=500).to_response()), 500
            except Exception as e:
                self.logger.error(f"读取数据失败: {e}")
                return jsonify(ApiError(ErrorCode.INTERNAL_ERROR, '读取数据失败', detail=str(e), status_code=500).to_response()), 500

        @app.route('/api/data')
        def api_data_by_date():
            """按日期获取数据 API
            
            支持参数:
                - date: 单个日期 (YYYY-MM-DD)
                - start_date: 开始日期 (YYYY-MM-DD)
                - end_date: 结束日期 (YYYY-MM-DD)
            """
            from datetime import datetime
            from src.db import TrendingDAO
            from src.config import DATABASE
            
            # 获取日期参数
            date_param = request.args.get('date')
            start_date_param = request.args.get('start_date')
            end_date_param = request.args.get('end_date')
            
            # 验证日期格式并计算日期范围
            if date_param:
                # 单个日期模式
                try:
                    target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
                    start_date = target_date
                    end_date = target_date
                except ValueError:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '日期格式无效,应为 YYYY-MM-DD', status_code=400).to_response()), 400
            elif start_date_param and end_date_param:
                # 日期范围模式
                try:
                    start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
                except ValueError:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '日期格式无效,应为 YYYY-MM-DD', status_code=400).to_response()), 400
                
                # 验证日期范围
                if start_date > end_date:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '开始日期不能晚于结束日期', status_code=400).to_response()), 400
            else:
                return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '缺少必要参数: date 或 start_date/end_date', status_code=400).to_response()), 400
            
            # 检查是否是未来日期
            today = datetime.now().date()
            if end_date > today:
                return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '不能查询未来日期', status_code=400).to_response()), 400
            
            # 构建日期范围字符串
            if start_date == end_date:
                date_range_str = start_date.isoformat()
            else:
                date_range_str = f"{start_date.isoformat()} to {end_date.isoformat()}"
            
            try:
                # 从数据库获取数据
                dao = TrendingDAO(DATABASE['path'])
                
                # 获取指定日期范围的数据
                items = dao.get_items(
                    start_date=start_date,
                    end_date=end_date,
                    limit=10000
                )
                
                # 如果没有数据，返回友好提示
                if not items:
                    return jsonify({
                        'success': True,
                        'data': {
                            'date': date_range_str,
                            'start_date': start_date.isoformat(),
                            'end_date': end_date.isoformat(),
                            'items': [],
                            'sources': {},
                            'total_items': 0,
                            'message': f'No data available for {date_range_str}'
                        }
                    })
                
                # 按数据源分组，并按热度排序
                sources = {}
                for item in items:
                    source = item.source
                    if source not in sources:
                        sources[source] = []
                    sources[source].append({
                        'title': item.title,
                        'url': item.url,
                        'hot_score': item.hot_score,
                        'description': item.description,
                        'author': item.author,
                        'category': item.category,
                        'keywords': item.keywords,
                        'extra': item.extra
                    })
                
                # 对每个数据源的数据按热度排序（降序）
                for source in sources:
                    sources[source].sort(key=lambda x: x.get('hot_score', 0) or 0, reverse=True)
                
                # 构建响应数据
                response_data = {
                    'success': True,
                    'data': {
                        'date': date_range_str,
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'items': [{
                            'title': item.title,
                            'url': item.url,
                            'source': item.source,
                            'hot_score': item.hot_score,
                            'description': item.description,
                            'author': item.author,
                            'category': item.category,
                            'keywords': item.keywords,
                            'extra': item.extra
                        } for item in items],
                        'sources': sources,
                        'total_items': len(items),
                        'sources_count': len(sources),
                        'generated_at': datetime.now().isoformat()
                    }
                }
                
                response = jsonify(response_data)
                response.headers.add('Access-Control-Allow-Origin', '*')
                return response
                
            except Exception as e:
                self.logger.error(f"获取日期数据失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/search')
        def api_search():
            """搜索数据库记录

            支持参数:
                - q: 搜索关键词（搜索 title 和 description）
                - source: 数据源筛选（可选）
                - limit: 返回数量（默认 50，最大 200）
            """
            from src.db import TrendingDAO
            from src.config import DATABASE

            query = request.args.get('q', '').strip()
            source = request.args.get('source')
            try:
                limit = min(int(request.args.get('limit', 50)), 200)
            except (ValueError, TypeError):
                limit = 50

            if not query:
                return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, '缺少搜索关键词参数: q', status_code=400).to_response()), 400

            try:
                dao = TrendingDAO(DATABASE['path'])
                items = dao.get_items(
                    source=source if source and source != 'all' else None,
                    keyword=query,
                    limit=limit
                )

                results = []
                for item in items:
                    results.append({
                        'title': item.title,
                        'url': item.url,
                        'source': item.source,
                        'hot_score': item.hot_score,
                        'description': item.description,
                        'author': item.author,
                        'category': item.category,
                        'keywords': item.keywords,
                        'fetched_at': item.fetched_at.isoformat() if item.fetched_at else None,
                        'extra': item.extra
                    })

                response = jsonify({
                    'success': True,
                    'query': query,
                    'total': len(results),
                    'items': results
                })
                response.headers.add('Access-Control-Allow-Origin', '*')
                return response

            except Exception as e:
                self.logger.error(f"搜索失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/status')
        def api_status():
            """服务状态检查"""
            return jsonify({
                'success': True,
                'status': 'running',
                'timestamp': datetime.now().isoformat(),
                'server': {
                    'host': self.host,
                    'port': self.port
                }
            })

        @app.route('/api/metrics')
        def api_metrics():
            """API 性能指标（P50/P95/平均/最大 响应时间，按端点分组统计）"""
            try:
                # 按端点分组
                groups = {}
                total_requests = 0
                with _response_times_lock:
                    for rec in _response_times:
                        key = f"{rec['method']} {rec['endpoint']}"
                        if key not in groups:
                            groups[key] = {
                                'endpoint': rec['endpoint'],
                                'method': rec['method'],
                                'durations': []
                            }
                        groups[key]['durations'].append(rec['duration_ms'])
                    total_requests = len(_response_times)

                endpoints = []
                for key, info in groups.items():
                    durations = sorted(info['durations'])
                    count = len(durations)
                    if count == 0:
                        continue

                    def _percentile(sorted_vals, p):
                        """线性插值法计算百分位数"""
                        n = len(sorted_vals)
                        if n == 1:
                            return round(sorted_vals[0], 2)
                        rank = (p / 100) * (n - 1)
                        lo = int(rank)
                        hi = min(lo + 1, n - 1)
                        frac = rank - lo
                        return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac, 2)

                    endpoints.append({
                        'endpoint': info['endpoint'],
                        'method': info['method'],
                        'count': count,
                        'p50_ms': _percentile(durations, 50),
                        'p95_ms': _percentile(durations, 95),
                        'avg_ms': round(sum(durations) / count, 2),
                        'max_ms': round(durations[-1], 2)
                    })

                # 按请求数降序排列
                endpoints.sort(key=lambda x: x['count'], reverse=True)

                return jsonify({
                    'success': True,
                    'data': {
                        'endpoints': endpoints,
                        'total_requests': total_requests
                    }
                })
            except Exception as e:
                self.logger.error(f"获取性能指标失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/api/refresh/<source>', methods=['POST'])
        def api_refresh_source(source: str):
            """刷新单个数据源"""
            try:
                from src.scheduler import TrendingTaskScheduler
                
                self.logger.info(f"收到刷新数据源请求: {source}")
                
                # 验证数据源是否有效
                valid_sources = ['github', 'github_ai', 'bilibili', 'arxiv', 
                               'hackernews', 'zhihu', 'weibo', 'douyin', 'aihot']
                if source not in valid_sources:
                    return jsonify(ApiError(ErrorCode.VALIDATION_ERROR, f'未知的数据源: {source}', status_code=400).to_response()), 400
                
                # 创建临时调度器来执行刷新
                scheduler = TrendingTaskScheduler(logger=self.logger)
                result = scheduler.refresh_data([source])
                
                self.logger.info(f"数据源 {source} 刷新完成")
                
                return jsonify({
                    'success': True,
                    'message': f'{source} 数据刷新成功',
                    'data': {
                        'source': source,
                        'refreshed_at': datetime.now().isoformat()
                    }
                })
            except Exception as e:
                self.logger.error(f"刷新数据源 {source} 失败: {e}")
                return jsonify(ApiError(ErrorCode.INTERNAL_ERROR, f'刷新数据源 {source} 失败', detail=str(e), status_code=500).to_response()), 500

        @app.route('/api/refresh-all', methods=['POST'])
        def api_refresh_all():
            """刷新所有数据源"""
            try:
                from src.scheduler import TrendingTaskScheduler
                
                self.logger.info("收到刷新所有数据源请求")
                
                # 创建临时调度器来执行刷新
                scheduler = TrendingTaskScheduler(logger=self.logger)
                result = scheduler.refresh_data()
                
                self.logger.info("所有数据源刷新完成")
                
                return jsonify({
                    'success': True,
                    'message': '所有数据源刷新成功',
                    'data': {
                        'refreshed_at': datetime.now().isoformat()
                    }
                })
            except Exception as e:
                self.logger.error(f"刷新所有数据源失败: {e}")
                resp, status = handle_api_error(e, self.logger)
                return jsonify(resp), status

        @app.route('/static/<path:filename>')
        def static_files(filename: str):
            """静态文件服务"""
            static_dir = project_root / 'static'
            if not static_dir.exists():
                return "Static directory not found", 404

            try:
                return send_from_directory(static_dir, filename)
            except Exception as e:
                self.logger.error(f"静态文件服务错误: {e}")
                return str(e), 404

        @app.errorhandler(404)
        def not_found(error):
            """404 错误处理 - 返回 JSON 而非重定向,保持 API 契约一致"""
            # 判断是否为 API 请求(路径以 /api/ 开头)
            if request.path.startswith('/api/'):
                return jsonify(ApiError(ErrorCode.DATA_NOT_FOUND, f'接口不存在: {request.path}', status_code=404).to_response()), 404
            # 非 API 请求(浏览器直接访问页面)保持重定向到报告页
            return redirect(ROUTES['report'])

        @app.errorhandler(500)
        def internal_error(error):
            """500 错误处理"""
            self.logger.error(f"服务器内部错误: {error}")
            return jsonify(ApiError(ErrorCode.INTERNAL_ERROR, '服务内部错误', status_code=500).to_response()), 500

    def _get_default_html(self) -> str:
        """获取默认 HTML 页面"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trending Service</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 40px; 
            background: #f5f5f5; 
        }
        .container { 
            max-width: 800px; 
            margin: 0 auto; 
            background: white; 
            padding: 40px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }
        h1 { color: #007bff; }
        .info { 
            background: #e7f3ff; 
            border: 1px solid #b3d9ff; 
            padding: 20px; 
            border-radius: 8px; 
            margin: 20px 0; 
        }
        code { 
            background: #f4f4f4; 
            padding: 2px 6px; 
            border-radius: 3px; 
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 Trending Service</h1>
        <div class="info">
            <h3>Welcome to Trending Service</h3>
            <p>This service collects trending information from GitHub, Bilibili, and ArXiv.</p>
            <p>To generate a report, run:</p>
            <code>python src/main.py --run-task fetch_trending</code>
        </div>
    </div>
</body>
</html>'''

    def start(self, blocking: bool = True):
        """启动服务器"""
        if self.running:
            self.logger.warning("服务器已在运行中")
            return

        try:
            self.logger.info(f"🌐 启动 Flask HTTP 服务器: http://{self.host}:{self.port}")
            
            if not blocking:
                self.server_thread = threading.Thread(
                    target=self._run_server,
                    daemon=True
                )
                self.server_thread.start()
                
                import socket as _socket
                for _ in range(60):
                    try:
                        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                        s.settimeout(0.5)
                        result = s.connect_ex((self.host, self.port))
                        s.close()
                        if result == 0:
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)
                
                self.running = True
                self.logger.info(f"✅ HTTP 服务器已启动: http://{self.host}:{self.port}")
                self.config_watcher.start()
            else:
                self.running = True
                self.config_watcher.start()
                self._run_server()
                
        except Exception as e:
            self.logger.error(f"启动 HTTP 服务器失败: {e}")
            self.stop()
            raise

    def _run_server(self):
        """运行 Flask 服务器"""
        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=False,
                threaded=True,
                use_reloader=False  # 禁用重载器，避免与线程冲突
            )
        except Exception as e:
            self.logger.error(f"服务器运行错误: {e}")

    def stop(self):
        """停止服务器"""
        if not self.running:
            return

        self.logger.info("🛑 正在停止 HTTP 服务器...")
        
        # Flask 没有直接的停止方法，我们需要使用 Werkzeug 的 shutdown
        if self.server_thread and self.server_thread.is_alive():
            # 注意：Flask 的开发服务器没有优雅的关闭方式
            # 在生产环境中应该使用 Gunicorn 或 uWSGI
            pass
        
        self.running = False
        self.config_watcher.stop()
        self.logger.info("✅ HTTP 服务器已停止")

    def is_running(self) -> bool:
        """检查服务器是否在运行"""
        return self.running


# 用于直接运行服务器（测试）
if __name__ == "__main__":
    server = TrendingServer()
    server.start(blocking=True)
