// ========= 主力资金 =========

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
        if (subview === 'fund-flow' && !window._fundFlowLoaded) {
            loadFundFlow('今日');
            window._fundFlowLoaded = true;
        }
    }
}
