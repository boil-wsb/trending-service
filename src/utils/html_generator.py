"""
HTML生成器模块
生成热点信息报告页面
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径（支持直接运行和作为包导入）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import DATA_FILES, REPORTS_DIR


class HTMLGenerator:
    """HTML报告生成器"""

    def __init__(self, reports_dir: Path = None):
        self.reports_dir = reports_dir or REPORTS_DIR
        self.template = self._get_template()

    def _get_template(self) -> str:
        """获取HTML模板"""
        # 读取模板文件
        template_path = Path(__file__).parent.parent / "templates" / "report_template.html"
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"读取模板文件失败: {e}")
            # 返回一个简单的默认模板作为备份
            return '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>每日热门数据报告</title>
</head>
<body>
    <h1>每日热门数据报告</h1>
    <p>模板加载失败，请检查模板文件是否存在。</p>
</body>
</html>
            '''

    def generate_report(self, data_files: Dict[str, Path] = None) -> Path:
        """
        生成HTML报告

        Args:
            data_files: 数据文件路径字典

        Returns:
            生成的HTML文件路径
        """
        data_files = data_files or DATA_FILES
        report_path = self.reports_dir / "report.html"

        try:
            # 确保所有数据文件存在（即使为空）
            for key, file_path in data_files.items():
                if not file_path.exists():
                    # 创建空数据文件
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
                    print(f"✅ 创建空数据文件: {file_path}")

            # 读取所有数据文件
            data = {}
            for key, file_path in data_files.items():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data[key] = json.load(f)
                except Exception as e:
                    print(f"读取数据文件 {file_path} 失败: {e}")
                    data[key] = []

            # 生成HTML内容
            html_content = self.template

            # 保存HTML文件
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"✅ HTML报告已生成: {report_path}")
            return report_path

        except Exception as e:
            print(f"❌ 生成HTML报告失败: {e}")
            return None