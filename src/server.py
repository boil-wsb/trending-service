"""
HTTP服务器模块
使用 Flask 框架提供 Web 服务
"""

import sys
import threading
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path
from functools import wraps

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, send_from_directory, redirect, Response, request
from src.config import SERVER, REPORTS_DIR, ROUTES, DATABASE, ConfigHotReloader
from src.utils import get_logger


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


def cached(ttl_seconds=30, key_prefix=''):
    """
    API 响应缓存装饰器

    Args:
        ttl_seconds: 缓存存活时间（秒）
        key_prefix: 缓存 key 前缀，用于按前缀清除
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存 key：前缀 + 函数名 + 参数哈希
            arg_str = json.dumps({
                'args': [str(a) for a in args],
                'kwargs': {k: str(v) for k, v in kwargs.items()},
                'query': dict(request.args) if request else {}
            }, sort_keys=True)
            key_hash = hashlib.md5(arg_str.encode()).hexdigest()[:12]
            cache_key = f"{key_prefix}:{func.__name__}:{key_hash}"

            # 尝试读缓存
            cached_val = _api_cache.get(cache_key)
            if cached_val is not None:
                return cached_val

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            _api_cache.set(cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator


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

        # ========== 指数行情API ==========

        @app.route('/api/index/market')
        def api_index_market():
            """A股市场指数列表"""
            try:
                from src.db.index_dao import IndexDAO

                dao = IndexDAO(DATABASE['path'])
                indices = dao.get_market_indices(limit=50)

                return jsonify({
                    'success': True,
                    'data': {
                        'indices': [idx.to_dict() for idx in indices],
                        'count': len(indices),
                        'fetched_at': indices[0].fetched_at.strftime('%Y-%m-%d %H:%M:%S') if indices else None
                    }
                })
            except Exception as e:
                self.logger.error(f"获取市场指数失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/industry')
        def api_index_industry():
            """申万行业指数列表（含 3日/7日 涨跌幅，30s 缓存）"""
            try:
                from src.db.index_dao import IndexDAO
                from flask import request

                try:
                    limit = min(int(request.args.get('limit', 500)), 1000)
                except (ValueError, TypeError):
                    limit = 500

                # 缓存检查（30s TTL）
                cache_key = f"industry:{limit}"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                # 使用带多日涨跌幅的方法（先排序后 limit）
                indices = dao.get_industry_indices_with_changes(limit=limit)

                result = jsonify({
                    'success': True,
                    'data': {
                        'indices': [idx.to_dict() for idx in indices],
                        'count': len(indices),
                        'fetched_at': indices[0].fetched_at.strftime('%Y-%m-%d %H:%M:%S') if indices else None
                    }
                })
                _api_cache.set(cache_key, result, ttl=30)
                return result
            except Exception as e:
                self.logger.error(f"获取行业指数失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

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
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/detail')
        def api_index_detail():
            """指数历史数据（按代码查询）"""
            try:
                from src.db.index_dao import IndexDAO
                from flask import request

                code = request.args.get('code')
                if not code:
                    return jsonify({'success': False, 'error': '缺少指数代码参数: code'}), 400

                try:
                    limit = min(int(request.args.get('limit', 30)), 200)
                except (ValueError, TypeError):
                    limit = 30

                dao = IndexDAO(DATABASE['path'])
                indices = dao.get_index_by_code(code, limit=limit)

                if not indices:
                    return jsonify({'success': False, 'error': f'未找到指数: {code}'}), 404

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
                return jsonify({'success': False, 'error': str(e)}), 500

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
                    return jsonify({'success': False, 'error': '缺少指数代码参数: code'}), 400

                try:
                    days = min(int(request.args.get('days', 30)), 365)
                except (ValueError, TypeError):
                    days = 30

                # 强制刷新参数：?force=1 跳过缓存直接拉取
                force_refresh = request.args.get('force', '0') == '1'

                # API 内存缓存检查（5min TTL，强制刷新时跳过）
                cache_key = f"kline:{code}:{days}"
                if not force_refresh:
                    cached = _api_cache.get(cache_key)
                    if cached is not None:
                        return cached

                # 根据指数代码类型确定数据源
                if code.startswith('80') and len(code) == 6 and code.isdigit():
                    source = 'sw'      # 申万行业指数
                elif code.isdigit() and len(code) == 6:
                    source = 'sina'    # 市场指数（新浪源）
                else:
                    source = 'ths'     # 概念板块（同花顺源）

                dao = IndexDAO(DATABASE['path'])

                # 1. 先读数据库缓存（使用对应数据源）
                if not force_refresh:
                    cached = dao.get_klines(code, days=days, source=source)
                    latest_date = dao.get_kline_latest_date(code, source=source)

                    # 2. 判断缓存是否需要刷新（最新日期不是今天且不是周末）
                    today = datetime.now().date()
                    need_refresh = True
                    if latest_date:
                        try:
                            latest_dt = datetime.strptime(latest_date, '%Y-%m-%d').date()
                            # 如果缓存最新日期是今天，或今天是周末（市场休市），则不需要刷新
                            if latest_dt >= today or today.weekday() >= 5:
                                need_refresh = False
                            # 如果缓存最新日期是昨天且今天还没到收盘时间（15:00），也不刷新
                            elif latest_dt == today - timedelta(days=1) and datetime.now().hour < 15:
                                need_refresh = False
                        except ValueError:
                            pass

                    # 3. 如果缓存有效，直接返回
                    if cached and not need_refresh:
                        return jsonify({
                            'success': True,
                            'data': {
                                'code': code,
                                'kline': cached,
                                'count': len(cached),
                                'source': 'cache'
                            }
                        })

                # 4. 缓存不存在或过期或强制刷新，按指数类型从对应数据源拉取
                fetcher = IndexFetcher(logger=self.logger)
                kline = fetcher.fetch_kline(code, days=days)

                # 5. 保存到数据库缓存（使用对应数据源标识）
                if kline:
                    try:
                        dao.save_klines(code, kline, source=source)
                        self.logger.info(f"K线数据已缓存: {code} {len(kline)} 条 (source={source})")
                    except Exception as e:
                        self.logger.warning(f"K线数据缓存失败: {e}")

                result = jsonify({
                    'success': True,
                    'data': {
                        'code': code,
                        'kline': kline,
                        'count': len(kline),
                        'source': source
                    }
                })
                _api_cache.set(cache_key, result, ttl=300)  # 5min 缓存
                return result
            except Exception as e:
                self.logger.error(f"获取指数K线失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/rotation')
        def api_index_rotation():
            """行业轮动分析数据（60s 缓存）

            返回行业指数的多周期涨跌幅排名、动量得分、成交额，
            用于前端展示强势/弱势排名表、热力图、轮动趋势。
            """
            try:
                from src.db.index_dao import IndexDAO

                # 缓存检查（60s TTL）
                cache_key = "rotation:all"
                cached = _api_cache.get(cache_key)
                if cached is not None:
                    return cached

                dao = IndexDAO(DATABASE['path'])
                # 获取全部行业指数（含 3日/7日涨跌幅）
                indices = dao.get_industry_indices_with_changes(limit=500)
                if not indices:
                    result = jsonify({'success': True, 'data': {'indices': [], 'count': 0}})
                    _api_cache.set(cache_key, result, ttl=60)
                    return result

                # 计算排名和动量得分
                items = []
                for idx in indices:
                    change_3d = idx.change_pct_3d if idx.change_pct_3d is not None else 0
                    change_7d = idx.change_pct_7d if idx.change_pct_7d is not None else 0
                    # 动量得分 = 今日(40%) + 3日(30%) + 7日(30%)
                    momentum = round(idx.change_pct * 0.4 + change_3d * 0.3 + change_7d * 0.3, 2)
                    items.append({
                        'code': idx.code,
                        'name': idx.name,
                        'price': round(idx.price, 2),
                        'change_pct': round(idx.change_pct, 2),
                        'change_pct_3d': idx.change_pct_3d,
                        'change_pct_7d': idx.change_pct_7d,
                        'amount': round(idx.amount / 100000000, 2) if idx.amount else 0,
                        'momentum': momentum,
                        'source': idx.source
                    })

                # 按各周期排名
                for field in ['change_pct', 'change_pct_3d', 'change_pct_7d', 'momentum']:
                    sorted_items = sorted(items, key=lambda x: x.get(field, 0) or 0, reverse=True)
                    for rank, item in enumerate(sorted_items, 1):
                        item[f'rank_{field}'] = rank

                # 按动量得分排序返回
                items.sort(key=lambda x: x['momentum'], reverse=True)

                result = jsonify({
                    'success': True,
                    'data': {
                        'indices': items,
                        'count': len(items),
                        'top_strong': items[:10],
                        'top_weak': items[-10:][::-1]
                    }
                })
                _api_cache.set(cache_key, result, ttl=60)
                return result
            except Exception as e:
                self.logger.error(f"获取行业轮动数据失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/trigger-fetch', methods=['POST'])
        def api_index_trigger_fetch():
            """手动触发指数数据获取"""
            try:
                from src.fetchers.index import IndexFetcher

                fetcher = IndexFetcher(logger=self.logger)
                count = fetcher.save_to_db(DATABASE['path'])

                self.logger.info(f"手动触发指数数据获取完成: {count} 条")

                return jsonify({
                    'success': True,
                    'data': {
                        'count': count,
                        'message': f'成功获取 {count} 条指数数据'
                    }
                })
            except Exception as e:
                self.logger.error(f"手动触发指数数据获取失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

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
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/style-rotation')
        def api_index_style_rotation():
            """风格轮动强弱（大盘价值↔小盘成长等）"""
            try:
                from src.fetchers.fund_flow import (
                    fetch_style_index_realtime, fetch_style_index_kline
                )
                from flask import request
                import threading, queue, pathlib

                days = min(int(request.args.get('days', 30)), 90)

                # 用线程 + 超时避免 akshare 卡住
                def _worker(q):
                    try:
                        realtime = fetch_style_index_realtime()
                        kline = fetch_style_index_kline(days=days)
                        q.put({'realtime': realtime, 'kline': kline})
                    except Exception as e:
                        q.put({'error': str(e)})

                q = queue.Queue()
                t = threading.Thread(target=_worker, args=(q,))
                t.daemon = True
                t.start()
                t.join(timeout=15)  # 最多等 15 秒

                if t.is_alive():
                    self.logger.warning("style-rotation: akshare timeout, returning empty")
                    return jsonify({
                        'success': True,
                        'data': {'realtime': [], 'kline': {}, 'days': days}
                    })

                result = q.get_nowait() if not q.empty() else {}
                if 'error' in result:
                    self.logger.error(f"style-rotation error: {result['error']}")
                    return jsonify({'success': False, 'error': result['error']}), 500

                return jsonify({
                    'success': True,
                    'data': {
                        'realtime': result.get('realtime', []),
                        'kline': result.get('kline', {}),
                        'days': days,
                    }
                })
            except Exception as e:
                self.logger.error(f"获取风格轮动数据失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/index/northbound')
        def api_index_northbound():
            """北向资金动向与趋势（含连续流入天数）"""
            try:
                from src.fetchers.fund_flow import (
                    fetch_northbound_summary, fetch_northbound_history,
                    fetch_northbound_streak
                )
                from flask import request

                days = min(int(request.args.get('days', 30)), 90)
                summary = fetch_northbound_summary()
                history = fetch_northbound_history(days=days)
                streak = fetch_northbound_streak(days=days)
                return jsonify({
                    'success': True,
                    'data': {
                        'summary': summary,
                        'history': history,
                        'streak': streak,
                        'days': days,
                    }
                })
            except Exception as e:
                self.logger.error(f"获取北向资金数据失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

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
                return jsonify({'error': 'Invalid data type'}), 400
            
            data_file = REPORTS_DIR / f"{data_type}.json"
            
            if not data_file.exists():
                return jsonify({'error': 'Data not found'}), 404
            
            try:
                import json
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                response = jsonify(data)
                response.headers.add('Access-Control-Allow-Origin', '*')
                return response
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON 解析错误: {e}")
                return jsonify({'error': 'Invalid JSON'}), 500
            except Exception as e:
                self.logger.error(f"读取数据失败: {e}")
                return jsonify({'error': str(e)}), 500

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
                    return jsonify({'success': False, 'error': 'Invalid date format. Expected: YYYY-MM-DD'}), 400
            elif start_date_param and end_date_param:
                # 日期范围模式
                try:
                    start_date = datetime.strptime(start_date_param, '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_param, '%Y-%m-%d').date()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid date format. Expected: YYYY-MM-DD'}), 400
                
                # 验证日期范围
                if start_date > end_date:
                    return jsonify({'success': False, 'error': 'start_date cannot be later than end_date'}), 400
            else:
                return jsonify({'success': False, 'error': 'Missing required parameters: date or start_date/end_date'}), 400
            
            # 检查是否是未来日期
            today = datetime.now().date()
            if end_date > today:
                return jsonify({'success': False, 'error': 'Cannot query future dates'}), 400
            
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
                return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

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
                return jsonify({'success': False, 'error': 'Missing search query parameter: q'}), 400

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
                return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

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
                    return jsonify({
                        'success': False, 
                        'message': f'未知的数据源: {source}. 有效的数据源: {", ".join(valid_sources)}'
                    }), 400
                
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
                return jsonify({
                    'success': False, 
                    'message': f'刷新失败: {str(e)}'
                }), 500

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
                return jsonify({
                    'success': False, 
                    'message': f'刷新失败: {str(e)}'
                }), 500

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
            """404 错误处理"""
            return redirect(ROUTES['report'])

        @app.errorhandler(500)
        def internal_error(error):
            """500 错误处理"""
            self.logger.error(f"服务器内部错误: {error}")
            return jsonify({'error': 'Internal Server Error'}), 500

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
