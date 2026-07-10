/**
 * Chart.js 配置预设 - 借鉴 stock-dashboard ChartPresets 工厂设计
 *
 * 抽取 6 个 new Chart() 中重复的配置，提供三层预设 + 颜色常量。
 * 现有图表不强制迁移，新图表优先使用预设。
 *
 * 预设层次：
 * 1. base    — 全部图表共用（responsive + maintainAspectRatio）
 * 2. synced  — K线/指标/成交量三图联动（interaction.index + onHover + tooltip）
 * 3. trend   — 趋势图（legend + scales + grid）
 *
 * 用法示例：
 *   const cfg = ChartPresets.trend();
 *   cfg.data = { datasets: [...] };
 *   new Chart(ctx, cfg);
 */
const ChartPresets = (function () {
    'use strict';

    // ===== 颜色常量（兜底默认值，实际使用应调用 getThemeColors() 读 CSS 变量）=====
    const COLORS = {
        up: '#e74c3c',           // 红涨（A股惯例）
        upAlpha: 'rgba(231,76,60,0.6)',
        down: '#27ae60',         // 绿跌
        downAlpha: 'rgba(39,174,96,0.6)',
        flat: '#95a5a6',         // 平盘/参考灰
        flatAlpha: 'rgba(128,128,128,0.4)',
        ma: '#9b59b6',           // MA 紫色
        orange: '#f39c12',       // BOLL/DEA 橙色
        orangeDark: '#e67e22',   // 深橙
        blue: '#3b82f6',         // 蓝色强调
        gridLight: 'rgba(0,0,0,0.05)',  // 浅网格线
        gridDark: 'rgba(255,255,255,0.06)', // 暗色网格线
        tickGray: 'rgba(127,140,141,0.85)', // 灰色刻度文字
        // 趋势图 5 色调色板
        palette5: ['#667eea', '#f093fb', '#43e97b', '#ff6b6b', '#feca57'],
    };

    // ===== 从 CSS 变量读取主题色（借鉴 stock-dashboard BoardDetail.tsx L209-280）=====
    // 每次调用都重新读取，确保主题切换后图表自动跟随
    function _cssVar(name, fallback) {
        const v = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    }

    function getThemeColors() {
        // 确保所有颜色值为字符串，避免 Chart.js 处理非字符串时 t.toString 报错
        return {
            rise: String(_cssVar('--color-rise', COLORS.up)),
            fall: String(_cssVar('--color-fall', COLORS.down)),
            flat: String(_cssVar('--color-flat', COLORS.flat)),
            riseAlpha: (a) => `rgba(${_cssVar('--color-rise-rgb', '231, 76, 60')}, ${a})`,
            fallAlpha: (a) => `rgba(${_cssVar('--color-fall-rgb', '39, 174, 96')}, ${a})`,
            ma5: String(_cssVar('--color-ma5', '#9b59b6')),
            ma10: String(_cssVar('--color-ma10', '#e67e22')),
            ma20: String(_cssVar('--color-ma20', '#1abc9c')),
            ma60: String(_cssVar('--color-ma60', '#34495e')),
            bollMid: String(_cssVar('--color-boll-mid', '#f39c12')),
            macdCross: String(_cssVar('--color-macd-cross', '#c0392b')),
            maCross: String(_cssVar('--color-ma-cross', '#2471a3')),
        };
    }

    // ===== line dataset 默认值（MA 系列 + 指标线共用）=====
    const lineDatasetDefaults = {
        borderWidth: 1.5,
        fill: false,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 3,
    };

    // ===== 第一层：基础预设（全部 6 图共用）=====
    function base() {
        return {
            responsive: true,
            maintainAspectRatio: false,
        };
    }

    // ===== 第二层：联动图表预设（K线/指标/成交量三图）=====
    // 需要 handleChartHover 回调（由 indicators.js 定义）
    function synced(chartRef) {
        return Object.assign(base(), {
            interaction: { mode: 'index', intersect: false },
            onHover: function (event, elements) {
                if (typeof handleChartHover === 'function') {
                    handleChartHover(chartRef, event);
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false,
                },
            },
            events: ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove'],
        });
    }

    // ===== 第三层：趋势图预设（core.js 两图共用）=====
    function trend() {
        return Object.assign(base(), {
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { usePointStyle: true, padding: 15 },
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: COLORS.gridLight },
                },
                x: {
                    grid: { display: false },
                },
            },
        });
    }

    // ===== 工具：格式化数字单位（万/亿）=====
    function formatVolume(val) {
        if (val >= 1e8) return (val / 1e8).toFixed(2) + '亿';
        if (val >= 1e4) return (val / 1e4).toFixed(2) + '万';
        return val.toString();
    }

    // ===== 工具：日期转星期（三图 tooltip 共用）=====
    function dateToWeekday(dateStr) {
        const days = ['日', '一', '二', '三', '四', '五', '六'];
        const d = new Date(dateStr);
        return isNaN(d) ? '' : '周' + days[d.getDay()];
    }

    return {
        COLORS: COLORS,
        getThemeColors: getThemeColors,
        lineDatasetDefaults: lineDatasetDefaults,
        base: base,
        synced: synced,
        trend: trend,
        formatVolume: formatVolume,
        dateToWeekday: dateToWeekday,
    };
})();
