"""
知乎热榜获取器
获取知乎热榜数据
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


class ZhihuHotFetcher(BaseFetcher):
    """知乎热榜获取器"""
    
    name = "zhihu"
    api_url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
    
    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 50})
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': REQUESTS.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.zhihu.com/hot'
        })
    
    def fetch(self) -> List[TrendingItem]:
        """
        获取知乎热榜
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        self.logger.info("开始获取知乎热榜...")
        
        try:
            response = self.session.get(
                self.api_url,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            items = []
            cards = data.get('data', [])
            limit = self.config.get('limit', 50)
            
            for card in cards[:limit]:
                try:
                    item = self._parse_card(card)
                    if self.validate_item(item):
                        items.append(item)
                except Exception as e:
                    self.logger.warning(f"解析卡片失败: {e}")
                    continue
            
            self.logger.info(f"知乎: 获取 {len(items)} 条数据")
            return items
            
        except Exception as e:
            self.logger.error(f"获取知乎热榜失败: {e}")
            return []
    
    def _parse_card(self, card: Dict) -> TrendingItem:
        """解析知乎卡片"""
        target = card.get('target', {})
        
        # 获取热度文本
        detail_text = card.get('detail_text', '')
        hot_score = self._parse_hot_score(detail_text)
        
        # 构建URL
        question_id = target.get('id')
        url = f"https://www.zhihu.com/question/{question_id}" if question_id else ''
        
        return TrendingItem(
            source=self.name,
            title=target.get('title', ''),
            url=url,
            author=None,
            description=target.get('excerpt', ''),
            hot_score=hot_score,
            category='social',
            extra={
                'answer_count': target.get('answer_count', 0),
                'follower_count': target.get('follower_count', 0),
                'type': target.get('type', 'question')
            }
        )
    
    def _parse_hot_score(self, detail_text: str) -> float:
        """解析热度数值"""
        if not detail_text:
            return 0.0
        
        try:
            # 处理 "1234 万热度" 格式
            if '万' in detail_text:
                num = float(detail_text.replace('万热度', '').replace('万', '').strip())
                return num * 10000
            else:
                # 直接数字
                return float(detail_text.replace('热度', '').strip())
        except:
            return 0.0


def main():
    """主函数"""
    from datetime import datetime
    
    print("🚀 开始获取知乎热榜...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    fetcher = ZhihuHotFetcher()
    
    # 获取数据
    items = fetcher.fetch()
    
    print(f"🎉 知乎热榜获取完成! 共 {len(items)} 条")
    
    # 显示前5条
    for i, item in enumerate(items[:5], 1):
        print(f"{i}. {item.title[:40]}... (热度: {item.hot_score})")
    
    return items


if __name__ == "__main__":
    main()
