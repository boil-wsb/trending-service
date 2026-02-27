"""
arXiv论文数据获取器
获取arXiv最新论文信息
"""

import sys
import io

# 设置标准输出编码为UTF-8（仅在交互式环境中）
if hasattr(sys.stdout, 'buffer') and not sys.stdout.closed:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

import requests
import re
from typing import List, Dict
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger, save_json
from .base import BaseFetcher, TrendingItem


class ArxivPapersFetcher(BaseFetcher):
    """arXiv论文数据获取器"""
    
    name = "arxiv"

    def __init__(self, config: Dict = None, logger=None):
        super().__init__(config, logger)
        self.base_url = "http://export.arxiv.org/api/query"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': REQUESTS['user_agent'],
            'Accept': 'application/xml',
        })
        self.logger = logger or get_logger('arxiv_papers')
        self.config = config or DATA_SOURCES['arxiv']

    def fetch(self) -> List[TrendingItem]:
        """
        获取arXiv论文（实现基类方法）
        
        Returns:
            List[TrendingItem]: 热点数据列表
        """
        limit = self.config.get('limit', 20)
        categories = self.config.get('categories', ['cs.AI', 'cs.LG'])
        
        self.logger.info(f"获取arXiv论文 (categories={categories}, limit={limit})...")

        # 构建查询
        category_query = ' OR '.join([f'cat:{cat}' for cat in categories])
        params = {
            'search_query': category_query,
            'start': 0,
            'max_results': limit,
            'sortBy': 'lastUpdatedDate',
            'sortOrder': 'descending'
        }

        try:
            response = self.session.get(self.base_url, params=params, timeout=REQUESTS['timeout'])
            response.raise_for_status()

            items = self._parse_response(response.text)
            self.logger.info(f"arXiv: 获取 {len(items)} 条数据")
            return items

        except Exception as e:
            self.logger.error(f"获取arXiv论文失败: {e}")
            return []

    def _parse_response(self, xml_text: str) -> List[TrendingItem]:
        """解析arXiv API响应"""
        items = []

        # 使用正则表达式提取论文信息
        entries = re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL)

        for entry in entries:
            try:
                # 提取ID
                id_match = re.search(r'<id>(.*?)</id>', entry)
                paper_id = id_match.group(1).split('/')[-1] if id_match else ''

                # 提取标题
                title_match = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                title = title_match.group(1).strip().replace('\n', ' ') if title_match else ''

                # 提取摘要
                summary_match = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                summary = summary_match.group(1).strip().replace('\n', ' ') if summary_match else ''

                # 提取作者
                authors = []
                author_matches = re.findall(r'<name>(.*?)</name>', entry)
                for author in author_matches:
                    authors.append(author.strip())

                # 提取发布日期
                published_match = re.search(r'<published>(.*?)</published>', entry)
                published = published_match.group(1) if published_match else ''

                # 提取更新日期
                updated_match = re.search(r'<updated>(.*?)</updated>', entry)
                updated = updated_match.group(1) if updated_match else ''

                # 提取分类
                category_match = re.search(r'<category term="(.*?)"', entry)
                category = category_match.group(1) if category_match else ''

                # 构建URL
                url = f"https://arxiv.org/abs/{paper_id}"

                item = TrendingItem(
                    source=self.name,
                    title=title,
                    url=url,
                    author=', '.join(authors[:3]) if authors else None,  # 只取前3个作者
                    description=summary,  # 完整描述
                    hot_score=None,  # arXiv 没有热度分数
                    category=category,
                    extra={
                        'paper_id': paper_id,
                        'authors': authors,
                        'published': published,
                        'updated': updated,
                        'category': category
                    }
                )
                items.append(item)

            except Exception as e:
                self.logger.warning(f"解析论文失败: {e}")
                continue

        return items

    def fetch_papers(self, categories: List[str] = None, limit: int = None) -> List[Dict]:
        """
        获取arXiv论文（旧接口，保留兼容性）

        Args:
            categories: 论文分类列表
            limit: 返回论文数量限制

        Returns:
            论文列表
        """
        items = self.fetch()
        return [
            {
                'id': item.extra.get('paper_id', ''),
                'title': item.title,
                'url': item.url,
                'summary': item.description,
                'authors': item.extra.get('authors', []),
                'published': item.extra.get('published', ''),
                'updated': item.extra.get('updated', ''),
                'category': item.category
            }
            for item in items
        ]

    def save_json(self, papers: List[Dict], filepath: Path) -> None:
        """保存论文数据到JSON文件"""
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "papers": []
        }

        for idx, paper in enumerate(papers, 1):
            data["papers"].append({
                "rank": idx,
                "id": paper.get('id', ''),
                "title": paper.get('title', ''),
                "url": paper.get('url', '#'),
                "summary": paper.get('summary', ''),
                "authors": paper.get('authors', []),
                "published": paper.get('published', ''),
                "updated": paper.get('updated', ''),
                "category": paper.get('category', '')
            })

        save_json(data, filepath)
        self.logger.info(f"数据已保存: {filepath}")

    def fetch_all(self, output_dir: Path) -> Dict[str, Path]:
        """获取所有arXiv数据并保存"""
        self.logger.info("开始获取arXiv论文数据...")

        result = {}
        
        # 定义分类映射
        categories = {
            'biology': ['q-bio', 'q-bio.CB', 'q-bio.GN', 'q-bio.MN', 'q-bio.NC', 'q-bio.OT', 'q-bio.PE', 'q-bio.QM', 'q-bio.SC', 'q-bio.TO'],
            'computer_ai': ['cs.AI', 'cs.LG', 'cs.CV', 'cs.NE', 'cs.RO']
        }
        
        # 获取生物分类论文
        biology_papers = self.fetch_papers(categories=categories['biology'])
        if biology_papers:
            filepath = output_dir / 'arxiv_biology.json'
            self.save_json(biology_papers, filepath)
            result['arxiv_biology'] = filepath
        else:
            self.logger.error("获取生物分类论文失败")
        
        # 获取计算机-人工智能分类论文
        computer_ai_papers = self.fetch_papers(categories=categories['computer_ai'])
        if computer_ai_papers:
            filepath = output_dir / 'arxiv_computer_ai.json'
            self.save_json(computer_ai_papers, filepath)
            result['arxiv_computer_ai'] = filepath
        else:
            self.logger.error("获取计算机-人工智能分类论文失败")

        return result


def main():
    """主函数"""
    print("🚀 开始获取arXiv论文数据...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from ..config import REPORTS_DIR
    fetcher = ArxivPapersFetcher()

    result = fetcher.fetch_all(REPORTS_DIR)

    print("🎉 arXiv数据获取完成!")
    return result


if __name__ == "__main__":
    main()
