"""
Hacker News 热点获取器
获取 Hacker News 热门故事
"""

import sys
import requests
from typing import List, Dict, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem


class HackerNewsFetcher(BaseFetcher):
    """Hacker News 热点获取器"""
    
    name = "hackernews"
    api_base = "https://hacker-news.firebaseio.com/v0"
    
    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 30})
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': REQUESTS.get('user_agent', 'Mozilla/5.0')
        })
    
    def fetch(self) -> List[TrendingItem]:
        """
        获取 Hacker News 热门故事
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        self.logger.info("开始获取 Hacker News 热门故事...")
        
        # 获取热门故事ID列表
        story_ids = self._get_top_stories()
        if not story_ids:
            return []
        
        limit = self.config.get('limit', 30)
        story_ids = story_ids[:limit]
        
        items = []
        for story_id in story_ids:
            try:
                story = self._get_story(story_id)
                if story:
                    item = self._parse_story(story)
                    if self.validate_item(item):
                        items.append(item)
            except Exception as e:
                self.logger.error(f"获取故事 {story_id} 失败: {e}")
                continue
        
        self.logger.info(f"Hacker News: 获取 {len(items)} 条数据")
        return items
    
    def _get_top_stories(self) -> List[int]:
        """获取热门故事ID列表"""
        try:
            url = f"{self.api_base}/topstories.json"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"获取热门故事列表失败: {e}")
            return []
    
    def _get_story(self, story_id: int) -> Optional[Dict]:
        """获取单个故事详情"""
        try:
            url = f"{self.api_base}/item/{story_id}.json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"获取故事 {story_id} 详情失败: {e}")
            return None
    
    def _parse_story(self, story: Dict) -> TrendingItem:
        """解析 HN 故事为统一格式"""
        # HN 文章链接
        story_url = story.get('url')
        if not story_url:
            # 如果没有外部链接，使用 HN 讨论页
            story_url = f"https://news.ycombinator.com/item?id={story.get('id')}"
        
        return TrendingItem(
            source=self.name,
            title=story.get('title', ''),
            url=story_url,
            author=story.get('by'),
            description=None,
            hot_score=float(story.get('score', 0)),
            category='tech',
            extra={
                'hn_id': story.get('id'),
                'descendants': story.get('descendants', 0),  # 评论数
                'type': story.get('type', 'story')
            }
        )


def main():
    """主函数"""
    from datetime import datetime
    
    print("🚀 开始获取 Hacker News 热门数据...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    fetcher = HackerNewsFetcher()
    
    # 获取数据
    items = fetcher.fetch()
    
    print(f"🎉 Hacker News 数据获取完成! 共 {len(items)} 条")
    
    # 显示前5条
    for i, item in enumerate(items[:5], 1):
        print(f"{i}. {item.title} (热度: {item.hot_score})")
    
    return items


if __name__ == "__main__":
    main()
