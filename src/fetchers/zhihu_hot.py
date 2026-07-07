"""
知乎热榜获取器
使用 Playwright 无头浏览器爬取知乎热榜
"""

import os
import sys
import json
import re
import time
from typing import List, Dict, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS, SOURCE_URLS, PROJECT_ROOT
from src.utils import get_logger
from .base import BaseFetcher, TrendingItem

# 尝试导入 Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class ZhihuHotFetcher(BaseFetcher):
    """知乎热榜获取器（使用 Playwright 无头浏览器）"""

    name = "zhihu"
    HOT_URL = "https://www.zhihu.com/hot"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.logger = logger or get_logger(self.name)
        self.config = config or DATA_SOURCES.get(self.name, {'limit': 50})
        self.cookies_file = PROJECT_ROOT / 'data' / 'zhihu_cookies.json'
        # P2: 统一从 config 读取 UA/超时/URL，支持热加载与统一管理
        self.user_agent = REQUESTS.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        self.page_timeout = int(REQUESTS.get('timeout', 60)) * 1000  # 秒 -> 毫秒
        self.hot_url = SOURCE_URLS.get('zhihu_hot', self.HOT_URL)

    def fetch(self) -> List[TrendingItem]:
        """
        获取知乎热榜

        Returns:
            List[TrendingItem]: 热点数据列表
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.error("Playwright 未安装，无法获取知乎热榜")
            return []

        self.logger.info("开始获取知乎热榜...")

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

                # 加载 Cookie（如果存在）
                if self.cookies_file.exists():
                    cookies = self._load_cookies()
                    if cookies:
                        context.add_cookies(cookies)
                        self.logger.info("已加载 Cookie")

                # 创建页面
                page = context.new_page()

                # 访问知乎热榜
                self.logger.info(f"访问: {self.hot_url}")
                page.goto(self.hot_url, wait_until='domcontentloaded', timeout=self.page_timeout)

                # 等待页面加载完成
                time.sleep(3)

                # 尝试多种选择器等待热榜加载
                selectors = [
                    '[data-za-detail-view-path-module="HotList"]',
                    '.HotList',
                    '.HotList-item',
                    '[class*="HotList"]'
                ]

                hot_list_found = False
                for selector in selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                        self.logger.info(f"找到热榜元素: {selector}")
                        hot_list_found = True
                        break
                    except:
                        continue

                if not hot_list_found:
                    self.logger.warning("未找到热榜元素，尝试继续解析...")

                # 额外等待 JavaScript 渲染
                time.sleep(2)

                # 解析热榜数据
                items = self._parse_hot_list(page)

                # 保存 Cookie（以便下次使用）
                cookies = context.cookies()
                self._save_cookies(cookies)

                # 关闭浏览器
                browser.close()

                self.logger.info(f"知乎热榜: 获取 {len(items)} 条数据")

        except PlaywrightTimeout:
            self.logger.error("页面加载超时")
        except Exception as e:
            self.logger.error(f"获取知乎热榜失败: {e}")

        return items

    def _parse_hot_list(self, page) -> List[TrendingItem]:
        """解析知乎热榜页面"""
        items = []

        try:
            # 获取所有热榜条目（使用正确的 CSS 选择器）
            hot_items = page.query_selector_all('.HotItem')

            self.logger.info(f"找到 {len(hot_items)} 个热榜条目")

            for idx, item_element in enumerate(hot_items, 1):
                try:
                    # 获取排名
                    rank_elem = item_element.query_selector('.HotItem-rank')
                    rank = rank_elem.inner_text().strip() if rank_elem else str(idx)

                    # 获取标题
                    title_elem = item_element.query_selector('.HotItem-title')
                    title = title_elem.inner_text().strip() if title_elem else ''

                    # 获取链接
                    link_elem = item_element.query_selector('a.HotItem-content')
                    if not link_elem:
                        link_elem = item_element.query_selector('a')
                    url = link_elem.get_attribute('href') if link_elem else ''
                    if url and url.startswith('/'):
                        url = f"https://www.zhihu.com{url}"

                    # 获取热度
                    hot_score = 0.0
                    metrics_text = ''  # 预初始化，避免作用域未定义
                    metrics_elem = item_element.query_selector('.HotItem-metrics')
                    if metrics_elem:
                        metrics_text = metrics_elem.inner_text().strip()
                        hot_score = self._parse_hot_score(metrics_text)

                    # 获取描述/摘要
                    description = ''
                    desc_elem = item_element.query_selector('.HotItem-excerpt')
                    if desc_elem:
                        description = desc_elem.inner_text().strip()

                    # 检查是否为商业推广
                    is_commercial = item_element.query_selector('.HotItem-commerce') is not None

                    if title and url:
                        item = TrendingItem(
                            source=self.name,
                            title=title,
                            url=url,
                            author=None,
                            description=description,
                            hot_score=hot_score,
                            category='hot' if not is_commercial else 'commercial',
                            extra={
                                'rank': rank,
                                'metrics': metrics_text if metrics_elem else '',
                                'is_commercial': is_commercial,
                            }
                        )
                        if self.validate_item(item):
                            items.append(item)

                except Exception as e:
                    self.logger.warning(f"解析热榜条目失败: {e}")
                    continue

            # P1: 应用 limit 限制（与其他 fetcher 一致）
            limit = self.config.get('limit', 50)
            items = items[:limit]

        except Exception as e:
            self.logger.error(f"解析热榜页面失败: {e}")

        return items

    def _parse_hot_score(self, text: str) -> float:
        """解析热度文本（优先匹配"X 万"格式，避免误匹配排名数字）"""
        if not text:
            return 0.0
        try:
            # 优先匹配 "X 万" 格式（带单位），避免误匹配排名等其它数字
            match = re.search(r'(\d+(?:\.\d+)?)\s*万', text)
            if match:
                return float(match.group(1)) * 10000
            # 再匹配纯数字（如 "1234 热度"）
            match = re.search(r'(\d+(?:\.\d+)?)', text)
            if match:
                return float(match.group(1))
        except (ValueError, AttributeError):
            pass
        return 0.0

    def _load_cookies(self) -> List[Dict]:
        """加载 Cookie"""
        try:
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"加载 Cookie 失败: {e}")
            return []

    def _save_cookies(self, cookies: List[Dict]):
        """保存 Cookie"""
        try:
            # 确保目录存在
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            self.logger.info("已保存 Cookie")
        except Exception as e:
            self.logger.warning(f"保存 Cookie 失败: {e}")


def main():
    """主函数"""
    print("🚀 开始获取知乎热榜...")

    fetcher = ZhihuHotFetcher()
    items = fetcher.fetch()

    print(f"\n✅ 获取成功: {len(items)} 条数据")
    print("\n前10条数据:")
    for i, item in enumerate(items[:10], 1):
        print(f"{i}. [{item.extra.get('rank', '-')}] {item.title[:50]}...")
        print(f"   热度: {item.hot_score:,.0f}")
        print(f"   链接: {item.url}")
        print()


if __name__ == "__main__":
    main()
