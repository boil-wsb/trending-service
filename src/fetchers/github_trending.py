"""
GitHub热门数据获取器
使用 GitHub Search API 获取最近7天创建的仓库，按星标排序
"""

import sys
import io
import requests
import json
import os
import re
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, SOURCE_URLS, REQUESTS, PROXY
from src.utils import get_logger, save_json
from .base import BaseFetcher, TrendingItem


class GitHubTrendingFetcher(BaseFetcher):
    """GitHub热门数据获取器 - 使用 Search API"""
    
    name = "github"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.base_url = "https://github.com"
        self.api_url = "https://api.github.com/search/repositories"
        self.session = requests.Session()
        
        # GitHub API 请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.github.v3+json',
        })
        
        # 如果配置了 GitHub Token，添加到请求头（提高速率限制）
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
        使用 Search API 获取最近7天创建的仓库，按星标排序
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        self.logger.info("开始获取GitHub热门数据（Search API）...")
        
        items = []
        
        # 获取最近7天创建的仓库，按星标排序
        days = self.config.get('days', 7)  # 默认查询最近7天
        limit = self.config.get('limit', 20)
        
        raw_repos = self.fetch_repositories_from_api(language=None, days=days, limit=limit)
        if raw_repos:
            repos = self.parse_api_repos(raw_repos, limit=limit)
            for repo in repos:
                item = TrendingItem(
                    source=self.name,
                    title=repo.get('full_name', ''),
                    url=repo.get('url', ''),
                    author=repo.get('builtBy')[0].get('username') if repo.get('builtBy') else None,
                    description=repo.get('description'),
                    hot_score=float(repo.get('stars', 0)),  # 使用总星标作为热度
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
                items.append(item)
        
        self.logger.info(f"GitHub: 获取 {len(items)} 条数据")
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
