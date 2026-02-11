"""
GitHub热门数据获取器
直接爬取 GitHub Trending 页面获取真正的本周热门项目
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
from bs4 import BeautifulSoup
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, SOURCE_URLS, REQUESTS, PROXY
from src.utils import get_logger, save_json


class GitHubTrendingFetcher:
    """GitHub热门数据获取器"""

    def __init__(self, logger=None):
        self.base_url = "https://github.com"
        self.trending_url = SOURCE_URLS['github_trending']
        self.session = requests.Session()
        
        # 更真实的浏览器请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        })
        self.logger = logger or get_logger('github_trending')
        self.config = DATA_SOURCES['github']
        self.max_retries = 3
        self.retry_delay = 5

    def fetch_trending_page(self, language: str = "", since: str = "weekly") -> BeautifulSoup:
        """
        爬取 GitHub Trending 页面
        language: 编程语言，如 "python", "javascript", "" 表示所有语言
        since: 时间周期，"daily", "weekly", "monthly"
        """
        url = self.trending_url
        params = {}

        if language:
            url = f"{self.trending_url}/{language}"

        if since:
            params['since'] = since

        # 添加随机延迟，模拟人类行为
        delay = random.uniform(2, 5)
        self.logger.info(f"等待 {delay:.1f} 秒后请求...")
        time.sleep(delay)

        # 重试机制
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"请求: {url}?since={since} (尝试 {attempt + 1}/{self.max_retries})")
                
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
                soup = BeautifulSoup(response.text, 'html.parser')
                return soup
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1) + random.uniform(1, 3)
                    self.logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"获取Trending页面失败，已重试 {self.max_retries} 次: {e}")
                    return None
            except Exception as e:
                self.logger.error(f"获取Trending页面失败: {e}")
                return None

    def parse_repos(self, soup: BeautifulSoup, limit: int = 20) -> List[Dict]:
        """解析 Trending 页面中的仓库信息"""
        repos = []

        # 查找所有仓库条目
        repo_articles = soup.find_all('article', class_='Box-row')

        for article in repo_articles[:limit]:
            try:
                # 获取仓库名称和链接
                title_element = article.find('h2', class_='h3 lh-condensed')
                if not title_element:
                    continue

                link_element = title_element.find('a')
                if not link_element:
                    continue

                full_name = link_element.get('href', '').lstrip('/')
                repo_url = f"{self.base_url}{link_element.get('href', '')}"

                # 获取描述
                desc_element = article.find('p', class_='col-9')
                description = desc_element.get_text(strip=True) if desc_element else ''

                # 获取编程语言
                language_element = article.find('span', itemprop='programmingLanguage')
                language = language_element.get_text(strip=True) if language_element else 'Unknown'

                # 获取 stars 数量
                stars_element = article.find('a', href=lambda x: x and '/stargazers' in x)
                stars = 0
                if stars_element:
                    stars_text = stars_element.get_text(strip=True)
                    stars = self.parse_number(stars_text)

                # 获取 forks 数量
                forks_element = article.find('a', href=lambda x: x and '/forks' in x)
                forks = 0
                if forks_element:
                    forks_text = forks_element.get_text(strip=True)
                    forks = self.parse_number(forks_text)

                # 获取本周新增 stars
                current_stars_element = article.find('span', class_='d-inline-block float-sm-right')
                current_period_stars = 0
                if current_stars_element:
                    stars_text = current_stars_element.get_text(strip=True)
                    match = re.search(r'(\d+(?:,\d+)*)\s+stars', stars_text)
                    if match:
                        current_period_stars = int(match.group(1).replace(',', ''))

                # 获取作者/贡献者头像
                built_by = []
                avatars = article.find_all('img', class_='avatar mb-1')
                for avatar in avatars:
                    built_by.append({
                        'username': avatar.get('alt', ''),
                        'avatar': avatar.get('src', '')
                    })

                repos.append({
                    'full_name': full_name,
                    'url': repo_url,
                    'description': description,
                    'language': language,
                    'stars': stars,
                    'forks': forks,
                    'currentPeriodStars': current_period_stars,
                    'builtBy': built_by,
                    'updatedAt': ''
                })

            except Exception as e:
                self.logger.warning(f"解析仓库失败: {e}")
                continue

        return repos

    def parse_number(self, text: str) -> int:
        """解析数字字符串，如 '1.2k' -> 1200"""
        text = text.strip().lower()

        if 'k' in text:
            num = float(text.replace('k', '').replace(',', ''))
            return int(num * 1000)

        return int(text.replace(',', ''))

    def get_trending_repos(self, per_page: int = None) -> List[Dict]:
        """获取本周热门仓库（所有语言）"""
        per_page = per_page or self.config['limit']
        self.logger.info("获取本周热门仓库...")

        soup = self.fetch_trending_page(language="", since=self.config['since'])
        if not soup:
            return []

        repos = self.parse_repos(soup, limit=per_page)
        self.logger.info(f"获取到 {len(repos)} 个热门仓库")
        return repos

    def get_ai_repos(self, per_page: int = None) -> List[Dict]:
        """获取AI领域热门项目"""
        per_page = per_page or self.config['limit']
        self.logger.info("获取AI领域热门项目...")

        # 获取 Python 热门项目（AI项目多为Python）
        soup = self.fetch_trending_page(language="python", since=self.config['since'])
        if not soup:
            return []

        python_repos = self.parse_repos(soup, limit=50)

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

        ai_repos = []
        for repo in python_repos:
            name = repo.get('full_name', '').lower()
            description = repo.get('description', '').lower()

            is_ai = any(keyword in name or keyword in description for keyword in ai_keywords)
            if is_ai:
                ai_repos.append(repo)

        self.logger.info(f"从 {len(python_repos)} 个Python项目中筛选出 {len(ai_repos)} 个AI项目")

        # 如果AI项目不够，补充更多Python项目
        if len(ai_repos) < per_page:
            additional = per_page - len(ai_repos)
            for repo in python_repos:
                if repo not in ai_repos and len(ai_repos) < per_page:
                    ai_repos.append(repo)
                if len(ai_repos) >= per_page:
                    break

        return ai_repos[:per_page]

    def save_json(self, repos: List[Dict], filename: str, repo_type: str = "repos") -> None:
        """保存JSON数据"""
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            repo_type: []
        }

        for idx, repo in enumerate(repos, 1):
            data[repo_type].append({
                "rank": idx,
                "name": repo.get('full_name', 'N/A'),
                "url": repo.get('url', '#'),
                "description": repo.get('description') or '',
                "stars": repo.get('stars', 0),
                "forks": repo.get('forks', 0),
                "language": repo.get('language', 'Unknown'),
                "current_period_stars": repo.get('currentPeriodStars', 0),
                "built_by": repo.get('builtBy', []),
                "updated_at": repo.get('updatedAt', '')
            })

        filepath = Path(filename)
        save_json(data, filepath)
        self.logger.info(f"数据已保存: {filepath}")

    def fetch_all(self, output_dir: Path) -> Dict[str, Path]:
        """获取所有GitHub数据并保存"""
        self.logger.info("开始获取GitHub热门数据...")

        result = {}

        # 获取本周热门仓库
        trending_repos = self.get_trending_repos(per_page=50)
        if trending_repos:
            # 按本周新增 stars 排序
            sorted_by_growth = sorted(trending_repos, key=lambda x: x.get('currentPeriodStars', 0), reverse=True)
            top_growth = sorted_by_growth[:self.config['limit']]

            # 按总stars排序
            sorted_by_total = sorted(trending_repos, key=lambda x: x.get('stars', 0), reverse=True)
            top_total = sorted_by_total[:self.config['limit']]

            # 保存数据
            growth_file = output_dir / 'github_weekly_growth.json'
            trending_file = output_dir / 'github_trending.json'

            self.save_json(top_growth, growth_file)
            self.save_json(top_total, trending_file)

            result['github_weekly_growth'] = growth_file
            result['github_trending'] = trending_file
        else:
            self.logger.error("获取热门仓库失败")

        # 获取AI项目
        ai_repos = self.get_ai_repos(per_page=self.config['limit'])
        if ai_repos:
            ai_file = output_dir / 'ai_trending.json'
            self.save_json(ai_repos, ai_file)
            result['ai_trending'] = ai_file
        else:
            self.logger.error("获取AI项目失败")

        return result


def main():
    """主函数"""
    print("🚀 开始获取GitHub热门数据...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from ..config import REPORTS_DIR
    fetcher = GitHubTrendingFetcher()

    # 获取所有数据
    result = fetcher.fetch_all(REPORTS_DIR)

    print("🎉 GitHub数据获取完成!")
    return result


if __name__ == "__main__":
    main()