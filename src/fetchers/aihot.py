"""
AI HOT 资讯获取器
获取 aihot.virxact.com 上的 AI 动态和精选资讯
"""

import sys
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem


class AihotFetcher(BaseFetcher):
    """AI HOT 资讯获取器"""

    name = "aihot"
    api_base = "https://aihot.virxact.com"

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
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': REQUESTS.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
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
            'take': min(limit, 100),
        }

        if category:
            params['category'] = category

        try:
            url = f"{self.api_base}/api/public/items"
            response = self.session.get(url, params=params, timeout=REQUESTS.get('timeout', 60))
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"AIHOT API HTTP 错误: {e}")
            return []
        except requests.exceptions.RequestException as e:
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
        """解析 AIHOT API 条目为统一格式"""
        category = raw.get('category')
        mapped_category = self.CATEGORY_MAP.get(category, category) if category else None

        extra = {
            'aihot_id': raw.get('id'),
        }

        if raw.get('title_en'):
            extra['title_en'] = raw['title_en']

        if raw.get('publishedAt'):
            extra['published_at'] = raw['publishedAt']

        return TrendingItem(
            source=self.name,
            title=raw.get('title', ''),
            url=raw.get('url', ''),
            author=raw.get('source'),
            description=raw.get('summary'),
            hot_score=None,
            category=mapped_category,
            extra=extra,
        )

    def fetch_daily(self) -> Optional[Dict]:
        """
        获取最新 AI HOT 日报

        Returns:
            日报数据字典，或 None
        """
        self.logger.info("获取 AI HOT 最新日报...")

        try:
            url = f"{self.api_base}/api/public/daily"
            response = self.session.get(url, timeout=REQUESTS.get('timeout', 60))
            response.raise_for_status()
            data = response.json()
            self.logger.info(f"AI HOT 日报获取成功: {data.get('date', 'unknown')}")
            return data
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
