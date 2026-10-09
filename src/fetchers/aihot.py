"""
AI HOT 资讯获取器
获取 aihot.news 上的 AI 动态和精选资讯（/api/v1 匿名只读接口）

2026-10 迁移（官方迁移指南 https://aihot.news/agent?tab=api#legacy-api-migration）：
- 旧域名 aihot.virxact.com 与 /api/public/* 接口 2026-10-31 停用，改用
  https://aihot.news/api/v1/*（字段一一对应）。
- 字段映射：url→links.original、permalink→links.aihot、title_en→originalTitle、
  source→source.name、take→limit；日报 /api/public/daily → /api/v1/dailies/latest
  （从响应顶层 report 读取）。
- HTTP 栈使用 curl_cffi（curl 原生 TLS 指纹）：aihot.news 边缘安全规则会掐断
  python-requests/urllib3 的 TLS ClientHello（SSL EOF），curl 指纹实测通过；
  官方要求不要伪装浏览器 UA，故 UA 用 aihot-api/2.0.0 规范格式。
"""

import sys
from curl_cffi import requests as cffi_requests
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem


class AihotFetcher(BaseFetcher):
    """AI HOT 资讯获取器"""

    name = "aihot"
    api_base = "https://aihot.news"
    # 官方匿名统计标识（非账号非密钥，仅用于合并统计）；固定值保证统计口径稳定
    ACTOR_ID = "5cfb029b-4107-4c60-8147-98657dc2d792"

    CATEGORY_MAP = {
        'ai-models': 'ai-models',
        'ai-products': 'ai-products',
        'industry': 'industry',
        'paper': 'paper',
        'tip': 'tip',
    }

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 30})
        # impersonate=None：使用 curl 原生 TLS 指纹（非浏览器伪装，见模块 docstring）
        self.session = cffi_requests.Session(impersonate=None)
        self.session.headers.update({
            'User-Agent': f'aihot-api/2.0.0 aihot-actor/{self.ACTOR_ID}',
            'Accept': 'application/json',
        })

    def fetch(self) -> List[TrendingItem]:
        """
        获取 AI HOT 精选资讯

        Returns:
            List[TrendingItem]: 资讯数据列表
        """
        self.logger.info("开始获取 AI HOT 资讯...")

        limit = self.config.get('limit', 30)
        mode = self.config.get('mode', 'selected')
        category = self.config.get('category')

        params = {
            'mode': mode,
            'limit': min(limit, 100),  # v1：旧 take 改名 limit
        }

        if category:
            params['category'] = category

        try:
            url = f"{self.api_base}/api/v1/items"
            response = self.session.get(url, params=params, timeout=REQUESTS.get('timeout', 60))
            response.raise_for_status()
            data = response.json()
        except cffi_requests.exceptions.HTTPError as e:
            self.logger.error(f"AIHOT API HTTP 错误: {e}")
            return []
        except cffi_requests.exceptions.RequestException as e:
            self.logger.error(f"AIHOT API 请求失败: {e}")
            return []
        except ValueError as e:
            self.logger.error(f"AIHOT API 响应解析失败: {e}")
            return []

        raw_items = data.get('items', [])
        if not raw_items:
            self.logger.info("AI HOT: 无数据返回")
            return []

        items = []
        for raw in raw_items:
            try:
                item = self._parse_item(raw)
                if self.validate_item(item):
                    items.append(item)
            except Exception as e:
                self.logger.error(f"解析 AIHOT 条目失败: {e}")
                continue

        self.logger.info(f"AI HOT: 获取 {len(items)} 条数据")
        return items

    def _parse_item(self, raw: Dict) -> TrendingItem:
        """解析 AIHOT v1 API 条目为统一格式

        v1 字段映射（对照旧 /api/public/items）：
        - url      → links.original（兜底 links.aihot，validate_item 要求 url 非空）
        - title_en → originalTitle
        - source   → source.name（旧为字符串，v1 为对象）
        - id / publishedAt / category / title / summary 保持不变
        """
        category = raw.get('category')
        mapped_category = self.CATEGORY_MAP.get(category, category) if category else None

        links = raw.get('links') or {}
        url = links.get('original') or links.get('aihot') or ''

        source = raw.get('source')
        if isinstance(source, dict):
            author = source.get('name')
        else:
            author = source  # 兼容旧结构（纯字符串）

        extra = {
            'aihot_id': raw.get('id'),
        }

        if raw.get('originalTitle'):
            extra['title_en'] = raw['originalTitle']

        if raw.get('publishedAt'):
            extra['published_at'] = raw['publishedAt']

        return TrendingItem(
            source=self.name,
            title=raw.get('title', ''),
            url=url,
            author=author,
            description=raw.get('summary'),
            hot_score=None,
            category=mapped_category,
            extra=extra,
        )

    def fetch_daily(self) -> Optional[Dict]:
        """
        获取最新 AI HOT 日报

        Returns:
            日报数据字典（report 对象，含 date/sections/flashes），或 None
        """
        self.logger.info("获取 AI HOT 最新日报...")

        try:
            url = f"{self.api_base}/api/v1/dailies/latest"
            response = self.session.get(url, timeout=REQUESTS.get('timeout', 60))
            response.raise_for_status()
            data = response.json()
            # v1：日报内容从响应顶层 report 读取（迁移指南明确）
            report = data.get('report') or {}
            self.logger.info(f"AI HOT 日报获取成功: {report.get('date', 'unknown')}")
            return report or None
        except Exception as e:
            self.logger.error(f"获取 AI HOT 日报失败: {e}")
            return None


def main():
    """主函数"""
    print("🚀 开始获取 AI HOT 资讯...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    fetcher = AihotFetcher()
    items = fetcher.fetch()

    print(f"🎉 AI HOT 数据获取完成! 共 {len(items)} 条")

    for i, item in enumerate(items[:5], 1):
        print(f"{i}. {item.title} ({item.author})")

    return items


if __name__ == "__main__":
    main()
