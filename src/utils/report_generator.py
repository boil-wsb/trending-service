"""
增强版报告生成器
支持从数据库读取数据，生成包含关键词和话题聚类的报告
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, date

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import DATABASE, REPORTS_DIR
from src.db import TrendingDAO, TrendingItem
from src.analytics import KeywordExtractor, TopicCluster, extract_keywords_for_items, generate_trend_chart_data


class ReportGenerator:
    """增强版报告生成器"""

    def __init__(self, reports_dir: Path = None):
        self.reports_dir = reports_dir or REPORTS_DIR
        self.dao = TrendingDAO(DATABASE['path'])
        self.keyword_extractor = KeywordExtractor(top_k=5)
        self.topic_cluster = TopicCluster(n_clusters=5)

    def generate_report(self) -> Path:
        """
        生成完整的HTML报告
        
        Returns:
            生成的HTML文件路径
        """
        print("📝 开始生成报告...")
        
        # 获取今天的数据
        today = date.today()
        items = self.dao.get_items(start_date=today, end_date=today, limit=200)
        
        if not items:
            print("⚠️ 今天没有数据，尝试获取最近的数据...")
            items = self.dao.get_items(limit=200)
        
        print(f"📊 获取到 {len(items)} 条数据")
        
        # 提取关键词
        items = extract_keywords_for_items(items, top_k=5)
        
        # 生成趋势图表数据
        trend_data = generate_trend_chart_data(self.dao, days=7)
        
        # 生成报告数据
        report_data = {
            'generated_at': datetime.now().isoformat(),
            'total_items': len(items),
            'sources': self._group_by_source(items),
            'keywords': self.keyword_extractor.extract_from_items(items),
            'topics': self._cluster_topics(items),
            'trends': trend_data,
            'stats': self._generate_stats(items)
        }
        
        # 生成HTML
        html_content = self._generate_html(report_data)
        
        # 保存报告
        report_path = self.reports_dir / "report.html"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ 报告已生成: {report_path}")
        return report_path

    def _group_by_source(self, items: List[TrendingItem]) -> Dict[str, List[Dict]]:
        """按数据源分组，并按热度排序"""
        from collections import defaultdict
        
        by_source = defaultdict(list)
        for item in items:
            item_dict = {
                'id': item.id,
                'title': item.title,
                'url': item.url,
                'author': item.author,
                'description': item.description,
                'hot_score': item.hot_score,
                'category': item.category,
                'keywords': item.keywords,
                'fetched_at': item.fetched_at.isoformat() if item.fetched_at else None,
                'extra': item.extra
            }
            by_source[item.source].append(item_dict)
        
        # 对每个数据源的数据按热度排序（降序）
        for source in by_source:
            by_source[source].sort(key=lambda x: x['hot_score'] or 0, reverse=True)
        
        return dict(by_source)

    def _cluster_topics(self, items: List[TrendingItem]) -> Dict[str, List[Dict]]:
        """按数据源对数据进行话题聚类"""
        if len(items) < 3:
            return {}
        
        # 使用按数据源聚类
        from src.analytics import cluster_items_by_source
        topics_by_source = cluster_items_by_source(items, n_clusters=3)
        
        result = {}
        for source, topics in topics_by_source.items():
            result[source] = []
            for topic in topics:
                result[source].append({
                    'id': topic.id,
                    'name': topic.name,
                    'keywords': topic.keywords,
                    'item_count': topic.item_count,
                    'source': topic.source,
                    'items': [
                        {
                            'title': item.title,
                            'url': item.url,
                            'source': item.source,
                            'hot_score': item.hot_score
                        }
                        for item in topic.items[:5]  # 只显示前5条
                    ]
                })
        
        return result

    def _generate_stats(self, items: List[TrendingItem]) -> Dict:
        """生成统计数据"""
        from collections import defaultdict
        
        # 按数据源统计
        by_source = defaultdict(lambda: {'count': 0, 'avg_score': 0, 'total_score': 0})
        
        for item in items:
            source = item.source
            by_source[source]['count'] += 1
            by_source[source]['total_score'] += item.hot_score or 0
        
        # 计算平均值
        for source in by_source:
            count = by_source[source]['count']
            if count > 0:
                by_source[source]['avg_score'] = round(by_source[source]['total_score'] / count, 2)
        
        return {
            'by_source': dict(by_source),
            'total_count': len(items),
            'date_range': {
                'start': min(item.fetched_at.isoformat() for item in items) if items else None,
                'end': max(item.fetched_at.isoformat() for item in items) if items else None
            }
        }

    def _generate_html(self, data: Dict) -> str:
        """生成HTML内容"""
        template = self._get_template()
        
        # 将数据嵌入到HTML中
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        
        html = template.replace(
            'window.REPORT_DATA = {};',
            f'window.REPORT_DATA = {json_data};'
        )
        
        return html

    def _get_template(self) -> str:
        """获取HTML模板"""
        # 优先使用增强版模板
        template_path = Path(__file__).parent.parent / "templates" / "enhanced_report_template.html"
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"读取增强版模板失败: {e}，尝试使用默认模板")
            # 如果增强版模板不存在，使用旧模板
            template_path = Path(__file__).parent.parent / "templates" / "report_template.html"
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e2:
                print(f"读取默认模板也失败: {e2}")
                return self._get_default_template()

    def _get_default_template(self) -> str:
        """获取默认模板（当模板文件不存在时）"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>每日热门数据报告</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #333; color: white; padding: 20px; text-align: center; }
        .section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
        th { background: #f5f5f5; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 每日热门数据报告</h1>
            <p>生成时间: <span id="generated-time"></span></p>
        </div>
        <div id="content"></div>
    </div>
    <script>
        window.REPORT_DATA = {};
    </script>
</body>
</html>'''


def main():
    """主函数"""
    print("🚀 开始生成报告...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    generator = ReportGenerator()
    report_path = generator.generate_report()
    
    print(f"\n🎉 报告生成完成!")
    print(f"📄 报告路径: {report_path}")


if __name__ == "__main__":
    main()
