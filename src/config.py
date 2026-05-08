"""
配置管理模块
支持从 config.yaml 加载配置，并监听文件变化热加载
"""

import os
import yaml
import hashlib
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / 'config.yaml'

DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
LOGS_DIR = DATA_DIR / "logs"
DB_DIR = DATA_DIR / "db"

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DB_DIR.mkdir(exist_ok=True)

_config: Dict[str, Any] = {}
_config_lock = threading.RLock()
_file_hash: str = ""
_callbacks: List[Callable[[Dict[str, Any]], None]] = []


def _load_yaml() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _resolve_paths(config: Dict[str, Any]) -> Dict[str, Any]:
    if 'database' in config and 'path' in config['database']:
        config['database']['path'] = PROJECT_ROOT / config['database']['path']
    else:
        config.setdefault('database', {})['path'] = DB_DIR / 'trending.db'

    if 'logging' in config and 'file' in config['logging']:
        config['logging']['file'] = PROJECT_ROOT / config['logging']['file']
    else:
        config.setdefault('logging', {})['file'] = LOGS_DIR / 'trending_service.log'

    if 'data_files' in config:
        for key in config['data_files']:
            config['data_files'][key] = PROJECT_ROOT / config['data_files'][key]
    else:
        config.setdefault('data_files', {})

    return config


def _deep_copy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    import copy
    return copy.deepcopy(config)


def _compute_file_hash() -> str:
    with open(CONFIG_FILE, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def _load_config() -> None:
    global _config, _file_hash
    raw_config = _load_yaml()
    _config = _resolve_paths(raw_config)
    _file_hash = _compute_file_hash()


def _on_config_changed() -> None:
    for callback in _callbacks:
        try:
            callback(_config)
        except Exception as e:
            print(f"配置变更回调执行失败: {e}")


def reload_config() -> None:
    global _config
    with _config_lock:
        old_config = _deep_copy_config(_config)
        _load_config()
        if old_config != _config:
            _on_config_changed()
    print("✅ 配置已重新加载")


def register_change_callback(callback: Callable[[Dict[str, Any]], None]) -> None:
    _callbacks.append(callback)


_load_config()

_callbacks.clear()


def get(key: str, default: Any = None) -> Any:
    keys = key.split('.')
    value = _config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
            if value is None:
                return default
        else:
            return default
    return value


def get_database() -> Dict[str, Any]:
    return _config.get('database', {})


def get_server() -> Dict[str, Any]:
    return _config.get('server', {})


def get_data_sources() -> Dict[str, Any]:
    return _config.get('data_sources', {})


def get_schedule() -> Dict[str, Any]:
    return _config.get('schedule', {})


def get_logging() -> Dict[str, Any]:
    return _config.get('logging', {})


def get_requests() -> Dict[str, Any]:
    return _config.get('requests', {})


def get_data_files() -> Dict[str, Any]:
    return _config.get('data_files', {})


def get_routes() -> Dict[str, Any]:
    return _config.get('routes', {})


def get_browser() -> Dict[str, Any]:
    return _config.get('browser', {})


def get_proxy() -> Dict[str, Any]:
    return _config.get('proxy', {})


def get_source_urls() -> Dict[str, Any]:
    return _config.get('source_urls', {})


class ConfigHotReloader:
    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _watch_loop(self):
        global _file_hash
        while self._running:
            try:
                current_hash = _compute_file_hash()
                if current_hash != _file_hash:
                    print("🔄 检测到配置文件变更，开始热加载...")
                    reload_config()
            except Exception as e:
                print(f"⚠️ 配置热加载检查失败: {e}")
            threading.Event().wait(self.interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        print(f"✅ 配置热加载监视已启动（间隔 {self.interval} 秒）")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)


DATABASE = get_database()
SERVER = get_server()
DATA_SOURCES = get_data_sources()
SCHEDULE = get_schedule()
LOGGING = get_logging()
REQUESTS = get_requests()
DATA_FILES = get_data_files()
ROUTES = get_routes()
BROWSER = get_browser()
PROXY = get_proxy()
SOURCE_URLS = get_source_urls()


def parse_cron_expression(cron_expr: str) -> dict:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}. Expected 5 parts, got {len(parts)}")

    def parse_field(field: str, min_val: int, max_val: int, field_name: str) -> list:
        values = set()
        for part in field.split(','):
            part = part.strip()
            if part.startswith('*/'):
                step = int(part[2:])
                values.update(range(min_val, max_val + 1, step))
            elif '-' in part:
                start, end = map(int, part.split('-'))
                values.update(range(start, end + 1))
            elif part.isdigit():
                values.add(int(part))
            elif part == '*':
                values.update(range(min_val, max_val + 1))
            else:
                raise ValueError(f"Invalid {field_name} value: {part}")
        for v in values:
            if not (min_val <= v <= max_val):
                raise ValueError(f"{field_name} value {v} out of range [{min_val}, {max_val}]")
        return sorted(list(values))

    return {
        'minute': parse_field(parts[0], 0, 59, 'minute'),
        'hour': parse_field(parts[1], 0, 23, 'hour'),
        'day': parse_field(parts[2], 1, 31, 'day'),
        'month': parse_field(parts[3], 1, 12, 'month'),
        'weekday': parse_field(parts[4], 0, 6, 'weekday'),
        'raw': cron_expr
    }


def validate_cron_expression(cron_expr: str) -> bool:
    try:
        parse_cron_expression(cron_expr)
        return True
    except ValueError:
        return False


def get_next_run_time(cron_expr: str, timezone: str = 'Asia/Shanghai') -> 'datetime':
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    parsed = parse_cron_expression(cron_expr)
    now = datetime.now(ZoneInfo(timezone))
    check_time = now.replace(second=0, microsecond=0)

    for _ in range(366 * 24 * 60):
        check_time += timedelta(minutes=1)
        if (check_time.minute in parsed['minute'] and
            check_time.hour in parsed['hour'] and
            check_time.day in parsed['day'] and
            check_time.month in parsed['month'] and
            check_time.weekday() in parsed['weekday']):
            return check_time

    raise ValueError("Could not find next run time within one year")


def is_time_to_run(schedule_config: dict, current_time: 'datetime' = None) -> bool:
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    if not schedule_config.get('enabled', False):
        return False

    schedule = schedule_config.get('schedule', '')
    timezone = schedule_config.get('timezone', 'Asia/Shanghai')

    if current_time is None:
        current_time = datetime.now(ZoneInfo(timezone))
    else:
        current_time = current_time.astimezone(ZoneInfo(timezone))

    if ':' in schedule and ' ' not in schedule and schedule.count(':') == 1:
        hour, minute = map(int, schedule.split(':'))
        return current_time.hour == hour and current_time.minute == minute

    try:
        parsed = parse_cron_expression(schedule)
        return (current_time.minute in parsed['minute'] and
                current_time.hour in parsed['hour'] and
                current_time.day in parsed['day'] and
                current_time.month in parsed['month'] and
                current_time.weekday() in parsed['weekday'])
    except ValueError:
        return False
