# Trending Service

## 项目概述

**Trending Service** 是一个热点信息采集服务，自动获取 GitHub Trending、B站热门视频、ArXiv论文等热点信息，并通过Web界面展示。

## 功能特性

- 📊 **GitHub Trending** 获取
- 🎬 **B站热门视频** 获取
- 🧬 **ArXiv论文** 获取（支持生物和计算机-人工智能分类）
- 🤖 **AI Trending** 获取
- 🌐 **Web界面** 展示热点报告
- 🔄 **定时任务** 自动获取热点信息
- 📡 **API接口** 提供数据访问
- 🛠️ **服务管理** 脚本（启动/停止/检查）

## 安装说明

### 1. 克隆项目

```bash
git clone <repository-url>
cd trending-service
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置项目

项目配置位于 `src/config.py` 文件中，可根据需要调整服务器端口、定时任务时间等设置。

## 使用方法

### 启动服务

```bash
python -m src.main
```

或使用启动脚本：

```bash
python scripts/start_service.py
```

### 访问报告

服务启动后，在浏览器中打开：

```
http://localhost:8000/report.html
```

### 检查服务状态

```bash
python scripts/check_service.py
```

### 停止服务

```bash
python scripts/stop_service.py
```

## 项目结构

```
trending-service/
├── src/                          # 源代码目录
│   ├── __init__.py              # 包初始化
│   ├── main.py                  # 主启动文件
│   ├── server.py                # HTTP服务器
│   ├── scheduler.py             # 定时任务调度器
│   ├── config.py                # 配置文件
│   ├── fetchers/                # 数据获取模块
│   │   ├── __init__.py
│   │   ├── github_trending.py   # GitHub热点获取
│   │   ├── bilibili_hot.py      # B站热门获取
│   │   └── arxiv_papers.py      # arXiv论文获取
│   └── utils/                   # 工具模块
│       ├── __init__.py
│       ├── html_generator.py    # HTML生成器
│       └── logger.py            # 日志工具
├── data/                        # 数据目录
│   ├── reports/                 # 生成的报告
│   └── logs/                    # 日志文件
├── scripts/                     # 脚本目录
│   ├── start_service.py         # 启动脚本
│   ├── stop_service.py          # 停止脚本
│   └── check_service.py         # 检查脚本
├── requirements.txt             # 依赖包
├── setup.py                     # 安装脚本
└── .gitignore                   # Git忽略文件
```

## API接口

### 获取GitHub热点

```
GET http://localhost:8000/api/github_trending
```

### 获取B站热门

```
GET http://localhost:8000/api/bilibili_trending
```

### 获取ArXiv生物分类

```
GET http://localhost:8000/api/arxiv_biology
```

### 获取ArXiv计算机-人工智能分类

```
GET http://localhost:8000/api/arxiv_computer_ai
```

### 获取AI热点

```
GET http://localhost:8000/api/ai_trending
```

### 获取GitHub本周增长

```
GET http://localhost:8000/api/github_weekly_growth
```

## 定时任务

服务内部集成了定时任务，无需外部依赖：

| 任务                     | 执行时间  | 功能                     |
| ------------------------ | --------- | ------------------------ |
| **fetch_trending** | 每日 8:00 | 自动获取所有热点信息     |
| **check_service**  | 每日 9:00 | 检查服务并打开浏览器预览 |

## 技术栈

- **Python 3.12+**
- **Flask** - Web框架
- **requests** - HTTP客户端
- **BeautifulSoup** - HTML解析
- **logging** - 日志记录

## 日志文件

服务日志位于：

```
data/logs/trending_service.log
```

## 维护说明

1. 定期检查日志文件，确保服务正常运行
2. 监控服务运行状态，可使用 `check_service.py` 脚本
3. 根据需要调整定时任务时间（在 `src/config.py` 中）
4. 如需修改数据源或添加新的数据源，可修改 `src/fetchers/` 目录下的相应文件

## 常见问题

### 服务无法启动

- 检查端口是否被占用
- 检查依赖是否正确安装
- 查看日志文件了解具体错误

### 数据不更新

- 检查定时任务是否启用（在 `src/config.py` 中）
- 手动运行服务，查看控制台输出了解错误
- 检查网络连接是否正常

### 报告页面显示异常

- 检查浏览器控制台是否有错误信息
- 检查数据文件是否存在且格式正确
- 重启服务尝试解决

## 许可证

本项目采用 MIT 许可证。
