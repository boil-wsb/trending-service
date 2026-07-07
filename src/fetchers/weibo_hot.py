"""
微博热榜获取器
使用 Playwright 无头浏览器爬取微博热搜
"""

import sys
import re
import time
from typing import List, Dict, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS, SOURCE_URLS
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem

# 尝试导入 Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class WeiboHotFetcher(BaseFetcher):
    """微博热榜获取器（使用 Playwright 无头浏览器）"""

    name = "weibo"
    HOT_URL = "https://s.weibo.com/top/summary"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 50})
        # P2: 统一从 config 读取 UA/超时/URL
        self.user_agent = REQUESTS.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        self.page_timeout = int(REQUESTS.get('timeout', 60)) * 1000  # 秒 -> 毫秒
        self.hot_url = SOURCE_URLS.get('weibo_hot', self.HOT_URL)

    def fetch(self) -> List[TrendingItem]:
        """
        获取微博热榜

        Returns:
            List[TrendingItem]: 热点数据列表
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.error("Playwright 未安装，无法获取微博热榜")
            return []

        self.logger.info("开始获取微博热榜...")

        items = []
        try:
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                    ]
                )

                # 创建上下文
                context = browser.new_context(
                    user_agent=self.user_agent,
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN',
                )

                # 创建页面
                page = context.new_page()

                # 访问微博热搜
                self.logger.info(f"访问: {self.hot_url}")
                page.goto(self.hot_url, wait_until='domcontentloaded', timeout=self.page_timeout)

                # 等待页面加载
                time.sleep(3)
                # 等待热搜表格渲染完成（最长 5s），失败则继续尝试解析
                try:
                    page.wait_for_selector('#pl_top_realtimehot table tr', timeout=5000)
                except Exception:
                    self.logger.warning("未找到热搜表格选择器，尝试继续解析...")

                # 解析热榜数据
                items = self._parse_hot_list(page)

                # 关闭浏览器
                browser.close()

                self.logger.info(f"微博热榜: 获取 {len(items)} 条数据")

        except PlaywrightTimeout:
            self.logger.error("页面加载超时")
        except Exception as e:
            self.logger.error(f"获取微博热榜失败: {e}")

        return items

    def _parse_hot_list(self, page) -> List[TrendingItem]:
        """解析微博热榜页面"""
        items = []

        try:
            # 获取热搜表格中的所有行
            rows = page.query_selector_all('#pl_top_realtimehot table tr')

            self.logger.info(f"找到 {len(rows)} 行数据")

            for idx, row in enumerate(rows[1:], 1):  # 跳过表头
                try:
                    # 获取所有单元格
                    tds = row.query_selector_all('td')
                    if len(tds) < 2:
                        continue

                    # 获取排名：优先取单元格纯文本，其次 <i>，最后用循环下标兜底
                    rank_text = tds[0].inner_text().strip()
                    rank = rank_text if rank_text.isdigit() else str(idx)

                    # 获取标题和链接
                    title_elem = tds[1].query_selector('a')
                    if not title_elem:
                        continue

                    title = title_elem.inner_text().strip()
                    url = title_elem.get_attribute('href') or ''
                    if url.startswith('/'):
                        url = f"https://s.weibo.com{url}"

                    # 获取热度（支持"万"单位）
                    hot_score = 0.0
                    hot_elem = tds[1].query_selector('span')
                    if hot_elem:
                        hot_text = hot_elem.inner_text().strip()
                        hot_score = self._parse_hot_score(hot_text)

                    # 获取标签（热、新、沸、爆等）
                    tag_elem = tds[1].query_selector('i')
                    tag = tag_elem.inner_text().strip() if tag_elem else ''

                    if title and url:
                        item = TrendingItem(
                            source=self.name,
                            title=title,
                            url=url,
                            author=None,
                            description=None,
                            hot_score=hot_score,
                            category='hot',
                            extra={
                                'rank': rank,
                                'tag': tag,
                            }
                        )
                        if self.validate_item(item):
                            items.append(item)

                except Exception as e:
                    self.logger.warning(f"解析热榜条目失败: {e}")
                    continue

            # 限制数量
            limit = self.config.get('limit', 50)
            items = items[:limit]

        except Exception as e:
            self.logger.error(f"解析热榜页面失败: {e}")

        return items

    def _parse_hot_score(self, text: str) -> float:
        """解析热度文本（支持"万"单位，与知乎/抖音保持一致）"""
        if not text:
            return 0.0
        try:
            # 优先匹配 "X 万" 格式
            match = re.search(r'(\d+(?:\.\d+)?)\s*万', text)
            if match:
                return float(match.group(1)) * 10000
            # 再匹配纯数字
            match = re.search(r'(\d+(?:\.\d+)?)', text)
            if match:
                return float(match.group(1))
        except (ValueError, AttributeError):
            pass
        return 0.0


def main():
    """主函数"""
    print("🚀 开始获取微博热榜...")

    fetcher = WeiboHotFetcher()
    items = fetcher.fetch()

    print(f"\n✅ 获取成功: {len(items)} 条数据")
    print("\n前10条数据:")
    for i, item in enumerate(items[:10], 1):
        rank = item.extra.get('rank', '-')
        tag = item.extra.get('tag', '')
        print(f"{i}. [{rank}] {item.title[:50]}... {tag}")
        print(f"   热度: {item.hot_score:,.0f}")
        print()


if __name__ == "__main__":
    main()
