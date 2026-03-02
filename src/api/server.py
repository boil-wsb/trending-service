#!/usr/bin/env python3
"""
API 服务器

提供简单的 HTTP API 接口供前端调用
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
import logging


class APIHandler(BaseHTTPRequestHandler):
    """API 请求处理器"""
    
    # 类变量，存储 scheduler 实例
    scheduler = None
    logger = None
    
    def log_message(self, format, *args):
        """自定义日志"""
        if self.logger:
            self.logger.info(f"{self.address_string()} - {format % args}")
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _send_error(self, message: str, status_code: int = 400):
        """发送错误响应"""
        self._send_json_response({'success': False, 'error': message}, status_code)
    
    def do_OPTIONS(self):
        """处理 OPTIONS 请求（CORS 预检）"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)
        
        # 路由匹配
        if path == '/api/status':
            self._handle_get_status()
        elif path == '/api/health':
            self._handle_health_check()
        else:
            self._send_error('Not Found', 404)
    
    def do_POST(self):
        """处理 POST 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 路由匹配
        if path.startswith('/api/refresh/'):
            source = path.split('/')[-1]
            self._handle_refresh_source(source)
        elif path == '/api/refresh-all':
            self._handle_refresh_all()
        else:
            self._send_error('Not Found', 404)
    
    def _handle_get_status(self):
        """获取所有数据源状态"""
        try:
            if not self.scheduler:
                self._send_error('Scheduler not initialized', 500)
                return
            
            status = self.scheduler.get_fetch_status()
            
            self._send_json_response({
                'success': True,
                'data': {
                    'sources': status,
                    'timestamp': self._get_timestamp()
                }
            })
        except Exception as e:
            if self.logger:
                self.logger.error(f"获取状态失败: {e}")
            self._send_error(str(e), 500)
    
    def _handle_health_check(self):
        """健康检查"""
        self._send_json_response({
            'success': True,
            'data': {
                'status': 'healthy',
                'timestamp': self._get_timestamp()
            }
        })
    
    def _handle_refresh_source(self, source: str):
        """刷新指定数据源"""
        try:
            if not self.scheduler:
                self._send_error('Scheduler not initialized', 500)
                return
            
            # 检查数据源是否有效
            from src.config import DATA_SOURCES
            
            # 特殊处理 github_ai，它是 github 的衍生数据源
            if source == 'github_ai':
                if not DATA_SOURCES.get('github', {}).get('enabled'):
                    self._send_error(f'Source github (parent of github_ai) is disabled', 400)
                    return
            elif source not in DATA_SOURCES:
                self._send_error(f'Unknown source: {source}', 400)
                return
            elif not DATA_SOURCES[source].get('enabled'):
                self._send_error(f'Source {source} is disabled', 400)
                return
            
            # 执行刷新
            success = self.scheduler.force_retry_source(source)
            
            if success:
                # 获取最新状态
                status = self.scheduler.get_fetch_status()
                source_status = status.get(source, {})
                
                self._send_json_response({
                    'success': True,
                    'message': f'{source} 刷新成功',
                    'data': {
                        'source': source,
                        'item_count': source_status.get('item_count', 0),
                        'status': source_status.get('status', 'unknown')
                    }
                })
            else:
                self._send_json_response({
                    'success': False,
                    'message': f'{source} 刷新失败',
                    'data': {
                        'source': source,
                        'status': 'failed'
                    }
                })
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"刷新数据源 {source} 失败: {e}")
            self._send_error(str(e), 500)
    
    def _handle_refresh_all(self):
        """刷新所有数据源"""
        try:
            if not self.scheduler:
                self._send_error('Scheduler not initialized', 500)
                return
            
            # 在后台线程执行刷新
            def refresh_all():
                try:
                    self.scheduler.refresh_data()
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"刷新所有数据源失败: {e}")
            
            thread = threading.Thread(target=refresh_all, daemon=True)
            thread.start()
            
            self._send_json_response({
                'success': True,
                'message': '已开始刷新所有数据源',
                'data': {
                    'status': 'refreshing'
                }
            })
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"刷新所有数据源失败: {e}")
            self._send_error(str(e), 500)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


class APIServer:
    """API 服务器"""
    
    def __init__(self, scheduler, host: str = None, port: int = None, 
                 logger: Optional[logging.Logger] = None):
        """
        初始化 API 服务器
        
        Args:
            scheduler: TrendingTaskScheduler 实例
            host: 主机地址，默认从配置读取
            port: 端口号，默认从配置读取
            logger: 日志记录器
        """
        # 从配置读取默认参数
        from src.config import SERVER
        
        self.scheduler = scheduler
        self.host = host or SERVER.get('host', 'localhost')
        self.port = port or SERVER.get('port', 8000)
        self.logger = logger or logging.getLogger(__name__)
        
        # 设置类变量
        APIHandler.scheduler = scheduler
        APIHandler.logger = logger
        
        self.server = None
        self.thread = None
        self.running = False
    
    def start(self):
        """启动 API 服务器"""
        if self.running:
            self.logger.warning("API 服务器已在运行中")
            return
        
        try:
            self.server = HTTPServer((self.host, self.port), APIHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            
            self.logger.info(f"API 服务器已启动: http://{self.host}:{self.port}")
            self.logger.info(f"  - 获取状态: GET http://{self.host}:{self.port}/api/status")
            self.logger.info(f"  - 刷新数据源: POST http://{self.host}:{self.port}/api/refresh/<source>")
            self.logger.info(f"  - 刷新所有: POST http://{self.host}:{self.port}/api/refresh-all")
        
        except Exception as e:
            self.logger.error(f"启动 API 服务器失败: {e}")
            raise
    
    def stop(self):
        """停止 API 服务器"""
        if not self.running:
            return
        
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            
            if self.thread:
                self.thread.join(timeout=5)
            
            self.running = False
            self.logger.info("API 服务器已停止")
        
        except Exception as e:
            self.logger.error(f"停止 API 服务器失败: {e}")
    
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self.running
