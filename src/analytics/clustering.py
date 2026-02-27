"""
话题聚类模块
使用 K-Means 对热点数据进行聚类
"""

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from typing import List, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.fetchers import TrendingItem


@dataclass
class Topic:
    """话题"""
    id: int
    name: str
    keywords: List[str]
    items: List
    item_count: int = 0
    source: str = ""  # 数据源
    
    def __post_init__(self):
        self.item_count = len(self.items)


class TopicCluster:
    """话题聚类器"""
    
    def __init__(self, n_clusters: int = 5, max_features: int = 1000):
        """
        初始化话题聚类器
        
        Args:
            n_clusters: 聚类数量
            max_features: TF-IDF 最大特征数
        """
        self.n_clusters = n_clusters
        self.max_features = max_features
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.8
        )
    
    def cluster(self, items: List) -> List[Topic]:
        """
        对数据项进行聚类
        
        Args:
            items: 热点数据列表
            
        Returns:
            List[Topic]: 话题列表
        """
        if not items:
            return []
        
        # 如果数据量小于聚类数，调整聚类数
        if len(items) < self.n_clusters:
            self.n_clusters = max(2, len(items) // 2) if len(items) > 2 else 1
        
        # 准备文本数据
        texts = []
        for item in items:
            text = item.title
            if item.description:
                text += ' ' + item.description
            texts.append(text)
        
        # 文本向量化
        try:
            vectors = self.vectorizer.fit_transform(texts)
        except ValueError:
            # 如果向量化失败（如所有文本相同），返回单个话题
            return [Topic(
                id=0,
                name=items[0].title[:30] + '...' if len(items[0].title) > 30 else items[0].title,
                keywords=[],
                items=items,
                source=items[0].source if items else ""
            )]
        
        # K-Means 聚类
        kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(vectors)
        
        # 获取特征词
        feature_names = self.vectorizer.get_feature_names_out()
        
        # 构建话题
        topics = []
        for i in range(self.n_clusters):
            topic_items = [
                items[j] for j in range(len(items)) if labels[j] == i
            ]
            
            if not topic_items:
                continue
            
            # 提取话题关键词
            center = kmeans.cluster_centers_[i]
            top_indices = center.argsort()[-5:][::-1]
            topic_keywords = [feature_names[j] for j in top_indices if j < len(feature_names)]
            
            # 过滤掉无意义的关键词
            topic_keywords = self._filter_keywords(topic_keywords)
            
            # 生成话题名称（使用热度最高的数据项标题）
            topic_name = self._generate_topic_name(topic_items)
            
            topics.append(Topic(
                id=i,
                name=topic_name,
                keywords=topic_keywords,
                items=topic_items,
                source=topic_items[0].source if topic_items else ""
            ))
        
        # 按话题内数据量排序
        topics.sort(key=lambda x: x.item_count, reverse=True)
        return topics
    
    def _filter_keywords(self, keywords: List[str]) -> List[str]:
        """过滤无意义的关键词"""
        # 停用词列表
        stop_words = {
            'hn', 'show', 'ask', 'tell', 'new', 'use', 'using', 'used',
            'build', 'building', 'built', 'make', 'making', 'made',
            'create', 'creating', 'created', 'write', 'writing', 'written',
            'time', 'year', 'day', 'way', 'work', 'worked', 'working',
            'run', 'running', 'ran', 'start', 'started', 'starting',
            'get', 'getting', 'got', 'use', 'using', 'used',
            'open', 'source', 'github', 'project', 'tool', 'app',
            'web', 'site', 'online', 'free', 'version', 'update',
            'release', 'launch', 'announced', 'available', 'based',
            'simple', 'easy', 'fast', 'quick', 'better', 'best',
        }
        
        filtered = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in stop_words and len(kw) > 2:
                filtered.append(kw)
        
        return filtered[:5]  # 最多返回5个关键词
    
    def _generate_topic_name(self, items: List) -> str:
        """生成话题名称"""
        if not items:
            return "未命名话题"
        
        # 使用热度最高的数据项标题作为话题名
        hottest = max(items, key=lambda x: x.hot_score or 0)
        # 截取前30个字符
        title = hottest.title[:30]
        if len(hottest.title) > 30:
            title += "..."
        return title


def cluster_items_by_source(items: List, n_clusters: int = 3) -> Dict[str, List[Topic]]:
    """
    按数据源分组进行话题聚类
    
    Args:
        items: 热点数据列表
        n_clusters: 每个数据源的聚类数
        
    Returns:
        Dict[str, List[Topic]]: 各数据源的话题列表
    """
    from collections import defaultdict
    
    # 按数据源分组
    by_source = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)
    
    # 为每个数据源进行聚类
    result = {}
    for source, source_items in by_source.items():
        if len(source_items) >= 3:  # 至少需要3条数据才能聚类
            # 根据数据量动态调整聚类数
            actual_clusters = min(n_clusters, len(source_items) // 2)
            actual_clusters = max(2, actual_clusters)  # 至少2个话题
            
            clusterer = TopicCluster(n_clusters=actual_clusters)
            topics = clusterer.cluster(source_items)
            result[source] = topics
        elif len(source_items) > 0:
            # 数据太少，直接作为一个话题
            result[source] = [Topic(
                id=0,
                name=source_items[0].title[:30] + '...' if len(source_items[0].title) > 30 else source_items[0].title,
                keywords=[],
                items=source_items,
                source=source
            )]
    
    return result


if __name__ == '__main__':
    # 测试
    from src.fetchers import TrendingItem
    
    test_items = [
        TrendingItem(source='github', title='Python 机器学习框架', description='深度学习 TensorFlow', hot_score=100),
        TrendingItem(source='github', title='PyTorch 神经网络库', description='Facebook 开源 ML', hot_score=90),
        TrendingItem(source='github', title='React 前端框架更新', description='JavaScript UI', hot_score=80),
        TrendingItem(source='github', title='Vue.js 3.0 发布', description='前端框架', hot_score=70),
        TrendingItem(source='hackernews', title='AI 模型训练技巧', description='机器学习', hot_score=85),
        TrendingItem(source='hackernews', title='Web 开发趋势', description='前端技术', hot_score=75),
    ]
    
    print('测试按数据源话题聚类:')
    result = cluster_items_by_source(test_items, n_clusters=2)
    
    for source, topics in result.items():
        print(f'\n{source}: {len(topics)} 个话题')
        for topic in topics:
            print(f'  - {topic.name} ({topic.item_count} 条)')
            print(f'    关键词: {topic.keywords}')
