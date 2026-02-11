"""
HTTP服务器模块
使用 Flask 框架提供 Web 服务
"""

import sys
import threading
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from flask import Flask, jsonify, send_from_directory, redirect, Response
from src.config import SERVER, REPORTS_DIR, ROUTES
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
