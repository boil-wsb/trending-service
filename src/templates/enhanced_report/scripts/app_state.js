/**
 * 应用状态命名空间 - 借鉴 stock-dashboard App.state 设计
 *
 * 将分散在各 JS 文件的全局变量收敛到统一状态对象，提供：
 * 1. 路径式读写：App.get('kline.code') / App.set('kline.indicator', 'rsi')
 * 2. 变更订阅：App.subscribe('kline.indicator', callback)
 * 3. 状态快照：App.snapshot() 用于调试
 *
 * 设计原则：
 * - 不破坏现有 let/var 全局变量，二者并行运行
 * - 新代码优先使用 App.state，旧代码可逐步迁移
 * - 订阅回调在 set 时同步触发（微任务批量化留待后续优化）
 */
const App = (function () {
    'use strict';

    // ===== 结构化状态树 =====
    // 命名空间划分：view(导航) / kline(K线) / data(数据缓存) / ui(UI状态)
    const _state = {
        view: {
            current: 'overview',       // 当前导航 Tab
            source: 'all',             // 当前数据源
            category: 'all',           // 数据源分类
            industryTab: 'industry',   // 行业指数 Tab: 'industry' | 'concept'
        },
        kline: {
            code: '',                  // 当前 K 线代码
            name: '',                  // 当前 K 线名称
            indicator: 'macd',         // 当前技术指标
            displayDays: 60,           // 显示天数
        },
        data: {
            industryIndices: [],       // 行业指数全量数据
            rotation: null,            // 轮动分析数据
            rotationByCode: {},        // 按 code 索引的轮动数据
            marketIndices: [],         // 市场指数缓存
            sourceStatus: {},          // 数据源状态缓存
            reportData: {},            // 报告全量数据
        },
        ui: {
            industrySortField: 'followed',  // 行业指数排序字段
            industrySortOrder: 'desc',      // 排序方向
            dashboardFilter: 'all',         // 仪表盘筛选
            dashboardSort: 'hot',           // 仪表盘排序
            dateRange: { start: null, end: null }, // 日期范围
            isRefreshing: false,            // 数据源刷新锁
            wordCloudRendered: false,       // 词云渲染标记
            theme: 'light',                // 当前主题
        },
    };

    // ===== 订阅注册表 =====
    // key = 路径前缀, value = Set<callback>
    const _subscribers = new Map();

    // ===== 路径解析 =====
    // 'kline.code' → ['kline', 'code']
    function _parsePath(path) {
        return path.split('.');
    }

    // 按路径读取值（不存在返回 undefined）
    function _getByPath(obj, parts) {
        let cur = obj;
        for (let i = 0; i < parts.length; i++) {
            if (cur == null) return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    // 按路径设置值（中间节点不存在时自动创建空对象）
    function _setByPath(obj, parts, value) {
        let cur = obj;
        for (let i = 0; i < parts.length - 1; i++) {
            if (cur[parts[i]] == null || typeof cur[parts[i]] !== 'object') {
                cur[parts[i]] = {};
            }
            cur = cur[parts[i]];
        }
        cur[parts[parts.length - 1]] = value;
    }

    // ===== 通知订阅者 =====
    // 精确匹配 + 父路径匹配（订阅 'kline' 可收到 'kline.code' 的变更）
    function _notify(path, newValue, oldValue) {
        // 精确路径订阅
        const exact = _subscribers.get(path);
        if (exact) {
            exact.forEach(cb => {
                try { cb(newValue, oldValue, path); } catch (e) { console.error('[App] subscribe error:', e); }
            });
        }
        // 父路径订阅（path 的祖先路径）
        const parts = _parsePath(path);
        for (let i = parts.length - 1; i > 0; i--) {
            const prefix = parts.slice(0, i).join('.');
            const subs = _subscribers.get(prefix);
            if (subs) {
                subs.forEach(cb => {
                    try { cb(newValue, oldValue, path); } catch (e) { console.error('[App] subscribe error:', e); }
                });
            }
        }
    }

    // ===== 公开 API =====
    return {
        state: _state,

        /**
         * 按路径读取状态值
         * @param {string} path - 点分隔路径，如 'kline.code'
         * @returns {*} 状态值（不存在返回 undefined）
         */
        get(path) {
            return _getByPath(_state, _parsePath(path));
        },

        /**
         * 按路径设置状态值并通知订阅者
         * @param {string} path - 点分隔路径
         * @param {*} value - 新值
         */
        set(path, value) {
            const parts = _parsePath(path);
            const oldValue = _getByPath(_state, parts);
            _setByPath(_state, parts, value);
            // 值未变化时不通知（浅比较，对象引用变化即通知）
            if (oldValue !== value) {
                _notify(path, value, oldValue);
            }
        },

        /**
         * 订阅路径变更（支持父路径通配）
         * @param {string} path - 订阅路径，如 'kline' 可收到 'kline.code' 的变更
         * @param {function} callback - (newValue, oldValue, fullpath) => void
         * @returns {function} 取消订阅函数
         */
        subscribe(path, callback) {
            if (!_subscribers.has(path)) {
                _subscribers.set(path, new Set());
            }
            _subscribers.get(path).add(callback);
            // 返回取消订阅函数
            return function unsubscribe() {
                const set = _subscribers.get(path);
                if (set) {
                    set.delete(callback);
                    if (set.size === 0) _subscribers.delete(path);
                }
            };
        },

        /**
         * 批量更新多个路径（只触发一次通知 per path）
         * @param {object} updates - { 'path1': value1, 'path2': value2 }
         */
        batch(updates) {
            for (const path in updates) {
                App.set(path, updates[path]);
            }
        },

        /**
         * 生成状态快照（深拷贝，用于调试）
         * @returns {object} 状态深拷贝
         */
        snapshot() {
            return JSON.parse(JSON.stringify(_state));
        },

        /**
         * 重置状态到默认值
         */
        reset() {
            _state.view = { current: 'overview', source: 'all', category: 'all', industryTab: 'industry' };
            _state.kline = { code: '', name: '', indicator: 'macd', displayDays: 60 };
            _state.data = { industryIndices: [], rotation: null, rotationByCode: {}, marketIndices: [], sourceStatus: {}, reportData: {} };
            _state.ui = { industrySortField: 'followed', industrySortOrder: 'desc', dashboardFilter: 'all', dashboardSort: 'hot', dateRange: { start: null, end: null }, isRefreshing: false, wordCloudRendered: false, theme: 'light' };
        },
    };
})();
