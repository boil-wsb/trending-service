"""
GitHub热门数据获取器
支持两种数据源：
1. GitHub Trending 页面 (今日趋势) - 用于普通 GitHub 按钮
2. GitHub Search API (本周增长) - 用于 GitHub本周增长 按钮
"""

import sys
import requests
import json
import os
import time
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, SOURCE_URLS, REQUESTS, PROXY
from src.utils import get_logger, save_json
from .base import BaseFetcher, TrendingItem


class GitHubTrendingFetcher(BaseFetcher):
    """GitHub热门数据获取器"""
    
    name = "github"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.base_url = "https://github.com"
        self.trending_url = "https://github.com/trending"
        self.api_url = "https://api.github.com/search/repositories"
        self.session = requests.Session()
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # 如果配置了 GitHub Token，添加到请求头（提高API速率限制）
        github_token = os.getenv('GITHUB_TOKEN')
        if github_token:
            self.session.headers.update({'Authorization': f'token {github_token}'})
        
        self.logger = logger or get_logger('github_trending')
        self.config = config or DATA_SOURCES['github']
        self.max_retries = 3
        self.retry_delay = 5

    def get_date_range(self, days: int = 7) -> str:
        """
        获取日期范围字符串（ISO 8601格式）
        返回格式: 2026-03-05 (当日 - days天)
        """
        date = datetime.now() - timedelta(days=days)
        return date.strftime('%Y-%m-%d')

    def fetch_trending_from_page(self, language: str = "", since: str = "daily", limit: int = 20) -> List[Dict]:
        """
        从 GitHub Trending 页面爬取数据
        
        Args:
            language: 编程语言筛选，如 "python", "javascript", "" 表示所有语言
            since: 时间周期，"daily", "weekly", "monthly"
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 仓库列表
        """
        url = self.trending_url
        params = {}
        
        if language:
            url = f"{self.trending_url}/{language}"
        if since:
            params['since'] = since
            
        # 添加随机延迟
        delay = random.uniform(2, 5)
        self.logger.info(f"等待 {delay:.1f} 秒后请求...")
        time.sleep(delay)
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"请求 GitHub Trending 页面: {url} (尝试 {attempt + 1}/{self.max_retries})")
                
                # 设置代理
                proxies = None
                if PROXY.get('enabled'):
                    proxies = {
                        'http': PROXY.get('http', ''),
                        'https': PROXY.get('https', '')
                    }
                
                response = self.session.get(
                    url,
                    params=params,
                    timeout=REQUESTS['timeout'],
                    proxies=proxies
                )
                response.raise_for_status()
                
                # 解析HTML
                repos = self._parse_trending_page(response.text, limit)
                self.logger.info(f"从 Trending 页面解析到 {len(repos)} 个仓库")
                return repos
                
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1) + random.uniform(1, 3)
                    self.logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"获取Trending页面失败，已重试 {self.max_retries} 次: {e}")
                    return []
            except Exception as e:
                self.logger.error(f"解析Trending页面失败: {e}")
                return []
        
        return []
    
    def _parse_trending_page(self, html: str, limit: int = 20) -> List[Dict]:
        """
        解析 GitHub Trending 页面 HTML
        
        Args:
            html: 页面HTML内容
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 解析后的仓库列表
        """
        repos = []
        
        # 使用正则表达式解析HTML
        # 查找所有仓库条目
        article_pattern = r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>'
        articles = re.findall(article_pattern, html, re.DOTALL)
        
        for article in articles[:limit]:
            try:
                # 获取仓库名称和链接
                title_match = re.search(r'<h2[^>]*class="[^"]*h3[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', article, re.DOTALL)
                if not title_match:
                    continue
                    
                href = title_match.group(1).strip()
                full_name = href.lstrip('/')
                repo_url = f"{self.base_url}{href}"
                
                # 获取描述
                desc_match = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', article, re.DOTALL)
                description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else ''
                
                # 获取编程语言
                lang_match = re.search(r'<span[^>]*itemprop="programmingLanguage"[^>]*>(.*?)</span>', article)
                language = lang_match.group(1).strip() if lang_match else 'Unknown'
                
                # 获取 stars 数量
                stars_match = re.search(r'<a[^>]*href="[^"]*stargazers[^"]*"[^>]*>(.*?)</a>', article, re.DOTALL)
                stars = 0
                if stars_match:
                    stars_text = re.sub(r'<[^>]+>', '', stars_match.group(1)).strip()
                    stars = self._parse_number(stars_text)
                
                # 获取 forks 数量
                forks_match = re.search(r'<a[^>]*href="[^"]*forks[^"]*"[^>]*>(.*?)</a>', article, re.DOTALL)
                forks = 0
                if forks_match:
                    forks_text = re.sub(r'<[^>]+>', '', forks_match.group(1)).strip()
                    forks = self._parse_number(forks_text)
                
                # 获取今日新增 stars
                today_stars_match = re.search(r'<span[^>]*class="[^"]*d-inline-block[^"]*float-sm-right[^"]*"[^>]*>(.*?)</span>', article, re.DOTALL)
                today_stars = 0
                if today_stars_match:
                    stars_text = re.sub(r'<[^>]+>', '', today_stars_match.group(1)).strip()
                    match = re.search(r'(\d+(?:,\d+)*)\s*stars?', stars_text)
                    if match:
                        today_stars = int(match.group(1).replace(',', ''))
                
                # 获取作者头像
                built_by = []
                avatar_matches = re.findall(r'<img[^>]*class="[^"]*avatar[^"]*"[^>]*alt="([^"]*)"[^>]*src="([^"]*)"', article)
                for username, avatar_url in avatar_matches:
                    built_by.append({
                        'username': username,
                        'avatar': avatar_url
                    })
                
                repos.append({
                    'full_name': full_name,
                    'url': repo_url,
                    'description': description,
                    'language': language,
                    'stars': stars,
                    'forks': forks,
                    'today_stars': today_stars,
                    'builtBy': built_by
                })
                
            except Exception as e:
                self.logger.warning(f"解析仓库失败: {e}")
                continue
        
        return repos
    
    def _parse_number(self, text: str) -> int:
        """解析数字字符串，如 '1.2k' -> 1200"""
        text = text.strip().lower()
        
        if 'k' in text:
            num = float(text.replace('k', '').replace(',', ''))
            return int(num * 1000)
        
        return int(text.replace(',', ''))

    def fetch_repositories_from_api(self, language: str = None, days: int = 7, limit: int = 30) -> List[Dict]:
        """
        使用 GitHub Search API 获取最近创建的仓库
        
        Args:
            language: 编程语言筛选，如 "python", "javascript"
            days: 查询最近多少天创建的仓库
            limit: 返回结果数量限制
        """
        # 计算日期
        date_threshold = self.get_date_range(days)
        
        # 构建查询参数
        # q=created:>2026-03-05&sort=stars&order=desc
        query = f"created:>{date_threshold}"
        if language:
            query += f" language:{language}"
        
        params = {
            'q': query,
            'sort': 'stars',
            'order': 'desc',
            'per_page': min(limit, 100)  # GitHub API 最大每页100
        }
        
        # 添加随机延迟
        delay = random.uniform(1, 3)
        self.logger.info(f"等待 {delay:.1f} 秒后请求...")
        time.sleep(delay)
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"请求 GitHub API: {self.api_url} (尝试 {attempt + 1}/{self.max_retries})")
                self.logger.info(f"查询条件: {query}")
                
                # 设置代理
                proxies = None
                if PROXY.get('enabled'):
                    proxies = {
                        'http': PROXY.get('http', ''),
                        'https': PROXY.get('https', '')
                    }
                
                response = self.session.get(
                    self.api_url,
                    params=params,
                    timeout=REQUESTS['timeout'],
                    proxies=proxies
                )
                
                # 检查速率限制
                if response.status_code == 403:
                    remaining = response.headers.get('X-RateLimit-Remaining')
                    reset_time = response.headers.get('X-RateLimit-Reset')
                    if remaining == '0' and reset_time:
                        reset_datetime = datetime.fromtimestamp(int(reset_time))
                        self.logger.warning(f"GitHub API 速率限制已达上限，将在 {reset_datetime} 重置")
                        self.logger.warning("建议设置 GITHUB_TOKEN 环境变量以提高限制")
                
                response.raise_for_status()
                data = response.json()
                
                repos = data.get('items', [])
                self.logger.info(f"GitHub API 返回 {len(repos)} 个仓库")
                
                return repos
                
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1) + random.uniform(1, 3)
                    self.logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"GitHub API 请求失败，已重试 {self.max_retries} 次: {e}")
                    return []
            except Exception as e:
                self.logger.error(f"GitHub API 请求失败: {e}")
                return []
        
        return []

    def parse_api_repos(self, repos: List[Dict], limit: int = 20) -> List[Dict]:
        """
        解析 GitHub API 返回的仓库数据
        
        Args:
            repos: API 返回的原始仓库列表
            limit: 返回结果数量限制
        """
        parsed_repos = []
        
        for repo in repos[:limit]:
            try:
                # 获取所有者信息
                owner = repo.get('owner', {})
                owner_info = {
                    'username': owner.get('login', ''),
                    'avatar': owner.get('avatar_url', '')
                }
                
                parsed_repo = {
                    'full_name': repo.get('full_name', ''),
                    'url': repo.get('html_url', ''),
                    'description': repo.get('description', ''),
                    'language': repo.get('language', 'Unknown'),
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'currentPeriodStars': repo.get('stargazers_count', 0),  # 使用总星标作为热度
                    'builtBy': [owner_info],
                    'created_at': repo.get('created_at', ''),
                    'updated_at': repo.get('updated_at', ''),
                    'pushed_at': repo.get('pushed_at', '')
                }
                
                parsed_repos.append(parsed_repo)
                
            except Exception as e:
                self.logger.warning(f"解析仓库失败: {e}")
                continue
        
        return parsed_repos

    def fetch(self) -> List[TrendingItem]:
        """
        获取GitHub热门数据（实现基类方法）
        从 GitHub Trending 页面获取今日热门仓库
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        self.logger.info("开始获取GitHub热门数据（Trending页面）...")
        
        items = []
        limit = self.config.get('limit', 20)
        
        # 从 GitHub Trending 页面获取今日热门
        repos = self.fetch_trending_from_page(language="", since="daily", limit=limit)
        
        for repo in repos:
            item = TrendingItem(
                source=self.name,
                title=repo.get('full_name', ''),
                url=repo.get('url', ''),
                author=repo.get('builtBy')[0].get('username') if repo.get('builtBy') else None,
                description=repo.get('description'),
                hot_score=float(repo.get('today_stars', 0)),  # 使用今日新增星标作为热度
                category=repo.get('language'),
                extra={
                    'stars': repo.get('stars', 0),
                    'forks': repo.get('forks', 0),
                    'language': repo.get('language', 'Unknown'),
                    'built_by': repo.get('builtBy', []),
                    'today_stars': repo.get('today_stars', 0)
                }
            )
            items.append(item)
        
        self.logger.info(f"GitHub: 从Trending页面获取 {len(items)} 条数据")
        return items

    def get_ai_repos(self) -> List[TrendingItem]:
        """获取AI领域热门项目"""
        self.logger.info("获取AI领域热门项目...")

        # 获取 Python 语言最近创建的仓库
        days = self.config.get('days', 7)
        limit = 50  # 多获取一些用于筛选
        
        raw_repos = self.fetch_repositories_from_api(language="python", days=days, limit=limit)
        if not raw_repos:
            return []

        repos = self.parse_api_repos(raw_repos, limit=limit)

        # AI关键词
        ai_keywords = [
            'ai', 'artificial', 'intelligence', 'machine', 'learning', 'ml',
            'deep', 'neural', 'network', 'tensorflow', 'pytorch', 'keras',
            'llm', 'gpt', 'chatgpt', 'claude', 'transformer', 'nlp',
            'computer', 'vision', 'cv', 'reinforcement', 'diffusion',
            'stable', 'diffusion', 'openai', 'anthropic', 'hugging',
            'langchain', 'agent', 'rag', 'embedding', 'vector', 'model',
            'inference', 'training', 'fine-tune', 'finetune', 'whisper',
            'segment', 'controlnet', 'midjourney', 'dalle', 'stable-diffusion',
            'autogpt', 'babyagi', 'chat', 'bot', 'copilot', 'assistant'
        ]

        ai_items = []
        for repo in repos:
            name = repo.get('full_name', '').lower()
            description = (repo.get('description') or '').lower()

            is_ai = any(keyword in name or keyword in description for keyword in ai_keywords)
            if is_ai:
                item = TrendingItem(
                    source=f"{self.name}_ai",
                    title=repo.get('full_name', ''),
                    url=repo.get('url', ''),
                    author=repo.get('builtBy')[0].get('username') if repo.get('builtBy') else None,
                    description=repo.get('description'),
                    hot_score=float(repo.get('stars', 0)),
                    category='AI',
                    extra={
                        'stars': repo.get('stars', 0),
                        'forks': repo.get('forks', 0),
                        'language': repo.get('language', 'Unknown'),
                        'built_by': repo.get('builtBy', []),
                        'created_at': repo.get('created_at', ''),
                        'updated_at': repo.get('updated_at', '')
                    }
                )
                ai_items.append(item)

        self.logger.info(f"从 {len(repos)} 个Python项目中筛选出 {len(ai_items)} 个AI项目")

        # 如果AI项目不够，补充更多Python项目
        target_limit = self.config.get('limit', 20)
        if len(ai_items) < target_limit:
            for repo in repos:
                if len(ai_items) >= target_limit:
                    break
                # 检查是否已经在列表中
                repo_name = repo.get('full_name', '')
                if not any(item.title == repo_name for item in ai_items):
                    item = TrendingItem(
                        source=f"{self.name}_ai",
                        title=repo.get('full_name', ''),
                        url=repo.get('url', ''),
                        author=repo.get('builtBy')[0].get('username') if repo.get('builtBy') else None,
                        description=repo.get('description'),
                        hot_score=float(repo.get('stars', 0)),
                        category=repo.get('language'),
                        extra={
                            'stars': repo.get('stars', 0),
                            'forks': repo.get('forks', 0),
                            'language': repo.get('language', 'Unknown'),
                            'built_by': repo.get('builtBy', []),
                            'created_at': repo.get('created_at', ''),
                            'updated_at': repo.get('updated_at', '')
                        }
                    )
                    ai_items.append(item)

        return ai_items[:target_limit]

    def fetch_all(self) -> List[TrendingItem]:
        """获取所有GitHub数据"""
        self.logger.info("开始获取GitHub热门数据...")

        all_items = []

        # 获取本周热门仓库
        trending_items = self.fetch()
        all_items.extend(trending_items)

        # 获取AI项目
        ai_items = self.get_ai_repos()
        all_items.extend(ai_items)

        self.logger.info(f"GitHub: 总共获取 {len(all_items)} 条数据")
        return all_items


def main():
    """主函数"""
    print("🚀 开始获取GitHub热门数据...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    fetcher = GitHubTrendingFetcher()

    # 获取所有数据
    items = fetcher.fetch_all()

    print(f"🎉 GitHub数据获取完成! 共 {len(items)} 条")
    
    # 显示前5条
    for i, item in enumerate(items[:5], 1):
        print(f"{i}. {item.title} (热度: {item.hot_score})")
    
    return items


if __name__ == "__main__":
    main()
