// ========= 主力资金 =========

// ── 主力资金净流入排行（中轴双向蝴蝶图）───────────────────
let fundFlowChart = null;

// 背离信号: 1=健康上涨 2=出货 3=吸筹 4=弱势
const FUND_SIG_MAP = { 1: '✅健康', 2: '⚠️出货', 3: '📥吸筹', 4: '❌弱势' };
const FUND_SIG_CLS = { 1: 'val-up', 2: 'val-down', 3: 'val-up', 4: 'val-down' };

function switchFundFlow(indicator) {
    // 更新按钮状态
    document.querySelectorAll('.fund-flow-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.indicator === indicator);
    });
    loadFundFlow(indicator);
}

async function loadFundFlow(indicator) {
    try {
        const data = await DataService.getFundFlow(indicator);
        renderFundFlowChart(data.items || []);
        renderFundFlowTable(data.items || []);
        window._fundFlowLoaded = true;   // 仅成功才置位，失败允许重试
    } catch (err) {
        console.error('主力资金加载失败:', err);
        window._fundFlowLoaded = false;  // 失败不置位，切走切回/切周期可自动重试
        renderFundFlowError();
    }
}

// 加载失败时显示友好提示（避免整块空白无任何反馈）
function renderFundFlowError() {
    const wrap = document.getElementById('fund-flow-chart-wrap');
    const tbody = document.getElementById('fund-flow-tbody');
    const tip = '⚠️ 主力资金数据源暂时不可用（可能为非交易时段或接口波动），点击上方「今日/5日/10日」按钮即可重试';
    if (wrap) {
        wrap.innerHTML = `<div class="index-loading" style="padding:32px;">${tip}</div>`;
    }
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="6" class="index-loading">⚠️ 数据源暂时不可用</td></tr>';
    }
}

function renderFundFlowChart(items) {
    const canvas = document.getElementById('fund-flow-canvas');
    if (!canvas || !items.length) return;
    if (fundFlowChart) fundFlowChart.destroy();

    // 蝴蝶图数据: 流入Top8 + 流出Top8; 流入在上(降序), 流出在下(按绝对值降序)
    const inflow = items.filter(d => (d.main_in_flow || 0) >= 0)
        .sort((a, b) => (b.main_in_flow || 0) - (a.main_in_flow || 0)).slice(0, 8);
    const outflow = items.filter(d => (d.main_in_flow || 0) < 0)
        .sort((a, b) => (a.main_in_flow || 0) - (b.main_in_flow || 0)).slice(0, 8);
    const sorted = [...inflow, ...outflow];

    // 左右共用同一比例尺, ×1.2 留白保证外端标签不溢出
    const maxVal = Math.max(...sorted.map(d => Math.abs(d.main_in_flow || 0) / 100000000)) * 1.2;

    // 用 HTML 中轴双向条形图(蝴蝶图): 流入向右延伸, 流出向左延伸
    const chartWrap = document.getElementById('fund-flow-chart-wrap');
    if (chartWrap) {
        const tc = ChartPresets.getThemeColors();
        const rows = sorted.map(d => {
            const val = (d.main_in_flow || 0) / 100000000;
            const pct = Math.min(Math.abs(val) / maxVal * 100, 100);
            const isIn = val >= 0;
            const tip = `${isIn ? '+' : ''}${val.toFixed(1)}`;
            const cp = d.change_pct;
            // hover 明细提示（沿用项目原生 title 惯例）
            const title = [
                d.name,
                `主力净流入: ${tip}亿`,
                `涨跌幅: ${cp != null ? (cp >= 0 ? '+' : '') + cp.toFixed(2) + '%' : '--'}`,
                `流入比: ${d.inflow_ratio != null ? d.inflow_ratio.toFixed(1) + '%' : '--'}`,
                `信号: ${FUND_SIG_MAP[d.divergence || 4] || '--'}`
            ].join('\n');
            const bar = `<div class="fund-bar-fill ${isIn ? 'bar-in' : 'bar-out'}" style="
                width:${pct.toFixed(1)}%;
                background:${isIn ? tc.riseAlpha(0.7) : tc.fallAlpha(0.5)};
            "></div>`;
            const tipHtml = `<span class="fund-bar-tip ${isIn ? 'val-up' : 'val-down'}">${tip}</span>`;
            return `<div class="fund-bar-row" title="${title}">
                <div class="fund-bar-label">${d.name}</div>
                <div class="fund-bar-track">
                    <div class="fund-bar-half fund-bar-left">${isIn ? '' : tipHtml + bar}</div>
                    <div class="fund-bar-half fund-bar-right">${isIn ? bar + tipHtml : ''}</div>
                </div>
            </div>`;
        }).join('');
        // 中轴旁左右最大刻度提示
        const scaleRow = `<div class="fund-bar-row fund-scale-row">
            <div class="fund-bar-label"></div>
            <div class="fund-bar-track">
                <div class="fund-bar-half fund-scale-left"><span>-${maxVal.toFixed(1)}亿</span></div>
                <div class="fund-bar-half fund-scale-right"><span>+${maxVal.toFixed(1)}亿</span></div>
            </div>
        </div>`;
        chartWrap.innerHTML = scaleRow + '<div class="fund-bar-axis"></div>' + rows;
        layoutFundBarTips();
        bindFundTipRelayout();
        return;  // 用 HTML 条形图，不需要 Chart.js
    }

    // fallback: 用 Chart.js 横向条形图
    const labels = sorted.map(d => d.name);
    const data = sorted.map(d => (d.main_in_flow || 0) / 100000000);
    const tc = ChartPresets.getThemeColors();
    const colors = data.map(v => v >= 0 ? tc.riseAlpha(0.7) : tc.fallAlpha(0.7));
    const borderColors = data.map(v => v >= 0 ? tc.rise : tc.fall);

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

// 条内/条外数值标签自适应: 条形足够宽(≥52px)时数值嵌入条内, 否则置于条形外端
function layoutFundBarTips() {
    const wrap = document.getElementById('fund-flow-chart-wrap');
    if (!wrap) return;
    wrap.querySelectorAll('.fund-bar-half').forEach(half => {
        const fill = half.querySelector('.fund-bar-fill');
        const tip = half.querySelector('.fund-bar-tip');
        if (!fill || !tip) return;
        // 用百分比×半轨宽度换算像素, 不受 width 过渡动画影响
        const pct = parseFloat(fill.style.width) || 0;
        const barPx = half.getBoundingClientRect().width * pct / 100;
        const inside = barPx >= 52;
        fill.classList.toggle('has-tip', inside);
        if (inside && !fill.contains(tip)) {
            fill.appendChild(tip);
        } else if (!inside && fill.contains(tip)) {
            if (half.classList.contains('fund-bar-right')) half.appendChild(tip);
            else half.insertBefore(tip, fill);
        }
    });
}

// 窗口尺寸变化时重新布局数值标签（只绑定一次）
let _fundTipRelayoutBound = false;
function bindFundTipRelayout() {
    if (_fundTipRelayoutBound) return;
    _fundTipRelayoutBound = true;
    let timer = null;
    window.addEventListener('resize', () => {
        clearTimeout(timer);
        timer = setTimeout(layoutFundBarTips, 200);
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
        // 背离信号: 1=健康上涨 2=出货 3=吸筹 4=弱势（复用模块级 FUND_SIG_MAP/FUND_SIG_CLS）
        const sig = d.divergence || 4;
        return `<tr>
            <td>${i + 1}</td>
            <td style="text-align:left">${d.name}</td>
            <td>${fmt(d.main_in_flow)}</td>
            <td>${pctFmt(d.change_pct)}</td>
            <td>${d.inflow_ratio != null ? d.inflow_ratio.toFixed(1) + '%' : '--'}</td>
            <td><span class="${FUND_SIG_CLS[sig]}">${FUND_SIG_MAP[sig] || '--'}</span></td>
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
    if (subview === 'fund-flow' && !window._fundFlowLoaded) {
        loadFundFlow('今日');
        loadNorthbound();
    }
    if (subview === 'heatmap' && !window._heatmapLoaded) {
        loadHeatmapData();
        window._heatmapLoaded = true;
    }
    if (subview === 'sentiment' && !window._sentimentLoaded) {
        loadSentimentData();
        window._sentimentLoaded = true;
    }
}

// ── Tab 切换时加载对应数据 ──────────────────────
function onTabShown(view) {
    if (view === 'index') {
        const activeSub = document.querySelector('.index-sub-tab.active');
        const subview = activeSub ? activeSub.dataset.subview : 'market';
        if (subview === 'fund-flow' && !window._fundFlowLoaded) {
            loadFundFlow('今日');
        }
        if (subview === 'heatmap' && !window._heatmapLoaded) {
            loadHeatmapData();
            window._heatmapLoaded = true;
        }
    }
}


// ── 北向资金（沪深港通）──────────────────────
let northboundChart = null;
let northboundData = null;

async function loadNorthbound() {
    const daysSelect = document.getElementById('nb-days-select');
    const days = daysSelect ? parseInt(daysSelect.value) : 30;
    try {
        northboundData = await DataService.getNorthbound(days);
        renderNorthboundStats(northboundData);
        renderNorthboundChart(northboundData);
    } catch (err) {
        console.error('北向资金加载失败:', err);
    }
}

function renderNorthboundStats(data) {
    const latest = data.latest || {};
    const summary = data.summary || {};

    const fmtVal = (v) => {
        if (v == null || isNaN(v)) return '--';
        const cls = v >= 0 ? 'index-up' : 'index-down';
        const sign = v >= 0 ? '+' : '';
        return `<span class="${cls}">${sign}${v.toFixed(2)}亿</span>`;
    };

    document.getElementById('nb-latest-total').innerHTML = fmtVal(latest.total);
    document.getElementById('nb-latest-sh').innerHTML = fmtVal(latest.sh);
    document.getElementById('nb-latest-sz').innerHTML = fmtVal(latest.sz);
    document.getElementById('nb-total-5d').innerHTML = fmtVal(summary.total_5d);
    document.getElementById('nb-total-20d').innerHTML = fmtVal(summary.total_20d);
}

function renderNorthboundChart(data) {
    const canvas = document.getElementById('northbound-chart');
    if (!canvas || !data || !data.dates || !data.dates.length) return;
    if (northboundChart) northboundChart.destroy();

    const tc = ChartPresets.getThemeColors();
    const datasets = [];

    if (document.getElementById('nb-show-total')?.checked) {
        datasets.push({
            label: '北向合计',
            data: data.total_net_flow,
            borderColor: tc.rise,
            backgroundColor: tc.riseAlpha(0.1),
            borderWidth: 2,
            fill: true,
            tension: 0.3,
        });
    }
    if (document.getElementById('nb-show-sh')?.checked) {
        datasets.push({
            label: '沪股通',
            data: data.sh_net_flow,
            borderColor: '#3498db',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            tension: 0.3,
        });
    }
    if (document.getElementById('nb-show-sz')?.checked) {
        datasets.push({
            label: '深股通',
            data: data.sz_net_flow,
            borderColor: '#9b59b6',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            tension: 0.3,
        });
    }

    northboundChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: { display: true, text: '日期' },
                    ticks: { maxTicksLimit: 15, font: { size: 10 } }
                },
                y: {
                    title: { display: true, text: '净流入(亿)' },
                    grid: { color: ctx => ctx.tick.value === 0 ? '#888' : 'rgba(0,0,0,0.06)' }
                }
            },
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: c => `${c.dataset.label}: ${c.parsed.y >= 0 ? '+' : ''}${c.parsed.y.toFixed(2)}亿`
                    }
                }
            }
        }
    });
}

function updateNorthboundChart() {
    if (northboundData) renderNorthboundChart(northboundData);
}
