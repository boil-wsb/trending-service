"""
B站热门视频数据获取器
获取B站热门视频信息
"""

import sys
import io
import requests
import json
from typing import List, Dict
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import DATA_SOURCES, REQUESTS
from src.utils import get_logger, save_json


class BilibiliHotFetcher:
    """B站热门视频数据获取器"""

    def __init__(self, logger=None):
        self.base_url = "https://www.bilibili.com"
        self.hot_url = "https://www.bilibili.com/hot"
        self.api_url = "https://api.bilibili.com/x/web-interface/popular"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': REQUESTS['user_agent'],
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.logger = logger or get_logger('bilibili_hot')
        self.config = DATA_SOURCES['bilibili']

    def fetch_hot_videos(self, limit: int = None) -> List[Dict]:
        """
        获取B站热门视频

        Args:
            limit: 返回视频数量限制

        Returns:
            视频列表
        """
        limit = limit or self.config['limit']
        self.logger.info(f"获取B站热门视频 (limit={limit})...")

        params = {
            'ps': limit,
            'pn': 1
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=REQUESTS['timeout'])
            response.raise_for_status()
            data = response.json()

            if data.get('code') != 0:
                self.logger.error(f"API返回错误: {data.get('message')}")
                return []

            videos = []
            for item in data.get('data', {}).get('list', []):
                videos.append({
                    'title': item.get('title', ''),
                    'url': f"https://www.bilibili.com/video/{item.get('bvid', '')}",
                    'description': item.get('desc', ''),
                    'view': item.get('stat', {}).get('view', 0),
                    'danmaku': item.get('stat', {}).get('danmaku', 0),
                    'reply': item.get('stat', {}).get('reply', 0),
                    'favorite': item.get('stat', {}).get('favorite', 0),
                    'coin': item.get('stat', {}).get('coin', 0),
                    'share': item.get('stat', {}).get('share', 0),
                    'like': item.get('stat', {}).get('like', 0),
                    'duration': item.get('duration', 0),
                    'owner': item.get('owner', {}).get('name', ''),
                    'pic': item.get('pic', ''),
                    'pubdate': item.get('pubdate', 0)
                })

            self.logger.info(f"获取到 {len(videos)} 个热门视频")
            return videos

        except Exception as e:
            self.logger.error(f"获取B站热门视频失败: {e}")
            return []

    def save_json(self, videos: List[Dict], filepath: Path) -> None:
        """保存视频数据到JSON文件"""
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "videos": []
        }

        for idx, video in enumerate(videos, 1):
            data["videos"].append({
                "rank": idx,
                "title": video.get('title', ''),
                "url": video.get('url', '#'),
                "description": video.get('description', ''),
                "view": video.get('view', 0),
                "danmaku": video.get('danmaku', 0),
                "reply": video.get('reply', 0),
                "favorite": video.get('favorite', 0),
                "coin": video.get('coin', 0),
                "share": video.get('share', 0),
                "like": video.get('like', 0),
                "duration": video.get('duration', 0),
                "owner": video.get('owner', ''),
                "pic": video.get('pic', ''),
                "pubdate": video.get('pubdate', 0)
            })

        save_json(data, filepath)
        self.logger.info(f"数据已保存: {filepath}")

    def fetch_all(self, output_dir: Path) -> Dict[str, Path]:
        """获取所有B站数据并保存"""
        self.logger.info("开始获取B站热门数据...")

        result = {}
        videos = self.fetch_hot_videos()

        if videos:
            filepath = output_dir / 'bilibili_trending.json'
            self.save_json(videos, filepath)
            result['bilibili_trending'] = filepath
        else:
            self.logger.error("获取B站热门视频失败")

        return result


def main():
    """主函数"""
    print("🚀 开始获取B站热门数据...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    from ..config import REPORTS_DIR
    fetcher = BilibiliHotFetcher()

    result = fetcher.fetch_all(REPORTS_DIR)

    print("🎉 B站数据获取完成!")
    return result


if __name__ == "__main__":
    main()