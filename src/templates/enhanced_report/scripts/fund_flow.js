// ========= 风格轮动 + 北向资金 + 主力资金 =========

// ── 风格轮动 ───────────────────────────────
let styleRadarChart = null;
let styleBarChart = null;

// 沪深300风格指数（可在 stock_zh_index_spot_em 中查到）
const STYLE_NAMES = ['300价值', '300成长', '300信息', '300通信', '300公用', '300金融'];
const STYLE_COLORS = {
    '300价值': '#e74c3c', '300成长': '#27ae60',
    '300信息': '#9b59b6', '300通信': '#3498db',
    '300公用': '#f39c12', '300金融': '#1abc9c',
};

function loadStyleRotation() {
    fetch('/api/index/style-rotation')
        .then(r => r.json())
        .then(json => {
            if (!json.success) throw new Error(json.error);
            renderStyleCharts(json.data);
        })
        .catch(err => console.error('风格轮动加载失败:', err));
}

function renderStyleCharts(data) {
    const { realtime } = data;
    if (!realtime || !realtime.length) {
        // 无数据时用示意数据渲染
        renderStylePlaceholder();
        return;
    }
    // 1) 雷达图：各风格今日涨跌幅
    const radarEl = document.getElementById('style-radar-canvas');
    if (radarEl) {
        if (styleRadarChart) styleRadarChart.destroy();
        const labels = realtime.map(d => d.name);
        const values = realtime.map(d => d.change_pct || 0);
        styleRadarChart = new Chart(radarEl.getContext('2d'), {
            type: 'radar',
            data: {
                labels,
                datasets: [{
                    label: '今日涨跌幅(%)',
                    data: values,
                    fill: true,
                    backgroundColor: 'rgba(155,89,182,0.25)',
                    borderColor: '#9b59b6',
                    borderWidth: 2,
                    pointBackgroundColor: labels.map(n => STYLE_COLORS[n] || '#9b59b6'),
                    pointBorderColor: '#fff',
                    pointRadius: 5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: {
                        label: ctx => `${ctx.label}: ${ctx.parsed.r >= 0 ? '+' : ''}${ctx.parsed.r.toFixed(2)}%`
                    }}
                },
                scales: {
                    r: {
                        min: -5,
                        max: 3,
                        ticks: { stepSize: 1 },
                        pointLabels: { font: { size: 12 } },
                    }
                }
            }
        });
    }

    // 2) 分组条形图：价值 vs 成长（用300价值/300成长对比）
    const barEl = document.getElementById('style-bar-canvas');
    if (barEl) {
        if (styleBarChart) styleBarChart.destroy();
        // 配对：价值类 vs 成长类
        const pairs = [
            { a: '300价值', b: '300成长' },
            { a: '300信息', b: '300通信' },
        ];
        const barLabels = pairs.map(p => p.a.replace('300',''));
        const aValues = pairs.map(p => {
            const d = realtime.find(x => x.name === p.a);
            return d ? d.change_pct || 0 : 0;
        });
        const bValues = pairs.map(p => {
            const d = realtime.find(x => x.name === p.b);
            return d ? d.change_pct || 0 : 0;
        });
        styleBarChart = new Chart(barEl.getContext('2d'), {
            type: 'bar',
            data: {
                labels: barLabels,
                datasets: [
                    {
                        label: '价值/信息',
                        data: aValues,
                        backgroundColor: 'rgba(231,76,60,0.7)',
                        borderColor: '#e74c3c',
                        borderWidth: 1,
                    },
                    {
                        label: '成长/通信',
                        data: bValues,
                        backgroundColor: 'rgba(39,174,96,0.7)',
                        borderColor: '#27ae60',
                        borderWidth: 1,
                    },
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    tooltip: { callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                    }}
                },
                scales: {
                    y: { title: { display: true, text: '涨跌幅(%)' }, min: -5, max: 3 },
                }
            }
        });
    }

    // 3) 图例
    const legendEl = document.getElementById('style-legend');
    if (legendEl) {
        legendEl.innerHTML = STYLE_NAMES.map(n =>
            `<span class="style-legend-item">
                <span class="style-legend-dot" style="background:${STYLE_COLORS[n]}"></span>
                ${n}
            </span>`
        ).join('');
    }
}

function renderStylePlaceholder() {
    // 无数据时显示提示
    const legendEl = document.getElementById('style-legend');
    if (legendEl) {
        legendEl.innerHTML = '<span style="color:#999;font-size:13px;">风格指数数据暂不可用，请稍后重试</span>';
    }
}


// ── 北向资金 ─────────────────────────────────
let northboundChart = null;

function loadNorthbound() {
    fetch('/api/index/northbound?days=30')
        .then(r => r.json())
        .then(json => {
            if (!json.success) throw new Error(json.error);
            renderNorthbound(json.data);
        })
        .catch(err => console.error('北向资金加载失败:', err));
}

function renderNorthbound(data) {
    const { summary, history, streak } = data;
    if (!summary && (!history || !history.length)) return;

    // 汇总卡片（含连续流入天数）
    if (summary) {
        const el = id => document.getElementById(id);
        const fmt = v => {
            if (v == null) return '--';
            const y = v / 100000000;
            const sign = y >= 0 ? '+' : '';
            return `<span class="${y >= 0 ? 'val-up' : 'val-down'}">${sign}${y.toFixed(2)}亿</span>`;
        };
        const todayEl = el('north-today-value');
        const shEl = el('north-sh-value');
        const szEl = el('north-sz-value');
        const cumEl = el('north-cumulative');
        if (todayEl) todayEl.innerHTML = fmt(summary.north_in_flow);
        if (shEl) shEl.innerHTML = fmt(summary.sh_in_flow);
        if (szEl) szEl.innerHTML = fmt(summary.sz_in_flow);
        if (cumEl && summary.cumulative_in_flow !== undefined)
            cumEl.innerHTML = fmt(summary.cumulative_in_flow);
    }

    // 连续流入/流出天数
    const streakEl = document.getElementById('north-streak');
    if (streakEl && streak) {
        const typeMap = { 'in': '连续流入', 'out': '连续流出', 'flat': '持平', 'unknown': '--' };
        const clsMap = { 'in': 'val-up', 'out': 'val-down', 'flat': 'val-flat', 'unknown': '' };
        streakEl.innerHTML = `<span class="${clsMap[streak.streak_type] || ''}">${typeMap[streak.streak_type] || '--'} ${streak.streak_days} 天</span>`;
    }

    // 趋势折线图（叠加沪深300）
    const trendEl = document.getElementById('northbound-trend-canvas');
    if (!trendEl || !history || !history.length) return;
    if (northboundChart) northboundChart.destroy();

    const labels = history.map(h => h.date);
    const totalData = history.map(h => h.north_in_flow != null ? h.north_in_flow / 100000000 : null);
    const hs300Data = history.map(h => h.hs300_pct != null ? h.hs300_pct : null);

    northboundChart = new Chart(trendEl.getContext('2d'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '北向净流入(亿)',
                    data: totalData,
                    borderColor: '#4a90d9',
                    backgroundColor: 'rgba(74,144,217,0.15)',
                    fill: true, tension: 0.2,
                    pointRadius: 0, borderWidth: 2, yAxisID: 'y',
                },
                {
                    label: '沪深300涨跌幅(%)',
                    data: hs300Data,
                    borderColor: '#f39c12',
                    backgroundColor: 'rgba(243,156,18,0.08)',
                    fill: false, tension: 0.2,
                    pointRadius: 0, borderWidth: 1.5, yAxisID: 'y1',
                    borderDash: [4, 2],
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        title: its => its.length ? its[0].label : '',
                        label: ctx => {
                            const v = ctx.parsed.y;
                            if (v == null) return null;
                            const unit = ctx.dataset.yAxisID === 'y' ? '亿' : '%';
                            const sign = v >= 0 ? '+' : '';
                            return `${ctx.dataset.label}: ${sign}${v.toFixed(2)}${unit}`;
                        }
                }
                }
            },
            scales: {
                x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 15 } },
                y: {
                    title: { display: true, text: '北向净流入(亿)' },
                    position: 'left',
                },
                y1: {
                    title: { display: true, text: '沪深300(%)' },
                    position: 'right',
                    grid: { drawOnChartArea: false },
                },
            }
        }
    });
}


// ── 主力资金净流入排行（双向条形图）───────────────────
let fundFlowChart = null;

function switchFundFlow(indicator) {
    // 更新按钮状态
    document.querySelectorAll('.fund-flow-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.indicator === indicator);
    });
    loadFundFlow(indicator);
}

function loadFundFlow(indicator) {
    fetch(`/api/index/fund-flow?indicator=${indicator}`)
        .then(r => r.json())
        .then(json => {
            if (!json.success) throw new Error(json.error);
            renderFundFlowChart(json.data.items || []);
            renderFundFlowTable(json.data.items || []);
        })
        .catch(err => console.error('主力资金加载失败:', err));
}

function renderFundFlowChart(items) {
    const canvas = document.getElementById('fund-flow-canvas');
    if (!canvas || !items.length) return;
    if (fundFlowChart) fundFlowChart.destroy();

    // 取前12名，按净流入排序
    const sorted = [...items].sort((a, b) =>
        Math.abs(b.main_in_flow || 0) - Math.abs(a.main_in_flow || 0)
    ).slice(0, 12).reverse();  // reverse 使最大在最上方

    const maxVal = Math.max(...sorted.map(d => Math.abs(d.main_in_flow || 0) / 100000000)) * 1.2;

    // 用 HTML 条形图代替 Chart.js（参照 dashboard.html 样式）
    const chartWrap = document.getElementById('fund-flow-chart-wrap');
    if (chartWrap) {
        chartWrap.innerHTML = sorted.map(d => {
            const val = (d.main_in_flow || 0) / 100000000;
            const pct = (Math.abs(val) / maxVal * 100).toFixed(1);
            const isIn = val >= 0;
            const cls = isIn ? 'val-up' : 'val-down';
            const bg = isIn ? 'rgba(231,76,60,0.7)' : 'rgba(39,174,96,0.5)';
            return `<div class="fund-bar-row">
                <div class="fund-bar-label">${d.name}</div>
                <div class="fund-bar-track">
                    <div class="fund-bar-fill ${isIn ? 'bar-in' : 'bar-out'}" style="
                        width:${pct}%;
                        background:${bg};
                    ">${Math.abs(val) >= 1 ? (isIn ? '+' : '') + val.toFixed(1) : ''}</div>
                </div>
                <div class="fund-bar-val ${cls}">${val >= 0 ? '+' : ''}${val.toFixed(1)}</div>
            </div>`;
        }).join('');
        return;  // 用 HTML 条形图，不需要 Chart.js
    }

    // fallback: 用 Chart.js 横向条形图
    const labels = sorted.map(d => d.name);
    const data = sorted.map(d => (d.main_in_flow || 0) / 100000000);
    const colors = data.map(v => v >= 0 ? 'rgba(231,76,60,0.7)' : 'rgba(39,174,96,0.7)');
    const borderColors = data.map(v => v >= 0 ? '#e74c3c' : '#27ae60');

    fundFlowChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '主力净流入(亿)',
                data,
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1,
                barThickness: 18,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.x;
                            return `主力净流入: ${v >= 0 ? '+' : ''}${v.toFixed(2)}亿`;
                        }
                }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: '净流入(亿) 红=流入 绿=流出' },
                    grid: { color: ctx => ctx.tick.value === 0 ? '#888' : 'rgba(0,0,0,0.08)' },
                },
                y: { ticks: { font: { size: 11 } } },
            }
        }
    });
}

function renderFundFlowTable(items) {
    const tbody = document.getElementById('fund-flow-tbody');
    if (!tbody) return;
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="index-loading">暂无数据</td></tr>';
        return;
    }
    // 按主力净流入降序
    const sorted = [...items].sort((a, b) =>
        (b.main_in_flow || 0) - (a.main_in_flow || 0)
    );
    tbody.innerHTML = sorted.map((d, i) => {
        const fmt = v => {
            if (v == null) return '--';
            const y = v / 100000000;
            const cls = y >= 0 ? 'val-up' : 'val-down';
            const sign = y >= 0 ? '+' : '';
            return `<span class="${cls}">${sign}${y.toFixed(2)}</span>`;
        };
        const pctFmt = v => {
            if (v == null) return '--';
            const cls = v >= 0 ? 'val-up' : 'val-down';
            const sign = v >= 0 ? '+' : '';
            return `<span class="${cls}">${sign}${v.toFixed(2)}%</span>`;
        };
        // 背离信号: 1=健康上涨 2=出货 3=吸筹 4=弱势
        const sigMap = { 1: '✅健康', 2: '⚠️出货', 3: '📥吸筹', 4: '❌弱势' };
        const sigCls = { 1: 'val-up', 2: 'val-down', 3: 'val-up', 4: 'val-down' };
        const sig = d.divergence || 4;
        return `<tr>
            <td>${i + 1}</td>
            <td style="text-align:left">${d.name}</td>
            <td>${fmt(d.main_in_flow)}</td>
            <td>${pctFmt(d.change_pct)}</td>
            <td>${d.inflow_ratio != null ? d.inflow_ratio.toFixed(1) + '%' : '--'}</td>
            <td><span class="${sigCls[sig]}">${sigMap[sig] || '--'}</span></td>
        </tr>`;
    }).join('');
}



// ── 指数子视图切换 ──────────────────────
function switchIndexSubView(subview) {
    document.querySelectorAll('.index-sub-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.subview === subview);
    });
    document.querySelectorAll('.index-sub-content').forEach(el => {
        el.classList.toggle('active', el.id === 'index-' + subview);
    });
    if (subview === 'style-north' && !window._styleLoaded) {
        loadStyleRotation();
        loadNorthbound();
        window._styleLoaded = true;
    }
    if (subview === 'fund-flow' && !window._fundFlowLoaded) {
        loadFundFlow('今日');
        window._fundFlowLoaded = true;
    }
}

// ── Tab 切换时加载对应数据 ──────────────────────
function onTabShown(view) {
    if (view === 'index') {
        const activeSub = document.querySelector('.index-sub-tab.active');
        const subview = activeSub ? activeSub.dataset.subview : 'market';
        if (subview === 'style-north' && !window._styleLoaded) {
            loadStyleRotation();
            loadNorthbound();
            window._styleLoaded = true;
        }
        if (subview === 'fund-flow' && !window._fundFlowLoaded) {
            loadFundFlow('今日');
            window._fundFlowLoaded = true;
        }
    }
}
