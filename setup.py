"""
Trending Service 安装脚本
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取README文件
readme_file = Path(__file__).parent / "docs" / "README.md"
if readme_file.exists():
    with open(readme_file, 'r', encoding='utf-8') as f:
        long_description = f.read()
else:
    long_description = "Trending Service - 热点信息采集服务"

# 读取requirements.txt
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
else:
    requirements = []

setup(
    name="trending-service",
    version="1.0.0",
    description="热点信息采集服务",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Trending Service",
    author_email="trending@example.com",
    url="https://github.com/yourusername/trending-service",
    
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    
    entry_points={
        'console_scripts': [
            'trending-service=src.main:main',
            'trending-service-start=scripts.start_service:main',
            'trending-service-stop=scripts.stop_service:main',
            'trending-service-check=scripts.check_service:main',
        ],
    },
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    
    python_requires=">=3.8",
    
    keywords="trending, github, bilibili, arxiv, hot, service",
    
    project_urls={
        "Bug Reports": "https://github.com/yourusername/trending-service/issues",
        "Source": "https://github.com/yourusername/trending-service",
        "Documentation": "https://github.com/yourusername/trending-service/docs",
    },
)