/**
 * 数据服务层 - 借鉴 stock-dashboard services/sdk.ts 设计
 *
 * 统一 API 调用入口,内置差异化 TTL 缓存与错误处理。
 * 解决以下痛点:
 * 1. 各 JS 文件直接 fetch,URL 风格不统一(API_BASE_URL vs 相对路径)
 * 2. K线数据无缓存,每次切换周期/指标都重新请求
 * 3. 错误处理分散,无法对接后端统一错误格式
 */
const DataService = (function () {
    'use strict';

    // ===== 差异化 TTL 缓存注册表(毫秒)=====
    // 借鉴 stock-dashboard DEFAULT_TTL 设计,不同数据类型独立 TTL
    const CACHE_TTL = {
        marketIndices: 30000,      // 市场指数 30s
        industryIndices: 60000,    // 行业指数 60s
        kline: 600000,             // K 线 10min(最大价值:切换周期/指标命中缓存)
        rotation: 60000,           // 轮动分析 60s
        rotationHistory: 300000,   // 轮动历史趋势 5min（历史数据不常变）
        fundFlow: 30000,           // 资金流 30s
        sentiment: 60000,          // 市场情绪 60s
        sourceStatus: 30000,       // 数据源状态 30s
        search: 30000,             // 搜索结果 30s
        dataByDate: 300000,        // 按日期范围的数据 5min
    };

    // ===== 内存缓存 =====
    const _cache = new Map();

    // ===== in-flight 请求去重（借鉴 stock-dashboard BoardDataContext 防重入）=====
    // 相同 key 的并发请求复用同一个 Promise，避免重复网络请求。
    // 场景：多模块同时调 getIndustryIndices()，只发一次请求。
    const _inflight = new Map();

    function _getCacheKey(method, ...args) {
        return `${method}:${JSON.stringify(args)}`;
    }

    function _getFromCache(key) {
        const item = _cache.get(key);
        if (!item) return null;
        if (Date.now() - item.timestamp > item.ttl) {
            _cache.delete(key);
            return null;
        }
        return item.data;
    }

    function _setCache(key, data, ttl) {
        _cache.set(key, { data, timestamp: Date.now(), ttl });
    }

    /**
     * 带缓存的 fetch 包装器（含 in-flight 去重）
     * @param {string} key - 缓存键
     * @param {number} ttl - 缓存 TTL(毫秒)
     * @param {Function} fetcher - 实际获取数据的函数(返回 Promise)
     * @param {boolean} useCache - 是否使用缓存(默认 true)
     */
    function _withCache(key, ttl, fetcher, useCache) {
        if (useCache !== false) {
            const cached = _getFromCache(key);
            if (cached !== null) return Promise.resolve(cached);
        }
        // in-flight 去重：相同 key 的并发调用复用同一个 Promise
        if (_inflight.has(key)) {
            return _inflight.get(key);
        }
        const p = Promise.resolve()
            .then(fetcher)
            .then(data => {
                if (useCache !== false) _setCache(key, data, ttl);
                return data;
            })
            .finally(() => {
                _inflight.delete(key);
            });
        _inflight.set(key, p);
        return p;
    }

    // ===== 统一 URL 构建(统一用相对路径)=====
    function _buildUrl(path, params) {
        if (!params) return path;
        const parts = [];
        for (const k in params) {
            if (params[k] !== undefined && params[k] !== null) {
                parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`);
            }
        }
        return parts.length ? `${path}?${parts.join('&')}` : path;
    }

    // ===== 统一请求函数 =====
    async function _request(path, options) {
        options = options || {};
        const method = options.method || 'GET';
        const params = options.params || {};
        const url = _buildUrl(path, params);

        // 用 perfMonitor 记录每个 API 请求耗时
        const perfLabel = `api:${path}`;
        if (window.perfMonitor) window.perfMonitor.start(perfLabel);

        try {
            // AbortController 超时保护，防止请求永久挂起导致 in-flight 锁永久占用
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);
            let resp;
            try {
                resp = await fetch(url, { method: method, signal: controller.signal });
            } finally {
                clearTimeout(timeoutId);
            }

            if (!resp.ok) {
                let errMsg = `HTTP ${resp.status}`;
                try {
                    const errBody = await resp.json();
                    errMsg = (errBody.error && errBody.error.message) || errBody.error || errMsg;
                } catch (_) { /* 非 JSON 响应,用 HTTP 状态码 */ }
                throw new Error(errMsg);
            }

            const body = await resp.json();
            // 兼容旧格式:有 success 字段时检查,无则直接返回
            if (body.success === false) {
                throw new Error((body.error && body.error.message) || body.error || '请求失败');
            }
            return body.success !== undefined ? (body.data !== undefined ? body.data : body) : body;
        } finally {
            if (window.perfMonitor) window.perfMonitor.end(perfLabel);
        }
    }

    // ===== 轮询工具（借鉴 stock-dashboard usePolling.ts 的 pauseOnHidden 设计）=====
    // 页面隐藏时自动暂停轮询，恢复时若已过期则立即刷新。
    // 用法：
    //   const poller = DataService.createPoller(fetchSourceStatus, 30000);
    //   poller.start();  // 开始轮询
    //   poller.stop();   // 停止
    //   poller.refresh(); // 手动触发一次（不重置计时）
    function createPoller(fetcher, interval) {
        let timer = null;
        let lastRun = 0;
        let running = false;

        function run() {
            if (running) return;
            running = true;
            lastRun = Date.now();
            Promise.resolve().then(fetcher).catch(function (e) {
                console.warn('[Poller] fetch error:', e);
            }).finally(function () {
                running = false;
            });
        }

        function scheduleNext() {
            if (timer === null) return;  // 已停止
            timer = setTimeout(function () {
                if (document.hidden) return;  // 隐藏时跳过本次，等可见事件触发
                run();
                scheduleNext();
            }, interval);
        }

        function start() {
            if (timer !== null) return;  // 已启动
            timer = 0;  // 标记已启动（非 null）
            run();
            scheduleNext();
            // 监听可见性变化
            document.addEventListener('visibilitychange', _onVisibility);
        }

        function stop() {
            if (timer !== null) {
                clearTimeout(timer);
                timer = null;
            }
            document.removeEventListener('visibilitychange', _onVisibility);
        }

        function _onVisibility() {
            if (document.hidden) return;
            // 页面恢复可见：若距上次刷新超过 interval，立即刷新
            if (Date.now() - lastRun >= interval) {
                run();
            }
        }

        return {
            start: start,
            stop: stop,
            refresh: run,
        };
    }

    // ===== 公开 API =====
    return {
        CACHE_TTL: CACHE_TTL,
        createPoller: createPoller,

        /** 清除所有缓存 */
        clearAll() { _cache.clear(); },

        /** 清除指定前缀的缓存 */
        clearByPrefix(prefix) {
            for (const key of _cache.keys()) {
                if (key.startsWith(prefix)) _cache.delete(key);
            }
        },

        // ===== 指数 API =====

        /** 获取市场指数列表 */
        getMarketIndices(useCache) {
            return _withCache('marketIndices', CACHE_TTL.marketIndices,
                () => _request('/api/index/market'), useCache);
        },

        /** 获取行业指数列表 */
        getIndustryIndices(limit, useCache) {
            return _withCache(
                _getCacheKey('industryIndices', limit || 10000),
                CACHE_TTL.industryIndices,
                () => _request('/api/index/industry', { params: { limit: limit || 10000 } }),
                useCache
            );
        },

        /**
         * 获取 K 线数据(10 分钟缓存,切换周期/指标时命中缓存)
         * @param {string} code - 指数代码
         * @param {number} days - 请求天数(含预热天数)
         * @param {boolean} force - 强制跳过缓存
         * @param {string} [period] - K线周期: 'day'(日K)/'week'(周K)/'month'(月K),默认 'day'
         */
        getKline(code, days, force, period) {
            const p = period || 'day';
            return _withCache(
                _getCacheKey('kline', code, days, p),
                CACHE_TTL.kline,
                () => _request('/api/index/kline', { params: { code: code, days: days, period: p } }),
                !force
            );
        },

        /** 获取轮动分析数据 */
        getRotation(useCache) {
            return _withCache('rotation', CACHE_TTL.rotation,
                () => _request('/api/index/rotation'), useCache);
        },

        /**
         * 获取轮动历史排名趋势（5min 缓存，用于 bump chart）
         * @param {number} days - 查询天数（7-90，默认 30）
         * @param {boolean} useCache - 是否使用缓存
         */
        getRotationHistory(days, useCache) {
            const d = days || 30;
            return _withCache(
                _getCacheKey('rotationHistory', d),
                CACHE_TTL.rotationHistory,
                () => _request('/api/index/rotation/history', { params: { days: d } }),
                useCache
            );
        },

        /** 获取数据完整性质量指标 */
        getDataQuality(useCache) {
            return _withCache('dataQuality', CACHE_TTL.industryIndices,
                () => _request('/api/index/data-quality'), useCache);
        },

        /** 触发指数数据获取(POST) */
        triggerFetch() {
            return _request('/api/index/trigger-fetch', { method: 'POST' });
        },

        /** 获取主力资金流 */
        getFundFlow(indicator, useCache) {
            return _withCache(
                _getCacheKey('fundFlow', indicator),
                CACHE_TTL.fundFlow,
                () => _request('/api/index/fund-flow', { params: { indicator: indicator } }),
                useCache
            );
        },

        /** 获取市场情绪指标（涨跌停统计） */
        getSentiment(useCache) {
            return _withCache('sentiment', CACHE_TTL.sentiment,
                () => _request('/api/index/sentiment'), useCache);
        },

        /** 获取北向资金每日净流入（沪深港通，60s 缓存） */
        getNorthbound(days, useCache) {
            const d = days || 30;
            return _withCache(
                `northbound_${d}`,
                CACHE_TTL.sentiment,
                () => _request('/api/northbound', { params: { days: d } }),
                useCache
            );
        },

        // ===== 数据源 API =====

        /** 获取数据源状态 */
        getSourceStatus(useCache) {
            return _withCache('sourceStatus', CACHE_TTL.sourceStatus,
                () => _request('/api/status'), useCache);
        },

        /** 刷新单个数据源(POST,清除状态缓存) */
        refreshSource(source) {
            _cache.delete('sourceStatus');
            return _request(`/api/refresh/${source}`, { method: 'POST' });
        },

        /** 刷新全部数据源(POST,清除状态缓存) */
        refreshAllSources() {
            _cache.delete('sourceStatus');
            return _request('/api/refresh-all', { method: 'POST' });
        },

        // ===== 通用数据 API =====

        /** 按日期范围获取数据 */
        getDataByDateRange(startDate, endDate, useCache) {
            return _withCache(
                _getCacheKey('dataByDate', startDate, endDate),
                CACHE_TTL.dataByDate,
                () => _request('/api/data', { params: { start_date: startDate, end_date: endDate } }),
                useCache
            );
        },

        /** 搜索 */
        search(query, source, limit, useCache) {
            return _withCache(
                _getCacheKey('search', query, source, limit),
                CACHE_TTL.search,
                () => _request('/api/search', { params: { q: query, source: source || '', limit: limit || 100 } }),
                useCache
            );
        },
    };
})();
