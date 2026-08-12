# Trending Service

## 快速安装（Windows 服务）

### 一键安装/卸载（推荐）

使用 `dist/TrendingServiceSetup.exe`，图形化界面，双击即可安装/卸载 Windows 服务。

**GUI 模式**（双击运行）：
1. 双击 `TrendingServiceSetup.exe`，自动弹出 UAC 提权
2. 输入或浏览选择项目根目录
3. 点击「安装服务」→ 自动注册 Windows 服务 + 开机自启 + 崩溃重启 + 开始菜单快捷方式
4. 点击「卸载服务」→ 停止并删除服务 + 清理快捷方式

**命令行模式**：

```powershell
# 安装服务（需管理员权限）
TrendingServiceSetup.exe -install "D:\MYDATA\Include\trending-service"

# 卸载服务（需管理员权限）
TrendingServiceSetup.exe -uninstall

# 查看服务状态
TrendingServiceSetup.exe -status

# 显示帮助
TrendingServiceSetup.exe -help
```

**安装后服务特性**：
- 服务名称：`TrendingService`
- 启动类型：自动（开机自启）
- 崩溃恢复：60 秒后自动重启
- 日志重定向：`data/logs/service_nssm_stdout.log` / `service_nssm_stderr.log`（10MB 轮转）
- 开始菜单：「Trending Service」分组下有「访问报告」「项目目录」「服务管理」「卸载服务」快捷方式

**编译安装器**（修改源码后重新编译）：

```powershell
# 使用 Windows 内置 .NET 编译器，无需安装任何工具
powershell -ExecutionPolicy Bypass -File scripts\build_setup.ps1
```

> **重要**：不要通过 `scripts/start_service.py` 在 IDE 终端中启动服务。`DETACHED_PROCESS` 不脱离 Windows 作业对象，IDE 关闭/重启时会终止子进程，导致服务"神秘消失"。必须使用 exe 安装器注册为 Windows 服务。

### 访问报告

服务启动后访问：

```
http://localhost:8888/report.html
```

---

## 项目简介

**Trending Service** 是一个热点信息采集与 A 股行情分析服务，自动获取 GitHub Trending、B站热门、ArXiv 论文、知乎/微博/抖音热榜、AIHOT 等热点信息，同时采集 A 股市场指数、申万行业指数、概念板块 K 线、行业轮动与主力资金流向，通过 Web 界面集中展示。

### 核心功能

**热点数据采集**：GitHub Trending（含 AI 子榜）、B站热门、ArXiv 论文、HackerNews、知乎热榜、微博热搜、抖音热榜、AIHOT 资讯

**A 股行情分析**：市场指数、申万行业指数（含涨跌幅/回撤/动量/排名变化）、K 线图（candlestick 蜡烛图 + MA/BOLL/MACD/RSI/KDJ + 金叉信号）、行业轮动分析（排名趋势图 + 强弱 TOP10 并排 + 动量得分）、主力资金流向（双向条形图 + 桑基图资金流向路径，支持今日/5日/10日周期切换）、概念板块（白名单过滤 + 热力图）、市场情绪温度计（涨跌停/炸板/连板梯队）、北向资金流入

**系统特性**：暗色主题 Web 界面、定时任务调度、重试管理器、RESTful API（统一错误格式 + 响应时间监控）、HTML 报告自动生成、配置热加载、Windows 服务部署（nssm + 开机自启 + 崩溃重启）

## 环境要求

- **Python**: 3.12+（推荐 3.12.10）
- **Playwright Chromium**: 知乎/抖音数据源必需
- **nssm**: Windows 服务注册（已包含在 `vendor/nssm/nssm.exe`）
- **操作系统**: Windows / Linux / macOS（Windows 服务功能仅限 Windows）

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

### 3. 注册为 Windows 服务（推荐）

使用安装器 exe（见本文档顶部「快速安装」）：

```powershell
# GUI 模式（双击运行，自动提权）
dist\TrendingServiceSetup.exe

# 命令行模式（需管理员权限）
dist\TrendingServiceSetup.exe -install "D:\MYDATA\Include\trending-service"
```

### 4. 配置

配置文件 `config.yaml` 支持热加载，主要项：
- `server.port`: 端口（默认 8888）
- `data_sources`: 数据源开关、条数、概念板块白名单
- `schedule`: 定时任务（fetch_trending 每 8 小时 / fetch_index 开盘时段每 30 分钟）
- `database.path`: SQLite 路径（默认 `data/db/trending.db`）

## 使用方法

### 服务管理

**Windows 服务方式（推荐）**：

```powershell
Start-Service -Name TrendingService      # 启动
Stop-Service -Name TrendingService        # 停止
Restart-Service -Name TrendingService     # 重启
Get-Service -Name TrendingService         # 状态
# 或使用安装器
TrendingServiceSetup.exe -status          # 查看状态
TrendingServiceSetup.exe -uninstall       # 卸载
```

**命令行方式（开发/调试）**：

```bash
python -m src.main                        # 前台运行
python -m src.main --status               # 查看状态
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

### 重新编译安装器

安装器源码在 `scripts/setup/SetupForm.cs`，使用 Windows 内置 csc.exe 编译：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_setup.ps1
```

输出：`dist/TrendingServiceSetup.exe`（约 24KB，无需 .NET SDK，仅依赖 Windows 内置 .NET Framework 4.x）

## 技术栈

- **Python 3.12+** + **Flask** - Web 框架
- **Playwright** - 浏览器自动化（知乎/抖音热榜）
- **AKShare** - A 股行情/资金流/涨跌停数据源
- **Chart.js 4.4.1** + **chartjs-chart-financial 0.2.1** + **chartjs-adapter-date-fns 3.0.0** - K 线图渲染
- **chartjs-chart-sankey 0.12.1** - 资金流向桑基图
- **chartjs-chart-treemap** - 行业热力图
- **jieba** - 中文分词
- **SQLite** - 数据存储（WAL 模式 + 批量事务）
- **APScheduler** - 定时任务
- **nssm** - Windows 服务注册与守护
- **.NET Framework 4.x (C#)** - 安装器 exe（Windows 内置编译器）

## 注意事项

- **Python 环境**：必须使用 Python 3.12.10（`C:\Users\<用户名>\.pyenv\pyenv-win\versions\3.12.10\python.exe`），低版本未安装 AKShare 会导致资金流/情绪等接口返回空数据
- **服务部署**：必须通过 exe 安装器或 PowerShell 脚本注册为 Windows 服务，不要在 IDE 终端用 `start_service.py` 启动（IDE 关闭时进程会被作业对象终止）
- **端口冲突**：启动前如遇端口占用，安装器会自动清理；手动处理用 `netstat -ano | findstr :8888` + `Stop-Process -Id <PID> -Force`
- **报告生成**：修改 `src/templates/enhanced_report/` 下 source 文件后，需重新运行报告生成命令更新 `data/reports/report.html`
- **崩溃诊断**：段错误堆栈写入 `data/logs/crash_traceback.log`（faulthandler 每 300 秒转储线程栈）；服务日志在 `data/logs/service_nssm_*.log`

## 许可证

MIT
