# Trending Service

## 项目简介

**Trending Service** 是一个热点信息采集与 A 股行情分析服务，自动获取 GitHub Trending、B站热门、ArXiv 论文、知乎/微博/抖音热榜、AIHOT 等热点信息，同时采集 A 股市场指数、申万行业指数、概念板块 K 线、行业轮动与主力资金流向，通过 Web 界面集中展示。

### 核心功能

**热点数据采集**：GitHub Trending（含 AI 子榜）、B站热门、ArXiv 论文、HackerNews、知乎热榜、微博热搜、抖音热榜、AIHOT 资讯

**A 股行情分析**：市场指数、申万行业指数（含涨跌幅/回撤/动量/排名变化）、K 线图（candlestick 蜡烛图 + MA/BOLL/MACD/RSI/KDJ + 金叉信号）、行业轮动分析、主力资金流向、概念板块（白名单过滤）

**系统特性**：暗色主题 Web 界面、定时任务调度、重试管理器、RESTful API、HTML 报告自动生成

## 环境要求

- **Python**: 3.12+（推荐 3.12.10）
- **Playwright Chromium**: 知乎/抖音数据源必需
- **操作系统**: Windows / Linux / macOS

## 安装步骤

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 安装 Playwright Chromium

项目将 `PLAYWRIGHT_BROWSERS_PATH` 指向项目本地 `vendor/playwright-browsers/`，必须安装到该路径：

```powershell
# Windows PowerShell
$env:PLAYWRIGHT_BROWSERS_PATH='d:\MYDATA\Include\trending-service\vendor\playwright-browsers'
C:\Users\<用户名>\.pyenv\pyenv-win\versions\3.12.10\python.exe -m playwright install chromium
```

验证：`vendor/playwright-browsers/chromium-1208/chrome-win64/chrome.exe` 应存在。

### 3. 配置

配置文件 `config.yaml` 支持热加载，主要项：
- `server.port`: 端口（默认 8888）
- `data_sources`: 数据源开关、条数、概念板块白名单
- `schedule`: 定时任务（fetch_trending 每 8 小时 / fetch_index 开盘时段每 30 分钟）
- `database.path`: SQLite 路径（默认 `data/db/trending.db`）

## 使用方法

### 启动服务

```bash
# 前台模式
python -m src.main

# 后台模式（关闭 IDE 仍运行）
python scripts/start_service.py
```

### 访问报告

```
http://localhost:8888/report.html
```

### 服务管理

```bash
python scripts/start_service.py   # 启动
python scripts/stop_service.py    # 停止
python scripts/check_service.py   # 检查状态
python -m src.main --status       # 查看状态
```

### 立即执行任务

```bash
# 执行热点采集任务
python -m src.main --run-task fetch_trending

# 刷新指定数据源（不影响运行中的服务）
python -m src.main --refresh weibo zhihu douyin

# 刷新所有数据源
python -m src.main --refresh
```

### 手动生成报告

```bash
python -c "import sys; sys.path.insert(0, '.'); from src.utils.report_generator import ReportGenerator; ReportGenerator().generate_report()"
```

> **重要**：`src/templates/enhanced_report/` 下的文件是权威来源（source），`data/reports/report.html` 是生成产物。修改前端代码只改 source，再重新生成报告，避免双向修改不同步。

## 技术栈

- **Python 3.12+** + **Flask** - Web 框架
- **Playwright** - 浏览器自动化（知乎/抖音热榜）
- **Chart.js 4.4.1** + **chartjs-chart-financial 0.2.1** + **chartjs-adapter-date-fns 3.0.0** - K 线图渲染
- **jieba** - 中文分词
- **SQLite** - 数据存储
- **APScheduler** - 定时任务

## 许可证

MIT
