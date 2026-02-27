"""
趋势分析模块
分析关键词和话题的历史趋势
"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from src.db import TrendingDAO


class TrendAnalyzer:
    """趋势分析器"""
    
    def __init__(self, dao: TrendingDAO):
        self.dao = dao
    
    def get_keyword_trend(
        self, 
        keyword: str, 
        days: int = 7
    ) -> List[Dict]:
        """
        获取关键词的历史趋势
        
        Args:
            keyword: 关键词
            days: 统计天数
            
        Returns:
            List[Dict]: 每日趋势数据
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # 获取历史数据
        items = self.dao.get_items(
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            limit=1000
        )
        
        # 按天统计
        daily_counts = defaultdict(int)
        daily_scores = defaultdict(list)
        
        for item in items:
            date_key = item.fetched_at.date()
            daily_counts[date_key] += 1
            if item.hot_score:
                daily_scores[date_key].append(item.hot_score)
        
        # 构建趋势数据
        trend = []
        for i in range(days + 1):
            current_date = start_date + timedelta(days=i)
            count = daily_counts.get(current_date, 0)
            scores = daily_scores.get(current_date, [])
            avg_score = sum(scores) / len(scores) if scores else 0
            
            trend.append({
                'date': current_date.isoformat(),
                'count': count,
                'avg_score': round(avg_score, 2)
            })
        
        return trend
    
    def get_hot_keywords_trend(
        self,
        days: int = 7,
        top_n: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        获取热门关键词的趋势
        
        Args:
            days: 统计天数
            top_n: 热门关键词数量
            
        Returns:
            Dict[str, List[Dict]]: 各关键词的趋势数据
        """
        # 先获取最近的热门关键词
        recent_keywords = self.dao.get_trending_keywords(days=1, top_n=top_n)
        
        result = {}
        for kw_data in recent_keywords:
            keyword = kw_data['keyword']
            trend = self.get_keyword_trend(keyword, days)
            result[keyword] = trend
        
        return result
    
    def get_source_trend(
        self,
        days: int = 7
    ) -> Dict[str, List[Dict]]:
        """
        获取各数据源的数据量趋势
        
        Args:
            days: 统计天数
            
        Returns:
            Dict[str, List[Dict]]: 各数据源的趋势数据
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # 获取所有数据源
        sources = self.dao.get_sources()
        
        result = {}
        for source in sources:
            trend = []
            for i in range(days + 1):
                current_date = start_date + timedelta(days=i)
                count = self.dao.get_count(
                    source=source,
                    start_date=current_date,
                    end_date=current_date
                )
                trend.append({
                    'date': current_date.isoformat(),
                    'count': count
                })
            result[source] = trend
        
        return result
    
    def get_top_items_by_date(
        self,
        target_date: date,
        limit: int = 10
    ) -> List[Dict]:
        """
        获取某天的热门数据
        
        Args:
            target_date: 目标日期
            limit: 返回数量
            
        Returns:
            List[Dict]: 热门数据列表
        """
        items = self.dao.get_items(
            start_date=target_date,
            end_date=target_date,
            limit=limit
        )
        
        # 按热度排序
        items.sort(key=lambda x: x.hot_score or 0, reverse=True)
        
        return [
            {
                'title': item.title,
                'url': item.url,
                'source': item.source,
                'hot_score': item.hot_score,
                'author': item.author
            }
            for item in items
        ]
    
    def compare_keywords(
        self,
        keywords: List[str],
        days: int = 7
    ) -> Dict[str, List[Dict]]:
        """
        对比多个关键词的趋势
        
        Args:
            keywords: 关键词列表
            days: 统计天数
            
        Returns:
            Dict[str, List[Dict]]: 各关键词的趋势对比数据
        """
        result = {}
        for keyword in keywords:
            trend = self.get_keyword_trend(keyword, days)
            result[keyword] = trend
        return result
    
    def get_trend_summary(self, days: int = 7) -> Dict:
        """
        获取趋势汇总信息
        
        Args:
            days: 统计天数
            
        Returns:
            Dict: 趋势汇总数据
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # 获取总数据量趋势
        total_trend = []
        for i in range(days + 1):
            current_date = start_date + timedelta(days=i)
            count = self.dao.get_count(
                start_date=current_date,
                end_date=current_date
            )
            total_trend.append({
                'date': current_date.isoformat(),
                'count': count
            })
        
        # 获取热门关键词
        hot_keywords = self.dao.get_trending_keywords(days=days, top_n=10)
        
        # 获取数据源分布
        source_distribution = {}
        for source in self.dao.get_sources():
            count = self.dao.get_count(source=source, start_date=start_date, end_date=end_date)
            source_distribution[source] = count
        
        return {
            'total_trend': total_trend,
            'hot_keywords': hot_keywords,
            'source_distribution': source_distribution,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }


def generate_trend_chart_data(
    dao: TrendingDAO,
    days: int = 7
) -> Dict:
    """
    生成趋势图表数据
    
    Args:
        dao: 数据访问对象
        days: 统计天数
        
    Returns:
        Dict: 图表数据
    """
    analyzer = TrendAnalyzer(dao)
    
    return {
        'keyword_trends': analyzer.get_hot_keywords_trend(days=days, top_n=5),
        'source_trends': analyzer.get_source_trend(days=days),
        'summary': analyzer.get_trend_summary(days=days)
    }


if __name__ == '__main__':
    # 测试
    from src.config import DATABASE
    
    dao = TrendingDAO(DATABASE['path'])
    analyzer = TrendAnalyzer(dao)
    
    print('测试趋势分析:')
    
    # 测试关键词趋势
    trend = analyzer.get_keyword_trend('AI', days=7)
    print(f'\nAI 关键词趋势:')
    for day in trend[-3:]:  # 显示最近3天
        print(f"  {day['date']}: {day['count']} 次")
    
    # 测试数据源趋势
    source_trends = analyzer.get_source_trend(days=7)
    print(f'\n数据源趋势:')
    for source, trend in source_trends.items():
        total = sum(d['count'] for d in trend)
        print(f"  {source}: {total} 条")
