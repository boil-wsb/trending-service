"""
HTTP服务器模块
使用 Flask 框架提供 Web 服务
"""

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, send_from_directory, redirect, Response, request
from src.config import SERVER, REPORTS_DIR, ROUTES, DATABASE
from src.utils import get_logger


class TrendingServer:
    """Trending Service HTTP 服务器 (Flask)"""

    def __init__(self, host: str = None, port: int = None, logger=None):
        self.host = host or SERVER['host']
        self.port = port or SERVER['port']
        self.logger = logger or get_logger('server')
        self.app = self._create_app()
        self.server_thread = None
        self.running = False

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
        
        # ========== 股票行情API (必须在通用路由之前注册) ==========
        
        @app.route('/api/stock/fetch-control', methods=['GET', 'POST'])
        def api_stock_fetch_control():
            """股票数据获取控制"""
            try:
                from src.config import DATA_SOURCES

                if request.method == 'GET':
                    # 获取当前状态
                    return jsonify({
                        'success': True,
                        'data': {
                            'enabled': DATA_SOURCES.get('stock', {}).get('enabled', True),
                            'auto_fetch': DATA_SOURCES.get('stock', {}).get('auto_fetch', True)
                        }
                    })
                else:
                    # POST - 更新状态
                    data = request.get_json()
                    if data is None:
                        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

                    enabled = data.get('enabled')
                    auto_fetch = data.get('auto_fetch')

                    # 更新配置
                    if 'stock' not in DATA_SOURCES:
                        DATA_SOURCES['stock'] = {}

                    if enabled is not None:
                        DATA_SOURCES['stock']['enabled'] = bool(enabled)
                    if auto_fetch is not None:
                        DATA_SOURCES['stock']['auto_fetch'] = bool(auto_fetch)

                    self.logger.info(f"股票数据获取控制更新: enabled={DATA_SOURCES['stock'].get('enabled')}, auto_fetch={DATA_SOURCES['stock'].get('auto_fetch')}")

                    return jsonify({
                        'success': True,
                        'data': {
                            'enabled': DATA_SOURCES['stock'].get('enabled', True),
                            'auto_fetch': DATA_SOURCES['stock'].get('auto_fetch', True)
                        }
                    })
            except Exception as e:
                self.logger.error(f"股票数据获取控制失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/stock/trigger-fetch', methods=['POST'])
        def api_stock_trigger_fetch():
            """手动触发股票数据获取"""
            try:
                from src.fetchers.stock import StockFetcher
                from src.config import DATABASE

                fetcher = StockFetcher(logger=self.logger)
                count = fetcher.save_to_db(DATABASE['path'])

                self.logger.info(f"手动触发股票数据获取完成: {count} 条")

                return jsonify({
                    'success': True,
                    'data': {
                        'count': count,
                        'message': f'成功获取 {count} 条股票数据'
                    }
                })
            except Exception as e:
                self.logger.error(f"手动触发股票数据获取失败: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.route('/api/stock/market')
        def api_stock_market():
            """A股市场概览数据"""
            try:
                from src.db.stock_dao import StockDAO

                dao = StockDAO(DATABASE['path'])
                gainers = dao.get_gainers(10)
                losers = dao.get_losers(10)
                volume_list = dao.get_by_volume(10)

                return jsonify({
                    'success': True,
                    'data': {
                        'gainers': [s.to_dict() for s in gainers],
                        'losers': [s.to_dict() for s in losers],
                        'volume': [s.to_dict() for s in volume_list],
                        'fetched_at': gainers[0].fetched_at.strftime('%Y-%m-%d %H:%M:%S') if gainers else None
                    }
                })
            except Exception as e:
                self.logger.error(f"获取股票市场数据失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/summary')
        def api_stock_summary():
            """市场整体概况"""
            try:
                from src.db.stock_dao import StockDAO

                dao = StockDAO(DATABASE['path'])
                summary = dao.get_market_summary()

                return jsonify({
                    'success': True,
                    'data': summary
                })
            except Exception as e:
                self.logger.error(f"获取市场概况失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/gainers')
        def api_stock_gainers():
            """涨幅榜"""
            try:
                from src.db.stock_dao import StockDAO
                from flask import request

                dao = StockDAO(DATABASE['path'])
                limit = int(request.args.get('limit', 10))
                gainers = dao.get_gainers(limit)

                return jsonify({
                    'success': True,
                    'data': {
                        'gainers': [s.to_dict() for s in gainers],
                        'count': len(gainers)
                    }
                })
            except Exception as e:
                self.logger.error(f"获取涨幅榜失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/losers')
        def api_stock_losers():
            """跌幅榜"""
            try:
                from src.db.stock_dao import StockDAO
                from flask import request

                dao = StockDAO(DATABASE['path'])
                limit = int(request.args.get('limit', 10))
                losers = dao.get_losers(limit)

                return jsonify({
                    'success': True,
                    'data': {
                        'losers': [s.to_dict() for s in losers],
                        'count': len(losers)
                    }
                })
            except Exception as e:
                self.logger.error(f"获取跌幅榜失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/volume')
        def api_stock_volume():
            """成交额榜"""
            try:
                from src.db.stock_dao import StockDAO

                dao = StockDAO(DATABASE['path'])
                volume_list = dao.get_by_volume(10)

                return jsonify({
                    'success': True,
                    'data': {
                        'volume': [s.to_dict() for s in volume_list],
                        'count': len(volume_list)
                    }
                })
            except Exception as e:
                self.logger.error(f"获取成交额榜失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/detail')
        def api_stock_detail():
            """个股详情"""
            try:
                from src.db.stock_dao import StockDAO
                from flask import request

                code = request.args.get('code')
                if not code:
                    return jsonify({'error': '缺少股票代码参数: code'}), 400

                dao = StockDAO(DATABASE['path'])
                detail = dao.get_stock_detail(code)

                if not detail:
                    return jsonify({'error': f'未找到股票: {code}'}), 404

                return jsonify({
                    'success': True,
                    'data': detail
                })
            except Exception as e:
                self.logger.error(f"获取股票详情失败: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/api/stock/kline')
        def api_stock_kline():
            """K线数据"""
            try:
                from src.fetchers.stock import StockFetcher
                from flask import request

                code = request.args.get('code')
                if not code:
                    return jsonify({'error': '缺少股票代码参数: code'}), 400

                days = int(request.args.get('days', 30))
                fetcher = StockFetcher(logger=self.logger)
                kline = fetcher.fetch_kline(code, days)

                return jsonify({
                    'success': True,
                    'data': kline
                })
            except Exception as e:
                self.logger.error(f"获取K线数据失败: {e}")
                return jsonify({'error': str(e)}), 500

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
            """按日期获取数据 API"""
            from datetime import datetime
            from src.db import TrendingDAO
            from src.config import DATABASE
            
            # 获取日期参数
            date_param = request.args.get('date')
            
            if not date_param:
                return jsonify({'success': False, 'error': 'Missing required parameter: date'}), 400
            
            # 验证日期格式
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Expected: YYYY-MM-DD'}), 400
            
            # 检查是否是未来日期
            today = datetime.now().date()
            if target_date > today:
                return jsonify({'success': False, 'error': 'Cannot query future dates'}), 400
            
            try:
                # 从数据库获取数据
                dao = TrendingDAO(DATABASE['path'])
                
                # 获取指定日期的数据
                items = dao.get_items(
                    start_date=target_date,
                    end_date=target_date,
                    limit=10000
                )
                
                # 如果没有数据，返回友好提示
                if not items:
                    return jsonify({
                        'success': True,
                        'data': {
                            'date': date_param,
                            'items': [],
                            'sources': {},
                            'total_items': 0,
                            'message': f'No data available for {date_param}'
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
                        'date': date_param,
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
            
            # 在非阻塞模式下使用线程运行服务器
            if not blocking:
                self.server_thread = threading.Thread(
                    target=self._run_server,
                    daemon=True
                )
                self.server_thread.start()
                # 等待服务器启动
                time.sleep(1)
                self.running = True
                self.logger.info(f"✅ HTTP 服务器已启动: http://{self.host}:{self.port}")
            else:
                self.running = True
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
        self.logger.info("✅ HTTP 服务器已停止")

    def is_running(self) -> bool:
        """检查服务器是否在运行"""
        return self.running


# 用于直接运行服务器（测试）
if __name__ == "__main__":
    server = TrendingServer()
    server.start(blocking=True)
