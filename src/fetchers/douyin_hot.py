"""
抖音热榜获取器
使用 Playwright 直接从抖音网页获取热榜数据
"""

import sys
import re
import time
from typing import List, Dict, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem

# 尝试导入 Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class DouyinHotFetcher(BaseFetcher):
    """抖音热榜获取器（使用 Playwright 无头浏览器）"""

    name = "douyin"
    HOT_URL = "https://www.douyin.com/hot"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 50})

    def fetch(self) -> List[TrendingItem]:
        """
        获取抖音热榜

        Returns:
            List[TrendingItem]: 热点数据列表
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.error("Playwright 未安装，无法获取抖音热榜")
            return []

        self.logger.info("开始获取抖音热榜...")

        items = []
        try:
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(headless=True)

                # 创建上下文
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN',
                )

                # 创建页面
                page = context.new_page()

                # 访问抖音热榜
                self.logger.info(f"访问: {self.HOT_URL}")
                page.goto(self.HOT_URL, wait_until='domcontentloaded', timeout=30000)

                # 等待页面加载
                time.sleep(5)

                # 解析热榜数据
                items = self._parse_hot_list(page)

                # 关闭浏览器
                browser.close()

                self.logger.info(f"抖音热榜: 获取 {len(items)} 条数据")

        except PlaywrightTimeout:
            self.logger.error("页面加载超时")
        except Exception as e:
            self.logger.error(f"获取抖音热榜失败: {e}")

        return items

    def _parse_hot_list(self, page) -> List[TrendingItem]:
        """解析抖音热榜页面"""
        items = []

        try:
            # 尝试使用选择器获取更结构化的数据
            hot_cards = page.query_selector_all('[data-e2e="hot-list-item"], .hot-list-item, [class*="hot"] [class*="item"], .list-item')
            
            if hot_cards and len(hot_cards) > 0:
                # 使用结构化解析
                items = self._parse_structured_cards(hot_cards)
            else:
                # 回退到文本解析
                items = self._parse_text_based(page)

            # 限制数量
            limit = self.config.get('limit', 50)
            items = items[:limit]

        except Exception as e:
            self.logger.error(f"解析热榜页面失败: {e}")
            # 尝试文本解析作为后备
            try:
                items = self._parse_text_based(page)
            except Exception as e2:
                self.logger.error(f"文本解析也失败: {e2}")

        return items

    def _parse_structured_cards(self, cards) -> List[TrendingItem]:
        """解析结构化的热榜卡片"""
        items = []
        
        for idx, card in enumerate(cards[:50], 1):  # 最多取50条
            try:
                # 尝试提取标题
                title_el = card.query_selector('[data-e2e="hot-title"], .title, h3, .content-text, [class*="title"]')
                title = title_el.inner_text().strip() if title_el else ""
                
                # 尝试提取热度
                hot_score = 0.0
                hot_text = "0"
                hot_el = card.query_selector('[data-e2e="hot-score"], .hot-score, [class*="hot"], [class*="heat"]')
                if hot_el:
                    hot_text_raw = hot_el.inner_text().strip()
                    match = re.search(r'(\d+(?:\.\d+)?)万', hot_text_raw)
                    if match:
                        hot_score = float(match.group(1)) * 10000
                        hot_text = f"{match.group(1)}万"
                
                # 尝试提取创作者/作者
                author = None
                author_el = card.query_selector('[data-e2e="author"], .author, .creator, [class*="author"], [class*="user"], [class*="creator"]')
                if author_el:
                    author = author_el.inner_text().strip()
                
                if title and len(title) > 3:
                    search_query = title.replace(' ', '').replace('#', '')
                    url = f"https://www.douyin.com/search/{search_query}"
                    
                    item = TrendingItem(
                        source=self.name,
                        title=title,
                        url=url,
                        author=author,
                        description=None,
                        hot_score=hot_score,
                        category='hot',
                        extra={
                            'rank': idx,
                            'hot_text': hot_text,
                        }
                    )
                    if self.validate_item(item):
                        items.append(item)
                        
            except Exception as e:
                self.logger.warning(f"解析卡片失败: {e}")
                continue
        
        return items

    def _parse_text_based(self, page) -> List[TrendingItem]:
        """基于文本的解析（后备方案）"""
        items = []
        text = page.inner_text('body')
        lines = text.split('\n')

        hot_items = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 尝试匹配排名（数字）
            if line.isdigit() and 1 <= int(line) <= 100:
                rank = int(line)

                # 下一行是标题
                if i + 1 < len(lines):
                    title = lines[i + 1].strip()

                    # 再下一行可能是热度
                    hot_score = 0.0
                    hot_text = "0"
                    author = None
                    
                    if i + 2 < len(lines):
                        hot_line = lines[i + 2].strip()
                        # 匹配热度格式: "1207.1万热度" 或 "1207.1万"
                        match = re.search(r'(\d+(?:\.\d+)?)万', hot_line)
                        if match:
                            hot_score = float(match.group(1)) * 10000
                            hot_text = f"{match.group(1)}万"
                            i += 1  # 跳过热度行
                        
                        # 尝试查找创作者（通常在热度之后）
                        # 注意：抖音热榜通常不显示创作者信息，这里仅在有明确标识时才提取
                        # 创作者通常有特定的前缀或标识，如 "@用户名" 或 "创作者：xxx"
                        if i + 3 < len(lines):
                            next_line = lines[i + 3].strip()
                            # 严格判断：只有符合创作者特征的行才认为是创作者
                            # 创作者特征：以 @ 开头，或包含 "创作者"、"作者" 等关键词
                            is_author = (
                                next_line.startswith('@') or
                                '创作者' in next_line or
                                '作者' in next_line or
                                '发布者' in next_line
                            )
                            # 同时排除明显不是创作者的情况（如另一个标题）
                            is_likely_title = (
                                len(next_line) > 15 or  # 标题通常较长
                                '大师赛' in next_line or  # 常见标题关键词
                                '冠军' in next_line or
                                '比赛' in next_line or
                                '决赛' in next_line
                            )
                            if is_author and not is_likely_title:
                                author = next_line
                                i += 1

                    # 过滤无效标题
                    if title and len(title) > 3 and not title.startswith('热度'):
                        hot_items.append({
                            'rank': rank,
                            'title': title,
                            'hot_score': hot_score,
                            'hot_text': hot_text,
                            'author': author
                        })
                    i += 1
            i += 1

        # 转换为 TrendingItem
        for item_data in hot_items:
            try:
                search_query = item_data['title'].replace(' ', '').replace('#', '')
                url = f"https://www.douyin.com/search/{search_query}"

                item = TrendingItem(
                    source=self.name,
                    title=item_data['title'],
                    url=url,
                    author=item_data.get('author'),
                    description=None,
                    hot_score=item_data['hot_score'],
                    category='hot',
                    extra={
                        'rank': item_data['rank'],
                        'hot_text': item_data['hot_text'],
                    }
                )
                if self.validate_item(item):
                    items.append(item)
            except Exception as e:
                self.logger.warning(f"解析条目失败: {e}")
                continue

        return items


def main():
    """主函数"""
    print("🚀 开始获取抖音热榜...")

    fetcher = DouyinHotFetcher()
    items = fetcher.fetch()

    print(f"\n✅ 获取成功: {len(items)} 条数据")
    print("\n前10条数据:")
    for i, item in enumerate(items[:10], 1):
        rank = item.extra.get('rank', '-')
        hot_text = item.extra.get('hot_text', '')
        print(f"{i}. [{rank}] {item.title[:50]}...")
        print(f"   热度: {hot_text}")
        print(f"   链接: {item.url[:60]}...")
        print()


if __name__ == "__main__":
    main()
