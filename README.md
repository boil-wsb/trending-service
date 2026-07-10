# Trending Service

## 项目简介

**Trending Service** 是一个热点信息采集与 A 股行情分析服务，自动获取 GitHub Trending、B站热门、ArXiv 论文、知乎/微博/抖音热榜、AIHOT 等热点信息，同时采集 A 股市场指数、申万行业指数、概念板块 K 线、行业轮动与主力资金流向，通过 Web 界面集中展示。

### 核心功能

**热点数据采集**：GitHub Trending（含 AI 子榜）、B站热门、ArXiv 论文、HackerNews、知乎热榜、微博热搜、抖音热榜、AIHOT 资讯

**A 股行情分析**：市场指数、申万行业指数（含涨跌幅/回撤/动量/排名变化）、K 线图（candlestick 蜡烛图 + MA/BOLL/MACD/RSI/KDJ + 金叉信号）、行业轮动分析（排名趋势图 + 强弱 TOP10 并排 + 动量得分）、主力资金流向（双向条形图 + 桑基图资金流向路径，支持今日/5日/10日周期切换）、概念板块（白名单过滤 + 热力图）、市场情绪温度计（涨跌停/炸板/连板梯队）、北向资金流入

**系统特性**：暗色主题 Web 界面、定时任务调度、重试管理器、RESTful API（统一错误格式 + 响应时间监控）、HTML 报告自动生成、配置热加载

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

### 服务管理

```bash
python scripts/start_service.py   # 启动
python scripts/stop_service.py    # 停止
python scripts/check_service.py   # 检查状态
python -m src.main --status       # 查看状态
```

### 启动服务

```bash
# 后台模式（关闭 IDE 仍运行）
python scripts/start_service.py

# 前台模式
python -m src.main
```

### 访问报告

```
http://localhost:8888/report.html
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
- **AKShare** - A 股行情/资金流/涨跌停数据源
- **Chart.js 4.4.1** + **chartjs-chart-financial 0.2.1** + **chartjs-adapter-date-fns 3.0.0** - K 线图渲染
- **chartjs-chart-sankey 0.12.1** - 资金流向桑基图
- **chartjs-chart-treemap** - 行业热力图
- **jieba** - 中文分词
- **SQLite** - 数据存储
- **APScheduler** - 定时任务

## 注意事项

- **Python 环境**：必须使用 Python 3.12.10（`C:\Users\<用户名>\.pyenv\pyenv-win\versions\3.12.10\python.exe`），低版本未安装 AKShare 会导致资金流/情绪等接口返回空数据
- **端口冲突**：Flask 开发服务器无法优雅关闭，启动前如遇 `Address already in use`，需用 `netstat -ano | findstr :8888` 查找并 `Stop-Process -Id <PID> -Force` 清理残留进程
- **报告生成**：修改 `src/templates/enhanced_report/` 下 source 文件后，需重新运行报告生成命令更新 `data/reports/report.html`

## 许可证

MIT
