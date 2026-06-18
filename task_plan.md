# Task Plan: 删除 StockFetcher + 实现 IndexFetcher

## Goal
从 trending-service 项目中删除现有 StockFetcher（个股数据）及相关代码，新增 IndexFetcher 获取 A 股市场指数 + 申万行业指数数据。

## Current Phase
Phase 1 - 计划已调整，等待用户确认

## Phases

### Phase 1: 删除 StockFetcher 相关代码
- [ ] 删除 `src/fetchers/stock.py`
- [ ] 删除 `src/db/stock_dao.py`
- [ ] 从 `src/db/models.py` 移除 `StockData` 数据类
- [ ] 从 `src/scheduler.py` 移除 stock 相关代码：
  - `_FETCHER_METHOD_MAP` 中的 `stock` 条目
  - `_is_stock_trading_time`、`is_stock_auto_fetch_enabled`、`set_stock_auto_fetch`、`is_stock_enabled` 方法
  - `_fetch_stock_data` 方法
  - `fetch_stock` 调度任务注册
- [ ] 从 `src/server.py` 移除 stock 相关 API 路由：
  - `/api/stock/fetch-control`、`/api/stock/trigger-fetch`、`/api/stock/market`
  - `/api/stock/summary`、`/api/stock/gainers`、`/api/stock/losers`
  - `/api/stock/volume`、`/api/stock/detail`、`/api/stock/kline`
- [ ] 从 `config.yaml` 移除 `stock` 数据源配置和 `fetch_stock` 调度配置
- [ ] 检查 `src/templates/enhanced_report_template.html` 是否有 stock 前端代码，按需清理
- **Status:** pending

### Phase 2: 数据模型与 DAO 层（IndexData）
- [ ] 在 `src/db/models.py` 新增 `IndexData` 数据类
  - 字段：id、code、name、category(market/industry)、price、change、change_pct、high、low、open、pre_close、volume、amount、turnover_rate、source、fetched_at
  - 包含 `to_dict` 和 `from_dict` 方法
- [ ] 新增 `src/db/index_dao.py` 实现 `IndexDAO`
  - 方法：`_init_table`、`save_index`、`save_indices`、`get_market_indices`、`get_industry_indices`、`get_latest`、`get_index_by_code`、`_get_latest_date`
- **Status:** pending

### Phase 3: IndexFetcher 实现
- [x] 新增 `src/fetchers/index.py`，实现 `IndexFetcher` 类
- [x] 实现东方财富 HTTP 接口获取 A 股市场指数实时行情（8 个主要指数）
- [x] 实现东方财富 K 线接口获取指数历史 K 线
- [x] 延迟导入 AKShare 获取申万行业指数
- [x] 实现 `save_to_db` 方法写入数据库
- **Status:** completed

### Phase 4: 注册与配置
- [ ] 在 `src/fetchers/__init__.py` 的 `_FETCHER_REGISTRY` 注册 `index`
- [ ] 在 `src/scheduler.py` 的 `_FETCHER_METHOD_MAP` 注册 `index: 'fetch'`
- [ ] 在 `src/scheduler.py` 添加 `_fetch_index_data` 方法和 `fetch_index` 调度任务
- [ ] 在 `config.yaml` 添加 `index` 数据源配置和 `fetch_index` 调度配置
- [ ] 在 `requirements.txt` 添加 `akshare>=1.12.0`
- [ ] 在 `src/server.py` 添加 index 相关 API 路由（可选，后续按需添加）
- **Status:** pending

### Phase 5: 测试与验证
- [x] 验证模块导入无误（IndexData、IndexDAO、IndexFetcher）
- [x] 验证调度器注册无误（`index` 已注册到 `_FETCHER_METHOD_MAP`）
- [x] 验证数据库 `index_data` 表创建正确（16 列）
- [x] 验证 IndexDAO 的 save_index、get_latest、get_index_by_code 方法
- [x] 验证 IndexFetcher 获取市场指数（8 条，含上证、深证、沪深300等）
- [x] 验证 K 线接口获取历史数据（5 条）
- [x] 验证 save_to_db 保存数据（8 条）
- [x] 验证 AKShare 延迟导入正常（未安装时优雅降级）
- [x] 验证 stock 相关代码已完全清理（Grep 搜索无残留）
- **Status:** completed

## Key Questions
1. IndexFetcher 是否继承 BaseFetcher？— 否，独立实现（BaseFetcher 返回 TrendingItem 不适用）
2. AKShare 延迟导入位置？— 在获取申万行业指数的方法内部 `import akshare`
3. 是否需要保留 stock 数据库表？— 否，完全清理，仅保留 index 相关表
4. server.py 的 stock API 路由是否替换为 index？— Phase 4 按需添加 index 路由

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 完全删除 StockFetcher 及相关代码 | 用户明确要求去除东方财富个股数据提取逻辑 |
| IndexFetcher 独立实现 | BaseFetcher 返回 TrendingItem 不适用指数数据 |
| 主数据源用东方财富 HTTP | 接口稳定，字段全，支持 K 线和实时行情 |
| 申万行业指数用 AKShare | 东财 HTTP 不直接提供，AKShare 覆盖完整 |
| AKShare 延迟导入 | 避免全量预导入导致 38s 启动时间（项目历史教训） |
| IndexData.category 取值 market/industry | 仅覆盖 A 股市场指数和申万行业指数 |

## Files to Create/Modify/Delete

### 删除文件
- `src/fetchers/stock.py`
- `src/db/stock_dao.py`

### 新增文件
- `src/fetchers/index.py` — IndexFetcher 实现
- `src/db/index_dao.py` — IndexDAO 实现

### 修改文件
- `src/db/models.py` — 移除 StockData，新增 IndexData
- `src/fetchers/__init__.py` — 注册 index fetcher
- `src/scheduler.py` — 移除 stock 代码，注册 index
- `src/server.py` — 移除 stock API 路由（后续按需添加 index 路由）
- `config.yaml` — 移除 stock 配置，添加 index 配置
- `requirements.txt` — 添加 akshare 依赖
- `src/templates/enhanced_report_template.html` — 按需清理 stock 前端代码

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- 删除 stock 代码时需谨慎，确保无残留引用导致导入错误
- AKShare 必须延迟导入，避免影响启动速度
- 东方财富指数 secid 格式：沪市 `1.代码`，深市 `0.代码`
- 申万行业指数代码：801010（农林牧渔）、801120（食品饮料）等
