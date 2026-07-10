        // ========== 指数行情相关 ==========
        let industryIndicesData = [];
        let industrySortField = 'followed';
        let industrySortOrder = 'desc';
        // 当前 Tab：'industry'（申万行业指数） / 'concept'（概念板块）
        let currentIndustryTab = 'industry';
        // 智能筛选条件（不影响原始数据，仅影响渲染）
        let screenerFilters = {
            trends: [],          // 趋势状态：strong_bull / weak_bull / sideways / weak_bear / strong_bear
            crossovers: [],      // 金叉信号：macd:golden / ma:golden / macd:near_golden / ma:near_golden / none
            changePctToday: { min: null, max: null },
            changePct3d: { min: null, max: null },
            changePct7d: { min: null, max: null },
            turnoverRate: { min: null, max: null },
            momentum: { min: null, max: null }
        };
        let currentKlineCode = '';
        let currentKlineName = '';
        let klineChart = null;
        let currentIndicator = 'macd';
        let indicatorChart = null;
        let volumeChart = null;
        let currentKlineData = null;  // 切片后的显示窗口数据（副图/风险指标用）
        let allKlineData = null;      // 完整历史数据（含预热期，主图 MA/BOLL 计算用）
        let allCrossoverData = null;  // 完整金叉点数据
        let currentDisplayDays = 30;  // 当前显示天数
        let currentKlinePeriod = 'day';  // 固定日K模式
        let _lastHoverX = null;       // 鼠标 x 位置（主图 onHover 或副图联动时记录，tooltip callback 使用）
        let marketComparisonData = null;
        let dataQualityData = null;

        // 板块对比选中列表（存储 {code, name} 对象数组，最多 4 个）
        let compareSelectedSectors = [];
        // 对比图表实例
        let compareChart = null;
        // 对比图表线条颜色（4色，区分各板块）
        const COMPARE_COLORS = ['#e74c3c', '#3498db', '#9b59b6', '#f39c12'];
        // Mansfield RS 基准指数代码（沪深300）
        const RS_BENCHMARK_CODE = '000300';

        // 关注列表管理（localStorage 持久化）
        const FOLLOWED_STORAGE_KEY = 'trending_followed_indices';

        function getFollowedIndices() {
            try {
                const data = localStorage.getItem(FOLLOWED_STORAGE_KEY);
                return data ? JSON.parse(data) : [];
            } catch (e) {
                return [];
            }
        }

        function isIndexFollowed(code) {
            return getFollowedIndices().includes(code);
        }

        function toggleFollowIndex(code) {
            let followed = getFollowedIndices();
            if (followed.includes(code)) {
                followed = followed.filter(c => c !== code);
            } else {
                followed.push(code);
            }
            try {
                localStorage.setItem(FOLLOWED_STORAGE_KEY, JSON.stringify(followed));
            } catch (e) {
                console.error('保存关注列表失败:', e);
            }
            renderIndustryIndices();
        }

        // 获取涨跌样式类（A股惯例：红涨绿跌）
        function formatChangeClass(changePct) {
            if (changePct > 0) return 'index-up';
            if (changePct < 0) return 'index-down';
            return 'index-flat';
        }

        // 格式化涨跌文本
        function formatChangeText(change, changePct) {
            const sign = change >= 0 ? '+' : '';
            return `${sign}${change.toFixed(2)} (${sign}${changePct.toFixed(2)}%)`;
        }

        // 格式化金叉徽章（用于市场指数卡片）
        function formatCrossoverBadge(crossover) {
            if (!crossover) return '';
            const badges = [];
            if (crossover.macd === 'golden') {
                badges.push('<span class="crossover-badge macd-golden" title="MACD金叉：DIF上穿DEA">MACD金叉</span>');
            } else if (crossover.macd === 'near_golden') {
                badges.push('<span class="crossover-badge macd-near" title="MACD即将金叉：DIF接近DEA">MACD即将金叉</span>');
            }
            if (crossover.ma === 'golden') {
                badges.push('<span class="crossover-badge ma-golden" title="MA金叉：MA5上穿MA10">MA金叉</span>');
            } else if (crossover.ma === 'near_golden') {
                badges.push('<span class="crossover-badge ma-near" title="MA即将金叉：MA5接近MA10">MA即将金叉</span>');
            }
            return badges.length ? `<div class="crossover-badges">${badges.join('')}</div>` : '';
        }

        // 格式化金叉文本（用于行业指数表格）—— 合并金叉信号 + 趋势状态
        function formatCrossoverText(crossover) {
            if (!crossover) return '<span class="crossover-none">-</span>';
            const texts = [];
            // 趋势状态（优先显示，从强到弱）
            if (crossover.trend) {
                const t = crossover.trend.trend;
                const adx = crossover.trend.adx;
                const trendMap = {
                    'strong_bull': { text: '强多头', cls: 'trend-strong-bull', title: 'MA5>MA10>MA20>MA60 完整多头排列' },
                    'weak_bull':   { text: '弱多头', cls: 'trend-weak-bull',   title: '价格>MA20，均线部分多头' },
                    'sideways':    { text: '震荡',   cls: 'trend-sideways',    title: '均线交织，无明确方向' },
                    'weak_bear':   { text: '弱空头', cls: 'trend-weak-bear',   title: '价格<MA20，均线部分空头' },
                    'strong_bear': { text: '强空头', cls: 'trend-strong-bear', title: 'MA5<MA10<MA20<MA60 完整空头排列' }
                };
                const info = trendMap[t];
                if (info) {
                    // 构建 title，包含均线排列 + ADX 强度
                    let title = info.title;
                    let extraCls = '';
                    if (adx !== null && adx !== undefined) {
                        const adxDesc = adx >= 50 ? '极强趋势' : adx >= 25 ? '强趋势' : adx >= 20 ? '趋势形成中' : '无趋势';
                        title += `\nADX: ${adx}（${adxDesc}）\n+DI: ${crossover.trend.plus_di}  -DI: ${crossover.trend.minus_di}`;
                        if (adx >= 25) extraCls = ' trend-adx-strong';
                    }
                    texts.push(`<span class="crossover-text ${info.cls}${extraCls}" title="${title}">${info.text}</span>`);
                }
            }
            // 金叉信号
            if (crossover.macd === 'golden') {
                texts.push('<span class="crossover-text macd-golden" title="DIF上穿DEA">MACD金叉</span>');
            } else if (crossover.macd === 'near_golden') {
                texts.push('<span class="crossover-text macd-near" title="DIF接近DEA">MACD即将金叉</span>');
            }
            if (crossover.ma === 'golden') {
                texts.push('<span class="crossover-text ma-golden" title="MA5上穿MA10">MA金叉</span>');
            } else if (crossover.ma === 'near_golden') {
                texts.push('<span class="crossover-text ma-near" title="MA5接近MA10">MA即将金叉</span>');
            }
            return texts.length ? texts.join('<br>') : '<span class="crossover-none">-</span>';
        }

        // 手动触发重新拉取指数数据（调用 /api/index/trigger-fetch）
        async function refreshIndexData() {
            const btn = document.getElementById('refresh-index-btn');
            if (!btn) return;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ 拉取中...';
            try {
                const data = await DataService.triggerFetch();
                const cnt = data && data.count ? data.count : 0;
                btn.innerHTML = '✅ 已拉取 ' + cnt + ' 条';
                // 重新加载页面数据
                setTimeout(() => {
                    loadIndexData();
                    if (typeof loadRotationData === 'function') loadRotationData();
                }, 500);
                setTimeout(() => { btn.innerHTML = originalText; btn.disabled = false; }, 3000);
            } catch (err) {
                console.error('拉取指数数据失败:', err);
                btn.innerHTML = '❌ 失败';
                setTimeout(() => { btn.innerHTML = originalText; btn.disabled = false; }, 3000);
                alert('拉取指数数据失败: ' + err.message);
            }
        }

        // 加载指数数据
        async function loadIndexData() {
            if (window.perfMonitor) window.perfMonitor.start('loadIndexData');
            try {
                const [marketData, industryData] = await Promise.all([
                    DataService.getMarketIndices(),
                    DataService.getIndustryIndices(10000)
                ]);

                if (marketData) {
                    marketComparisonData = marketData.comparison || null;
                    dataQualityData = marketData.data_quality || null;
                    renderMarketIndices(marketData.indices || []);
                }
                if (industryData) {
                    industryIndicesData = industryData.indices || [];
                    renderIndustryIndices();
                }
                // 渲染市场总览统计区（市场指数 + 行业数据均已就绪）
                renderMarketOverview();
            } catch (err) {
                console.error('加载指数数据失败:', err);
                document.getElementById('market-indices-grid').innerHTML = '<div class="index-loading">加载失败</div>';
                document.getElementById('industry-indices-body').innerHTML = '<tr><td colspan="16" class="index-loading">加载失败</td></tr>';
            }

            // 加载行业轮动数据
            loadRotationData();
            if (window.perfMonitor) window.perfMonitor.end('loadIndexData');
        }

        // 行业轮动数据
        let rotationData = null;
        // 轮动数据按 code 建立索引，供行业指数表合并展示
        let rotationByCode = {};

        async function loadRotationData() {
            const strongList = document.getElementById('rotation-strong-list');
            const weakList = document.getElementById('rotation-weak-list');

            if (strongList) strongList.innerHTML = '<div class="index-loading">加载中...</div>';
            if (weakList) weakList.innerHTML = '<div class="index-loading">加载中...</div>';

            try {
                const data = await DataService.getRotation();
                rotationData = data;
                // 构建 code -> 轮动信息 索引
                rotationByCode = {};
                if (rotationData && rotationData.indices) {
                    rotationData.indices.forEach(item => {
                        rotationByCode[item.code] = item;
                    });
                }
                renderRotationRanking();
                // 渲染异常轮动预警卡片
                renderRotationAlerts();
                // 热力图已移至独立子 tab「🔥 热力图」，此处不再渲染
                // 轮动数据已合并到行业指数表，刷新表格以显示动量/排名列
                renderIndustryIndices();
                // 加载轮动历史排名趋势图（bump chart）
                loadRotationHistory();
                // 加载资金流向桑基图
                loadRotationSankey();
            } catch (err) {
                console.error('加载行业轮动数据失败:', err);
                if (strongList) strongList.innerHTML = `<div class="index-loading">加载失败</div>`;
                if (weakList) weakList.innerHTML = `<div class="index-loading">加载失败</div>`;
            }
        }

        function renderRotationRanking() {
            if (!rotationData) return;

            // 强势 TOP 10
            const strongList = document.getElementById('rotation-strong-list');
            if (strongList) {
                strongList.innerHTML = rotationData.top_strong.map((item, i) => {
                    const rank = i + 1;
                    const rankClass = rank <= 3 ? `rank-${rank}` : '';
                    const valClass = item.change_pct >= 0 ? 'index-up' : 'index-down';
                    return `
                        <div class="rotation-item ${rankClass}">
                            <span><span class="rotation-item-rank">${rank}</span><span class="rotation-item-name">${item.name}</span></span>
                            <span class="rotation-item-value ${valClass}">${item.change_pct >= 0 ? '+' : ''}${item.change_pct}%</span>
                        </div>
                    `;
                }).join('');
            }

            // 弱势 TOP 10
            const weakList = document.getElementById('rotation-weak-list');
            if (weakList) {
                weakList.innerHTML = rotationData.top_weak.map((item, i) => {
                    const rank = i + 1;
                    const rankClass = rank <= 3 ? `rank-${rank}` : '';
                    const valClass = item.change_pct >= 0 ? 'index-up' : 'index-down';
                    return `
                        <div class="rotation-item ${rankClass}">
                            <span><span class="rotation-item-rank">${rank}</span><span class="rotation-item-name">${item.name}</span></span>
                            <span class="rotation-item-value ${valClass}">${item.change_pct >= 0 ? '+' : ''}${item.change_pct}%</span>
                        </div>
                    `;
                }).join('');
            }
        }

        // ===== 异常轮动预警卡片 =====
        function renderRotationAlerts() {
            const container = document.getElementById('rotation-alerts-container');
            if (!container) return;
            const alerts = (rotationData && rotationData.alerts) || [];
            if (alerts.length === 0) {
                container.style.display = 'none';
                container.innerHTML = '';
                return;
            }
            container.style.display = 'flex';
            const levelConfig = {
                high: { class: 'alert-high', icon: '🔴', label: '高' },
                medium: { class: 'alert-medium', icon: '🟠', label: '中' },
                low: { class: 'alert-low', icon: '🟡', label: '低' }
            };
            container.innerHTML = alerts.map(function (a) {
                const cfg = levelConfig[a.level] || levelConfig.low;
                return '<div class="rotation-alert-card ' + cfg.class + '" onclick="showKline(\'' + a.code + '\', \'' + a.name.replace(/'/g, '') + '\')" title="点击查看K线">' +
                    '<span class="alert-icon">' + cfg.icon + '</span>' +
                    '<div class="alert-content">' +
                    '<div class="alert-message">' + a.message + '</div>' +
                    '<div class="alert-type">' + a.type.replace(/_/g, ' ') + '</div>' +
                    '</div>' +
                    '<button class="alert-close" onclick="event.stopPropagation(); dismissAlert(this)" title="关闭">✕</button>' +
                    '</div>';
            }).join('');
        }

        function dismissAlert(btn) {
            const card = btn.closest('.rotation-alert-card');
            if (card) card.remove();
            const container = document.getElementById('rotation-alerts-container');
            if (container && container.children.length === 0) container.style.display = 'none';
        }

        // ===== 轮动历史排名趋势图（bump chart）=====
        let rotationHistoryChart = null;
        let rotationHistoryData = null;

        async function loadRotationHistory() {
            const container = document.getElementById('rotation-history-chart-container');
            if (!container) return;

            const daysSelect = document.getElementById('rotation-history-days');
            const days = daysSelect ? parseInt(daysSelect.value, 10) : 30;

            try {
                const data = await DataService.getRotationHistory(days);
                rotationHistoryData = data;
                renderRotationHistoryChart(data);
            } catch (err) {
                console.error('加载轮动历史趋势数据失败:', err);
            }
        }

        // 计算每个板块的线条颜色/宽度（基于 TOP 10 和搜索关键词）
        function _computeRotationLineStyles(sectors, keyword) {
            // 按最近一日排名排序，TOP 10 用深色
            const latestRanks = sectors.map(function (s, i) {
                return { idx: i, latest: s.ranks[s.ranks.length - 1] || 999 };
            }).sort(function (a, b) { return a.latest - b.latest; });
            const top10Indices = {};
            for (let k = 0; k < Math.min(10, latestRanks.length); k++) {
                top10Indices[latestRanks[k].idx] = true;
            }

            const kw = keyword ? keyword.toLowerCase() : '';
            return sectors.map(function (s, i) {
                if (kw && s.name.toLowerCase().indexOf(kw) >= 0) {
                    return { borderColor: 'rgba(231,76,60,0.9)', borderWidth: 3, pointRadius: 3 };
                }
                if (kw) {
                    return { borderColor: 'rgba(200,200,200,0.12)', borderWidth: 1, pointRadius: 0 };
                }
                if (top10Indices[i]) {
                    return { borderColor: 'rgba(74,144,217,0.7)', borderWidth: 2, pointRadius: 2 };
                }
                return { borderColor: 'rgba(150,150,150,0.25)', borderWidth: 1.5, pointRadius: 2 };
            });
        }

        function renderRotationHistoryChart(data) {
            const canvas = document.getElementById('rotation-history-chart');
            if (!canvas || !data || !data.sectors || data.sectors.length === 0) return;

            if (rotationHistoryChart) {
                rotationHistoryChart.destroy();
                rotationHistoryChart = null;
            }

            const tc = ChartPresets.getThemeColors();
            const sectors = data.sectors;
            // 只显示 TOP 20 和 BOTTOM 20，避免线条过多导致图表混乱
            const sortedByRank = sectors.slice().sort(function (a, b) {
                var ra = a.ranks[a.ranks.length - 1] || 999;
                var rb = b.ranks[b.ranks.length - 1] || 999;
                return ra - rb;
            });
            const top20 = sortedByRank.slice(0, 20);
            const bottom20 = sortedByRank.slice(-20);
            const filteredSectors = top20.concat(bottom20);
            const styles = _computeRotationLineStyles(filteredSectors, '');

            const datasets = filteredSectors.map(function (s, i) {
                var st = styles[i];
                var latestRank = s.ranks[s.ranks.length - 1] || 999;
                // TOP 5 板块增加数据点标注
                var pointRadius = (latestRank <= 5) ? 4 : st.pointRadius;
                return {
                    label: s.name,
                    data: s.ranks.slice(),
                    borderColor: st.borderColor,
                    backgroundColor: 'transparent',
                    borderWidth: st.borderWidth,
                    pointRadius: pointRadius,
                    pointHoverRadius: 6,
                    tension: 0,
                    spanGaps: true
                };
            });

            const ctx = canvas.getContext('2d');
            rotationHistoryChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.dates,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: {
                            reverse: true,
                            min: 1,
                            title: { display: true, text: '排名', color: tc.flat },
                            ticks: { color: tc.flat },
                            grid: { color: 'rgba(0,0,0,0.05)' }
                        },
                        x: {
                            title: { display: true, text: '日期', color: tc.flat },
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                autoSkipPadding: 50,
                                color: tc.flat
                            },
                            grid: { display: false }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            itemSort: function (a, b) { return a.parsed.y - b.parsed.y; },
                            callbacks: {
                                title: function (items) {
                                    return data.dates[items[0].dataIndex];
                                },
                                label: function (c) {
                                    return c.dataset.label + ': #' + c.parsed.y;
                                }
                            }
                        }
                    },
                    onHover: function (event, elements) {
                        if (event.native && event.native.target) {
                            event.native.target.style.cursor = elements.length > 0 ? 'pointer' : 'default';
                        }
                    }
                }
            });
        }

        function highlightRotationLine() {
            if (!rotationHistoryChart || !rotationHistoryData) return;

            const input = document.getElementById('rotation-history-search');
            const keyword = input ? input.value.trim() : '';

            const sectors = rotationHistoryData.sectors;
            const styles = _computeRotationLineStyles(sectors, keyword);

            rotationHistoryChart.data.datasets.forEach(function (ds, i) {
                var st = styles[i];
                if (!st) return;
                ds.borderColor = st.borderColor;
                ds.borderWidth = st.borderWidth;
                ds.pointRadius = st.pointRadius;
            });
            rotationHistoryChart.update('none');
        }

        // ===== 轮动路径桑基图（资金流向）=====
        let sankeyChart = null;
        let sankeyCurrentPeriod = '今日';

        function switchSankeyPeriod(period) {
            sankeyCurrentPeriod = period;
            document.querySelectorAll('.sankey-period-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.period === period);
            });
            loadRotationSankey();
        }

        async function loadRotationSankey() {
            try {
                const data = await DataService.getFundFlow(sankeyCurrentPeriod);
                let items = data.items || [];

                // 回退：fund-flow API 返回空时，使用 rotation API 的数据
                if (items.length === 0) {
                    const rotData = await DataService.getRotation(false);
                    const rotItems = (rotData.indices || []).map(function (it) {
                        var bd = it.momentum_breakdown || {};
                        var fd = bd.fund_detail || {};
                        // 使用 main_in_flow 如果有值，否则用 change_pct * amount 作为估算
                        var flow = fd.main_in_flow;
                        if (flow === null || flow === undefined || flow === 0) {
                            flow = (it.change_pct || 0) * (it.amount || 0) * 1000000;
                        }
                        return { name: it.name, main_in_flow: flow };
                    }).filter(function (it) { return it.main_in_flow !== 0; });
                    items = rotItems;

                    // 显示无实时数据提示
                    var hint = document.getElementById('sankey-data-hint');
                    if (hint) {
                        hint.style.display = 'block';
                        hint.textContent = '⚠️ 实时资金流接口暂不可用，以下为基于涨跌幅估算的资金流向';
                    }
                } else {
                    var hint = document.getElementById('sankey-data-hint');
                    if (hint) hint.style.display = 'none';
                }

                renderSankeyChart(items);
            } catch (err) {
                console.error('桑基图加载失败:', err);
            }
        }

        function renderSankeyChart(items) {
            const canvas = document.getElementById('rotation-sankey-chart');
            if (!canvas || !items.length) return;
            if (sankeyChart) sankeyChart.destroy();

            // 净流出 TOP 10（资金来源）和净流入 TOP 10（资金去向）
            const sorted = [...items].sort((a, b) => (b.main_in_flow || 0) - (a.main_in_flow || 0));
            const inflowTop = sorted.slice(0, 10);   // 净流入最多
            const outflowTop = sorted.slice(-10).reverse();  // 净流出最多

            const tc = ChartPresets.getThemeColors();
            const nodes = new Map();  // name -> { color, column }

            // 左列：净流出板块（column 0）
            outflowTop.forEach(item => {
                nodes.set(item.name, { color: tc.fall, column: 0 });
            });

            // 右列：净流入板块（column 1）
            inflowTop.forEach(item => {
                nodes.set(item.name, { color: tc.rise, column: 1 });
            });

            // 连线：每个净流出板块按比例分配到净流入板块（资金守恒简化模型）
            const totalInflow = inflowTop.reduce((s, i) => s + Math.max(0, i.main_in_flow || 0), 0);
            const flows = [];
            if (totalInflow > 0) {
                outflowTop.forEach(fromItem => {
                    const fromOutflow = Math.abs(fromItem.main_in_flow || 0);
                    inflowTop.forEach(toItem => {
                        const toInflow = Math.max(0, toItem.main_in_flow || 0);
                        const flow = (fromOutflow * toInflow / totalInflow);
                        if (flow > 0) {
                            flows.push({
                                from: fromItem.name,
                                to: toItem.name,
                                flow: Math.round(flow / 100000000 * 100) / 100  // 转亿元，保留2位
                            });
                        }
                    });
                });
            }

            sankeyChart = new Chart(canvas.getContext('2d'), {
                type: 'sankey',
                data: {
                    datasets: [{
                        label: '资金流向',
                        data: flows,
                        colorFrom: (c) => nodes.get(c.raw.from)?.color || '#999',
                        colorTo: (c) => nodes.get(c.raw.to)?.color || '#999',
                        colorMode: 'gradient',
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                title: () => '',
                                label: (c) => {
                                    const f = c.raw;
                                    return [`${f.from} → ${f.to}`, `估算流量: ${f.flow.toFixed(2)}亿`];
                                }
                            }
                        }
                    },
                    scales: {
                        x: { display: false },
                        y: { display: false }
                    }
                }
            });
        }

        // ===== 动量雷达图抽屉 =====
        let radarChart = null;
        let radarMode = 'single';
        let radarCurrentCode = null;
        let radarCompareCode = null;

        function showRadarDrawer(code) {
            // 对比模式：已有主板块时，第二次点击设为对比板块
            if (radarMode === 'compare' && radarCurrentCode && radarCurrentCode !== code) {
                radarCompareCode = code;
                document.getElementById('radar-drawer-overlay').style.display = 'block';
                document.getElementById('radar-drawer').style.display = 'block';
                document.getElementById('radar-drawer').classList.add('open');
                renderRadarChart();
                return;
            }
            radarCurrentCode = code;
            radarCompareCode = null;
            document.getElementById('radar-drawer-overlay').style.display = 'block';
            document.getElementById('radar-drawer').style.display = 'block';
            document.getElementById('radar-drawer').classList.add('open');
            renderRadarChart();
        }

        function closeRadarDrawer() {
            document.getElementById('radar-drawer-overlay').style.display = 'none';
            document.getElementById('radar-drawer').style.display = 'none';
            document.getElementById('radar-drawer').classList.remove('open');
            if (radarChart) { radarChart.destroy(); radarChart = null; }
        }

        function setRadarMode(mode) {
            radarMode = mode;
            document.querySelectorAll('.radar-mode-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.mode === mode);
            });
            if (mode === 'single') {
                radarCompareCode = null;
            }
            renderRadarChart();
            renderRadarInfoPanel();
        }

        function buildRadarData(code) {
            const item = rotationByCode[code];
            if (!item) return null;
            const b = item.momentum_breakdown;

            // 五维指标（均标准化 0-100）
            const dimensions = {
                price: b?.price ? Math.round(b.price / 50 * 100) : 50,
                volume: b?.volume ? Math.round(b.volume / 30 * 100) : 50,
                fund: b?.fund ? Math.round(b.fund / 20 * 100) : 50,
                trend: _computeTrendScore(item),
                drawdown: _computeDrawdownScore(item)
            };
            return dimensions;
        }

        function _computeTrendScore(item) {
            // 趋势得分：基于多周期涨跌方向一致性
            let score = 50;
            if (item.change_pct > 0) score += 10;
            if (item.change_pct_3d > 0) score += 15;
            if (item.change_pct_7d > 0) score += 15;
            if (item.momentum > 60) score += 10;
            return Math.min(100, Math.max(0, score));
        }

        function _computeDrawdownScore(item) {
            // 回撤控制：回撤越小分越高
            const dd = item.drawdown || rotationByCode[item.code]?.drawdown;
            if (!dd || dd.depth == null) return 50;
            return Math.min(100, Math.max(0, Math.round(100 - dd.depth * 3.3)));
        }

        function renderRadarChart() {
            const canvas = document.getElementById('radar-chart');
            if (!canvas) return;
            if (radarChart) radarChart.destroy();

            const labels = ['价格动量', '量能', '资金', '趋势', '回撤控制'];
            const datasets = [];

            const data1 = buildRadarData(radarCurrentCode);
            if (data1) {
                const item1 = rotationByCode[radarCurrentCode];
                const tc = ChartPresets.getThemeColors();
                datasets.push({
                    label: item1.name,
                    data: [data1.price, data1.volume, data1.fund, data1.trend, data1.drawdown],
                    backgroundColor: tc.riseAlpha(0.2),
                    borderColor: tc.rise,
                    borderWidth: 2,
                    pointBackgroundColor: tc.rise,
                    pointRadius: 4,
                });
            }

            if (radarMode === 'compare' && radarCompareCode) {
                const data2 = buildRadarData(radarCompareCode);
                if (data2) {
                    const item2 = rotationByCode[radarCompareCode];
                    const tc = ChartPresets.getThemeColors();
                    datasets.push({
                        label: item2.name,
                        data: [data2.price, data2.volume, data2.fund, data2.trend, data2.drawdown],
                        backgroundColor: tc.fallAlpha(0.2),
                        borderColor: tc.fall,
                        borderWidth: 2,
                        pointBackgroundColor: tc.fall,
                        pointRadius: 4,
                    });
                }
            }

            radarChart = new Chart(canvas.getContext('2d'), {
                type: 'radar',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            min: 0,
                            max: 100,
                            ticks: { stepSize: 20, font: { size: 10 } },
                            pointLabels: { font: { size: 12 } }
                        }
                    },
                    plugins: {
                        legend: { display: true, position: 'top' },
                        tooltip: {
                            callbacks: {
                                label: (c) => `${c.dataset.label}: ${c.parsed.r}/100`
                            }
                        }
                    }
                }
            });
            renderRadarInfoPanel();
        }

        function renderRadarInfoPanel() {
            const panel = document.getElementById('radar-info-panel');
            if (!panel) return;
            let html = '';
            const item1 = rotationByCode[radarCurrentCode];
            if (item1) {
                html += `<div class="radar-info-item"><strong>${item1.name}</strong> (动量 ${item1.momentum?.toFixed(1) || '-'})</div>`;
            }
            if (radarMode === 'compare') {
                if (radarCompareCode) {
                    const item2 = rotationByCode[radarCompareCode];
                    if (item2) {
                        html += `<div class="radar-info-item"><strong>${item2.name}</strong> (动量 ${item2.momentum?.toFixed(1) || '-'})</div>`;
                    }
                } else {
                    html += `<div class="radar-info-hint">💡 在行业指数表中点击另一个板块的 📊 按钮进行对比</div>`;
                }
            }
            panel.innerHTML = html;
        }

        // 热力图 Chart 实例（Treemap，面积按成交额加权）
        let heatmapChart = null;

        // 加载热力图数据（首次切换到热力图 tab 时调用）
        async function loadHeatmapData() {
            const container = document.getElementById('heatmap-container');
            if (!container) return;
            // 如果已有数据，直接渲染
            if (rotationData) {
                renderHeatmapTab();
                return;
            }
            container.innerHTML = '<div class="index-loading">加载中...</div>';
            try {
                const data = await DataService.getRotation();
                rotationData = data;
                rotationByCode = {};
                if (rotationData && rotationData.indices) {
                    rotationData.indices.forEach(item => {
                        rotationByCode[item.code] = item;
                    });
                }
                renderHeatmapTab();
            } catch (err) {
                console.error('加载热力图数据失败:', err);
                container.innerHTML = '<div class="index-loading">加载失败</div>';
            }
        }

        // 渲染热力图 Treemap（支持多维度切换）
        function renderHeatmapTab() {
            if (window.perfMonitor) window.perfMonitor.start('renderHeatmapTab');
            const container = document.getElementById('heatmap-container');
            if (!container) { if (window.perfMonitor) window.perfMonitor.end('renderHeatmapTab'); return; }
            if (!rotationData || !rotationData.indices) {
                container.innerHTML = '<div class="index-loading">暂无数据</div>';
                if (window.perfMonitor) window.perfMonitor.end('renderHeatmapTab');
                return;
            }

            // 读取控件值
            const dimension = (document.getElementById('heatmap-dimension') || {}).value || 'industry';
            const colorField = (document.getElementById('heatmap-color') || {}).value || 'change_pct';
            const sizeField = (document.getElementById('heatmap-size') || {}).value || 'amount';
            const topN = parseInt((document.getElementById('heatmap-top') || {}).value || '100', 10);

            // 按维度筛选：industry=纯数字 code，concept=非纯数字 code
            let indices = rotationData.indices.filter(item => {
                const isIndustry = /^\d+$/.test(item.code);
                return dimension === 'industry' ? isIndustry : !isIndustry;
            });

            if (indices.length === 0) {
                if (heatmapChart) { heatmapChart.destroy(); heatmapChart = null; }
                container.innerHTML = '<div class="index-loading">暂无' + (dimension === 'industry' ? '行业' : '概念') + '数据</div>';
                if (window.perfMonitor) window.perfMonitor.end('renderHeatmapTab');
                return;
            }

            // 按面积字段排序后取 Top N
            indices = indices.slice().sort((a, b) => {
                const av = parseFloat(a[sizeField]) || 0;
                const bv = parseFloat(b[sizeField]) || 0;
                return bv - av;
            }).slice(0, topN);

            // 销毁旧实例
            if (heatmapChart) { heatmapChart.destroy(); heatmapChart = null; }

            // 准备 treemap 数据
            const treeData = indices.map(item => {
                const pct = parseFloat(item.change_pct) || 0;
                const turnover = parseFloat(item.turnover_rate) || 0;
                const amount = parseFloat(item.amount) || 0;
                const marketCap = parseFloat(item.market_cap) || 0;
                // 面积权重：优先用选定字段，为 0 时降级为另一字段，再为 0 时用涨跌幅绝对值兜底
                // amount 可能为负（概念板块资金净流出），面积用绝对值
                let weight;
                if (sizeField === 'market_cap') {
                    weight = marketCap > 0 ? marketCap : (Math.abs(amount) > 0 ? Math.abs(amount) : (Math.abs(pct) + 0.5));
                } else {
                    weight = Math.abs(amount) > 0 ? Math.abs(amount) : (marketCap > 0 ? marketCap : (Math.abs(pct) + 0.5));
                }
                return {
                    name: item.name,
                    code: item.code,
                    change_pct: pct,
                    change_pct_3d: item.change_pct_3d,
                    change_pct_7d: item.change_pct_7d,
                    turnover_rate: turnover,
                    amount: amount,
                    market_cap: marketCap,
                    momentum: parseFloat(item.momentum) || 0,
                    rank_momentum: item.rank_momentum || 0,
                    weight: weight,
                };
            });

            // 颜色函数：涨跌幅用红绿深浅，换手率用蓝色深浅
            const tc = ChartPresets.getThemeColors();
            function heatColor(item) {
                if (colorField === 'turnover_rate') {
                    // 换手率：蓝色深浅（用 riseAlpha 作为通用深色， intensity 按换手率/10）
                    const intensity = Math.min((item.turnover_rate || 0) / 10, 1);
                    const alpha = 0.20 + intensity * 0.70;
                    return tc.riseAlpha(alpha);
                }
                // 涨跌幅：红涨绿跌深浅
                const pct = item.change_pct || 0;
                const intensity = Math.min(Math.abs(pct) / 5, 1);  // 5% 为最大强度
                const alpha = 0.22 + intensity * 0.68;
                return pct >= 0 ? tc.riseAlpha(alpha) : tc.fallAlpha(alpha);
            }

            // 构建 canvas 容器 + 颜色图例
            const isExpanded = container.classList.contains('expanded');
            // 图例：涨跌幅模式 红→灰→绿，换手率模式 浅红→深红
            const legendHtml = colorField === 'turnover_rate'
                ? '<div class="heatmap-legend"><span class="legend-label">换手率</span>'
                    + '<div class="legend-bar"><div class="legend-gradient legend-gradient-turnover"></div>'
                    + '<div class="legend-ticks"><span>0%</span><span>5%</span><span>10%+</span></div></div></div>'
                : '<div class="heatmap-legend"><span class="legend-label">涨跌幅</span>'
                    + '<div class="legend-bar"><div class="legend-gradient legend-gradient-change"></div>'
                    + '<div class="legend-ticks"><span>-5%</span><span>0</span><span>+5%</span></div></div></div>';
            container.innerHTML = legendHtml
                + '<div class="heatmap-treemap-wrap' + (isExpanded ? ' expanded' : '') + '">'
                + '<canvas id="heatmap-treemap-canvas"></canvas></div>';
            const canvas = document.getElementById('heatmap-treemap-canvas');
            if (!canvas) { if (window.perfMonitor) window.perfMonitor.end('renderHeatmapTab'); return; }

            // 标签/tooltip 文案
            const sizeLabel = sizeField === 'market_cap' ? '总市值' : '成交额';
            const colorLabel = colorField === 'turnover_rate' ? '换手率' : '涨跌幅';

            heatmapChart = new Chart(canvas, {
                type: 'treemap',
                data: {
                    datasets: [{
                        tree: treeData,
                        key: 'weight',
                        spacing: 1,
                        borderWidth: 1,
                        borderColor: 'rgba(255,255,255,0.25)',
                        hoverBorderWidth: 3,
                        hoverBorderColor: 'rgba(255,255,255,0.95)',
                        backgroundColor: function(c) {
                            const item = c.raw && c.raw._data;
                            return item ? heatColor(item) : 'rgba(150,150,150,0.2)';
                        },
                        labels: {
                            display: true,
                            font: { size: 11 },
                            color: '#fff',
                            overflow: 'cut',
                            formatter: function(c) {
                                const item = c.raw && c.raw._data;
                                if (!item) return '';
                                if (colorField === 'turnover_rate') {
                                    return [item.name, (item.turnover_rate || 0).toFixed(2) + '%'];
                                }
                                const pct = item.change_pct || 0;
                                return [item.name, (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'];
                            }
                        }
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(30,30,40,0.92)',
                            titleColor: '#fff',
                            bodyColor: '#e0e0e0',
                            borderColor: 'rgba(255,255,255,0.2)',
                            borderWidth: 1,
                            padding: 10,
                            cornerRadius: 6,
                            displayColors: false,
                            callbacks: {
                                title: function() { return ''; },
                                label: function(c) {
                                    const item = c.raw && c.raw._data;
                                    if (!item) return '';
                                    const pct = item.change_pct || 0;
                                    const pct3d = item.change_pct_3d;
                                    const pct7d = item.change_pct_7d;
                                    const momentum = item.momentum || 0;
                                    const rankMomentum = item.rank_momentum || 0;
                                    const lines = [item.name];
                                    lines.push('今日涨跌幅: ' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%');
                                    if (pct3d !== null && pct3d !== undefined) {
                                        lines.push('3日涨跌幅: ' + (pct3d >= 0 ? '+' : '') + pct3d.toFixed(2) + '%');
                                    }
                                    if (pct7d !== null && pct7d !== undefined) {
                                        lines.push('7日涨跌幅: ' + (pct7d >= 0 ? '+' : '') + pct7d.toFixed(2) + '%');
                                    }
                                    lines.push('换手率: ' + (item.turnover_rate || 0).toFixed(2) + '%');
                                    // amount 可能为负（概念板块资金净流出），显示实际值
                                    if (item.amount !== 0) {
                                        const amt = item.amount;
                                        lines.push('成交额: ' + (amt >= 0 ? '' : '') + amt.toFixed(2) + '亿' + (amt < 0 ? ' (净流出)' : ''));
                                    }
                                    if (item.market_cap > 0) {
                                        lines.push('总市值: ' + (item.market_cap / 10000).toFixed(2) + '万亿');
                                    } else if (sizeField === 'market_cap') {
                                        lines.push('总市值: 数据待补充（已用成交额替代）');
                                    }
                                    lines.push('动量得分: ' + momentum.toFixed(1) + '/100' + (rankMomentum ? ' (排名 #' + rankMomentum + ')' : ''));
                                    lines.push('');
                                    lines.push('💡 点击查看K线图');
                                    return lines;
                                }
                            }
                        }
                    },
                    onClick: function(e, elements) {
                        if (!elements || elements.length === 0) return;
                        const el = elements[0];
                        // 多种方式获取数据（兼容不同版本 treemap 插件）
                        let item = null;
                        // 方式1：$context.raw._data（当前 treemap 插件版本）
                        if (el.$context && el.$context.raw && el.$context.raw._data) {
                            item = el.$context.raw._data;
                        }
                        // 方式2：$raw._data（旧版 treemap 插件）
                        if (!item && el.$raw && el.$raw._data) item = el.$raw._data;
                        // 方式3：从 dataset.tree 按 dataIndex 获取
                        if (!item) {
                            const ds = this.data.datasets[el.datasetIndex];
                            const idx = el.$context ? el.$context.dataIndex : el.index;
                            if (ds && ds.tree && idx >= 0 && idx < ds.tree.length) {
                                item = ds.tree[idx];
                            }
                        }
                        if (item && item.code) {
                            showKline(item.code, item.name);
                        }
                    }
                }
            });
            if (window.perfMonitor) window.perfMonitor.end('renderHeatmapTab');
        }

        // 涨跌幅色深：参照热力图，幅度越大颜色越深（红涨绿跌，颜色读 CSS 变量）
        function getChangeDepthBg(pct, maxPct, baseAlpha, peakAlpha) {
            maxPct = (maxPct == null) ? 5 : maxPct;
            baseAlpha = (baseAlpha == null) ? 0.10 : baseAlpha;
            peakAlpha = (peakAlpha == null) ? 0.50 : peakAlpha;
            if (pct == null || isNaN(pct)) return 'transparent';
            if (pct === 0) return 'rgba(149,165,166,0.12)';
            const intensity = Math.min(Math.abs(pct) / maxPct, 1);
            const alpha = baseAlpha + intensity * (peakAlpha - baseAlpha);
            const tc = ChartPresets.getThemeColors();
            return pct >= 0 ? tc.riseAlpha(alpha) : tc.fallAlpha(alpha);
        }

        // 渲染市场指数卡片
        let marketIndicesCache = [];

        // 市场总览统计区（借鉴 stock-dashboard 总览页：成交额/涨跌/最强最弱行业）
        // 数据来源：marketIndicesCache + industryIndicesData（loadIndexData 已加载到内存，零额外请求）
        function renderMarketOverview() {
            const markets = marketIndicesCache || [];
            // 行业指数（排除概念板块，概念板块 code 非纯数字）
            const industries = (industryIndicesData || []).filter(idx => /^\d+$/.test(idx.code));

            // 全市场成交额（市场指数 amount 汇总，单位亿元）
            const totalAmount = markets.reduce((s, idx) => s + (idx.amount || 0), 0);
            const amtEl = document.getElementById('overview-total-amount');
            if (amtEl) amtEl.textContent = totalAmount >= 10000 ? (totalAmount / 10000).toFixed(2) + '万亿' : totalAmount.toFixed(0) + '亿';

            // 行业涨跌统计
            let rise = 0, fall = 0, flat = 0;
            industries.forEach(idx => {
                const pct = idx.change_pct || 0;
                if (pct > 0) rise++;
                else if (pct < 0) fall++;
                else flat++;
            });
            const riseEl = document.getElementById('overview-rise-count');
            const fallEl = document.getElementById('overview-fall-count');
            const flatEl = document.getElementById('overview-flat-count');
            if (riseEl) riseEl.textContent = rise;
            if (fallEl) fallEl.textContent = fall;
            if (flatEl) flatEl.textContent = flat;

            // 最强/最弱行业（按今日涨跌幅）
            let strongest = null, weakest = null;
            industries.forEach(idx => {
                const pct = idx.change_pct || 0;
                if (!strongest || pct > (strongest.change_pct || -Infinity)) strongest = idx;
                if (!weakest || pct < (weakest.change_pct || Infinity)) weakest = idx;
            });
            const sNameEl = document.getElementById('overview-strongest-name');
            const sPctEl = document.getElementById('overview-strongest-pct');
            const wNameEl = document.getElementById('overview-weakest-name');
            const wPctEl = document.getElementById('overview-weakest-pct');
            if (sNameEl) sNameEl.textContent = strongest ? strongest.name : '--';
            if (sPctEl) sPctEl.textContent = strongest ? (strongest.change_pct >= 0 ? '+' : '') + strongest.change_pct.toFixed(2) + '%' : '--';
            if (wNameEl) wNameEl.textContent = weakest ? weakest.name : '--';
            if (wPctEl) wPctEl.textContent = weakest ? (weakest.change_pct >= 0 ? '+' : '') + weakest.change_pct.toFixed(2) + '%' : '--';

            // 最强/最弱卡片点击跳转 K 线
            const sCard = document.getElementById('overview-strongest-card');
            const wCard = document.getElementById('overview-weakest-card');
            if (sCard) sCard.onclick = strongest ? () => showKline(strongest.code, strongest.name) : null;
            if (wCard) wCard.onclick = weakest ? () => showKline(weakest.code, weakest.name) : null;

            // 更新时间
            const updatedEl = document.getElementById('market-overview-updated');
            if (updatedEl && markets.length > 0 && markets[0].fetched_at) {
                updatedEl.textContent = '更新于 ' + markets[0].fetched_at.substring(11, 16);
            }

            // 渲染历史对比标签
            const amtCompEl = document.getElementById('overview-amount-comparison');
            const riseCompEl = document.getElementById('overview-rise-comparison');

            if (marketComparisonData && marketComparisonData.has_history) {
                // 成交额对比
                if (amtCompEl) {
                    const parts = [];
                    if (marketComparisonData.amount_vs_yesterday !== null) {
                        const v = marketComparisonData.amount_vs_yesterday;
                        const cls = v >= 0 ? 'comp-up' : 'comp-down';
                        const arrow = v >= 0 ? '↑' : '↓';
                        parts.push(`<span class="${cls}">较昨日 ${arrow}${Math.abs(v).toFixed(1)}%</span>`);
                    }
                    if (marketComparisonData.amount_vs_5d_avg !== null) {
                        const v = marketComparisonData.amount_vs_5d_avg;
                        const cls = v >= 0 ? 'comp-up' : 'comp-down';
                        const arrow = v >= 0 ? '↑' : '↓';
                        parts.push(`<span class="${cls}">较5日均 ${arrow}${Math.abs(v).toFixed(1)}%</span>`);
                    }
                    amtCompEl.innerHTML = parts.length ? parts.join(' ') : '';
                }
                // 上涨家数对比
                if (riseCompEl) {
                    if (marketComparisonData.rise_count_vs_yesterday !== null) {
                        const v = marketComparisonData.rise_count_vs_yesterday;
                        const cls = v >= 0 ? 'comp-up' : 'comp-down';
                        const arrow = v >= 0 ? '↑' : '↓';
                        riseCompEl.innerHTML = `<span class="${cls}">较昨日 ${arrow}${Math.abs(v)} 家</span>`;
                    }
                }
            } else {
                if (amtCompEl) amtCompEl.innerHTML = '<span class="comp-none">暂无历史数据</span>';
                if (riseCompEl) riseCompEl.innerHTML = '<span class="comp-none">暂无历史数据</span>';
            }

            // 渲染数据质量标签（行业/概念板块字段填充率）
            const qualityBadge = document.getElementById('data-quality-badge');
            if (qualityBadge) {
                if (!dataQualityData || !dataQualityData.has_data) {
                    qualityBadge.style.display = 'none';
                } else {
                    const indAmt = dataQualityData.industry_amount_filled || 0;
                    const conMcap = dataQualityData.concept_market_cap_filled || 0;
                    const conAmt = dataQualityData.concept_amount_filled || 0;
                    const minRatio = Math.min(indAmt, conMcap, conAmt);

                    // 质量等级：全 ≥80% 完整 / 70%-80% 部分缺失 / <70% 数据异常
                    let cls, text;
                    if (minRatio >= 0.80) {
                        cls = 'quality-good';
                        text = '✅ 数据完整';
                    } else if (minRatio >= 0.70) {
                        cls = 'quality-warn';
                        text = '⚠️ 部分缺失';
                    } else {
                        cls = 'quality-error';
                        text = '⚠️ 数据异常';
                    }

                    // tooltip 详情：各维度填充率
                    const pct = function (v) { return (v * 100).toFixed(1) + '%'; };
                    const tooltipLines = [
                        '数据完整性校验',
                        '行业成交额: ' + pct(indAmt) + ' (' + dataQualityData.industry_total + ' 个)',
                        '概念总市值: ' + pct(conMcap) + ' (' + dataQualityData.concept_total + ' 个)',
                        '概念成交额: ' + pct(conAmt)
                    ];

                    qualityBadge.className = 'data-quality-badge ' + cls;
                    qualityBadge.textContent = text;
                    qualityBadge.title = tooltipLines.join('\n');
                    qualityBadge.style.display = 'inline-flex';
                }
            }
        }

        function renderMarketIndices(indices) {
            const container = document.getElementById('market-indices-grid');
            const toggleBtn = document.getElementById('market-indices-toggle');
            marketIndicesCache = indices || [];
            if (!indices || indices.length === 0) {
                container.innerHTML = '<div class="index-loading">暂无数据</div>';
                if (toggleBtn) toggleBtn.style.display = 'none';
                return;
            }
            container.innerHTML = indices.map(idx => {
                const changeClass = formatChangeClass(idx.change_pct);
                const depthBg = getChangeDepthBg(idx.change_pct, 5, 0.08, 0.42);
                const crossoverBadge = formatCrossoverBadge(idx.crossover);
                return `
                    <div class="market-index-card" style="background:${depthBg}" onclick="showKline('${idx.code}', '${idx.name}')">
                        ${crossoverBadge}
                        <div class="market-index-name">${idx.name}<span class="market-index-code">${idx.code}</span></div>
                        <div class="market-index-price ${changeClass}">${idx.price.toFixed(2)}</div>
                        <div class="market-index-change ${changeClass}">${formatChangeText(idx.change, idx.change_pct)}</div>
                    </div>
                `;
            }).join('');
            // 8 个及以下不显示切换按钮；超过 8 个显示并默认收起
            if (toggleBtn) {
                if (indices.length > 8) {
                    toggleBtn.style.display = 'flex';
                    container.classList.add('collapsed');
                    updateMarketIndicesToggleText(indices.length);
                } else {
                    toggleBtn.style.display = 'none';
                    container.classList.remove('collapsed');
                }
            }
        }

        function updateMarketIndicesToggleText(total) {
            const toggleBtn = document.getElementById('market-indices-toggle');
            if (!toggleBtn) return;
            const textEl = toggleBtn.querySelector('.toggle-text');
            const container = document.getElementById('market-indices-grid');
            if (!textEl || !container) return;
            if (container.classList.contains('collapsed')) {
                const hidden = total - 8;
                textEl.textContent = `展开全部 (共 ${total} 个，余 ${hidden} 个)`;
            } else {
                textEl.textContent = '收起';
            }
        }

        function toggleMarketIndices() {
            const container = document.getElementById('market-indices-grid');
            if (!container) return;
            container.classList.toggle('collapsed');
            updateMarketIndicesToggleText(marketIndicesCache.length);
        }

        // 热力图：展开/收起
        function toggleHeatmap() {
            const body = document.getElementById('heatmap-container');
            const btn = document.getElementById('heatmap-toggle-btn');
            if (!body || !btn) return;
            body.classList.toggle('expanded');
            const isExpanded = body.classList.contains('expanded');
            // 同步内部 treemap wrap 的 expanded class（控制高度）
            const wrap = body.querySelector('.heatmap-treemap-wrap');
            if (wrap) wrap.classList.toggle('expanded', isExpanded);
            const textEl = btn.querySelector('.toggle-text');
            if (textEl) textEl.textContent = isExpanded ? '收起' : '展开';
            // 触发 Chart.js 重新适应容器高度
            if (heatmapChart) {
                setTimeout(function() { heatmapChart.resize(); }, 50);
            }
        }

        // 行业指数表：展开/收起
        function toggleIndustryTable() {
            const wrapper = document.getElementById('industry-table-wrapper');
            const btn = document.getElementById('industry-table-toggle');
            if (!wrapper || !btn) return;
            wrapper.classList.toggle('collapsed');
            const expanded = !wrapper.classList.contains('collapsed');
            btn.classList.toggle('expanded', expanded);
            const textEl = btn.querySelector('.toggle-text');
            if (textEl) textEl.textContent = expanded ? '收起' : '展开全部';
        }

        // 渲染行业指数表格
        // 构建多因子动量得分的 tooltip 文本（用于表格动量列 hover 提示）
        function buildMomentumTooltip(rot) {
            if (!rot.momentum_breakdown) return `动量得分: ${rot.momentum}`;
            const b = rot.momentum_breakdown;
            let lines = [`动量总分: ${rot.momentum}/100`];
            lines.push(`├ 价格动量: ${b.price}/50`);
            if (b.price_detail) {
                lines.push(`│  ├ 今日: ${b.price_detail.today != null ? b.price_detail.today.toFixed(1) : '-'}`);
                lines.push(`│  ├ 3日: ${b.price_detail.d3 != null ? b.price_detail.d3.toFixed(1) : '-'}`);
                lines.push(`│  └ 7日: ${b.price_detail.d7 != null ? b.price_detail.d7.toFixed(1) : '-'}`);
            }
            lines.push(`├ 量价动量: ${b.volume}/30`);
            if (b.volume_detail) {
                const rate = b.volume_detail.amount_change_rate;
                lines.push(`│  ├ 量比5日均: ${rate != null ? (rate >= 0 ? '+' : '') + rate.toFixed(1) + '%' : '-'}`);
                lines.push(`│  ├ 量能百分位: ${b.volume_detail.amount_pctile != null ? b.volume_detail.amount_pctile.toFixed(1) : '-'}`);
                lines.push(`│  └ 换手百分位: ${b.volume_detail.turnover_pctile != null ? b.volume_detail.turnover_pctile.toFixed(1) : '-'}`);
            }
            lines.push(`└ 资金动量: ${b.fund}/20`);
            if (b.fund_detail) {
                const flow = b.fund_detail.main_in_flow;
                if (flow != null) {
                    const flowYi = flow / 1e8;
                    lines.push(`   └ 主力净流入: ${flowYi >= 0 ? '+' : ''}${flowYi.toFixed(2)}亿 (百分位 ${b.fund_detail.fund_pctile != null ? b.fund_detail.fund_pctile.toFixed(1) : '-'})`);
                } else {
                    lines.push(`   └ 主力净流入: 无数据`);
                }
            }
            return lines.join('\n');
        }

        function renderIndustryIndices() {
            if (window.perfMonitor) window.perfMonitor.start('renderIndustryIndices');
            const tbody = document.getElementById('industry-indices-body');
            const countDisplay = document.getElementById('industry-count-display');
            const followedBadge = document.getElementById('followed-count-display');
            const followedNumEl = document.getElementById('followed-count-num');
            if (!industryIndicesData || industryIndicesData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="16" class="index-loading">暂无数据</td></tr>';
                if (countDisplay) countDisplay.textContent = '';
                if (followedBadge) followedBadge.style.display = 'none';
                if (window.perfMonitor) window.perfMonitor.end('renderIndustryIndices');
                return;
            }

            // 搜索过滤
            const searchInput = document.getElementById('index-search-input');
            const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
            let filtered = industryIndicesData;

            // Tab 过滤：'industry' = 申万行业指数（code 为纯数字） / 'concept' = 概念板块（code 为中文名称）
            const isConceptCode = (code) => !/^\d+$/.test(String(code || ''));
            if (currentIndustryTab === 'industry') {
                filtered = filtered.filter(idx => !isConceptCode(idx.code));
            } else {
                filtered = filtered.filter(idx => isConceptCode(idx.code));
            }

            // 标识筛选（趋势/金叉）
            const badgeFilter = document.getElementById('index-badge-filter');
            const badgeValue = badgeFilter ? badgeFilter.value : '';
            if (badgeValue) {
                filtered = filtered.filter(idx => {
                    const co = idx.crossover;
                    if (badgeValue === 'none') {
                        // 无标识：无趋势、无金叉、无即将金叉
                        const hasTrend = co && co.trend && co.trend.trend;
                        const hasMacd = co && (co.macd === 'golden' || co.macd === 'near_golden');
                        const hasMa = co && (co.ma === 'golden' || co.ma === 'near_golden');
                        return !hasTrend && !hasMacd && !hasMa;
                    }
                    const [type, val] = badgeValue.split(':');
                    if (!co) return false;
                    if (type === 'trend') return co.trend && co.trend.trend === val;
                    if (type === 'macd') return co.macd === val;
                    if (type === 'ma') return co.ma === val;
                    return false;
                });
            }

            if (query) {
                filtered = filtered.filter(idx =>
                    idx.code.toLowerCase().includes(query) ||
                    idx.name.toLowerCase().includes(query)
                );
            }

            // 智能筛选（多条件组合，AND 逻辑；不影响原始数据）
            const screenerActive = isScreenerActive();
            if (screenerActive) {
                filtered = filtered.filter(idx => matchesScreener(idx));
            }

            // 获取关注列表
            const followedSet = new Set(getFollowedIndices());

            // 排序（三级优先级：关注状态 > 金叉标识置顶 > 正常排序）
            // 仅 MACD金叉 / MA金叉 视为金叉置顶；其他标识（趋势/即将金叉）按正常排序
            // 用户主动点击列头排序时（industrySortField !== 'followed'）跳过金叉置顶，避免干扰指定字段排序
            const isGolden = (co) => {
                if (!co) return false;
                return co.macd === 'golden' || co.ma === 'golden';
            };
            const isDefaultSort = industrySortField === 'followed';
            const sorted = [...filtered].sort((a, b) => {
                // 1) 关注状态优先（始终最优先）
                const aFollowed = followedSet.has(a.code) ? 1 : 0;
                const bFollowed = followedSet.has(b.code) ? 1 : 0;
                if (aFollowed !== bFollowed) {
                    return bFollowed - aFollowed;  // 关注的在前
                }
                // 2) 金叉标识置顶（仅默认排序时生效；用户点击列头排序时跳过，避免干扰）
                if (isDefaultSort) {
                    const aGolden = isGolden(a.crossover) ? 1 : 0;
                    const bGolden = isGolden(b.crossover) ? 1 : 0;
                    if (aGolden !== bGolden) {
                        return bGolden - aGolden;
                    }
                }
                // 3) 正常排序
                // 默认（industrySortField === 'followed'）按今日涨跌幅降序
                if (industrySortField === 'followed') {
                    return (b.change_pct || 0) - (a.change_pct || 0);
                }
                let valA = a[industrySortField];
                let valB = b[industrySortField];
                // 合并的轮动字段从 rotationByCode 解析
                if (industrySortField === 'momentum' ||
                    industrySortField === 'rank_today' ||
                    industrySortField === 'rank_3d' ||
                    industrySortField === 'rank_7d' ||
                    industrySortField === 'rank_change') {
                    const rotA = rotationByCode[a.code] || {};
                    const rotB = rotationByCode[b.code] || {};
                    if (industrySortField === 'momentum') { valA = rotA.momentum; valB = rotB.momentum; }
                    else if (industrySortField === 'rank_today') { valA = rotA.rank_change_pct; valB = rotB.rank_change_pct; }
                    else if (industrySortField === 'rank_3d') { valA = rotA.rank_change_pct_3d; valB = rotB.rank_change_pct_3d; }
                    else if (industrySortField === 'rank_7d') { valA = rotA.rank_change_pct_7d; valB = rotB.rank_change_pct_7d; }
                    else if (industrySortField === 'rank_change') {
                        valA = (rotA.rank_change_pct != null && rotA.rank_change_pct_7d != null) ? (rotA.rank_change_pct_7d - rotA.rank_change_pct) : null;
                        valB = (rotB.rank_change_pct != null && rotB.rank_change_pct_7d != null) ? (rotB.rank_change_pct_7d - rotB.rank_change_pct) : null;
                    }
                } else if (industrySortField === 'drawdown') {
                    // 回撤从 idx.drawdown.drawdown_pct 解析
                    valA = a.drawdown ? a.drawdown.drawdown_pct : null;
                    valB = b.drawdown ? b.drawdown.drawdown_pct : null;
                }
                // null 值排到最后
                if (valA == null) valA = industrySortOrder === 'asc' ? Infinity : -Infinity;
                if (valB == null) valB = industrySortOrder === 'asc' ? Infinity : -Infinity;
                // 字符串字段按中文排序
                if (typeof valA === 'string') {
                    valA = valA.toString();
                    valB = valB.toString();
                    return industrySortOrder === 'asc' ? valA.localeCompare(valB, 'zh') : valB.localeCompare(valA, 'zh');
                }
                valA = parseFloat(valA) || 0;
                valB = parseFloat(valB) || 0;
                return industrySortOrder === 'asc' ? valA - valB : valB - valA;
            });

            // 更新计数显示
            if (countDisplay) {
                if (query || screenerActive) {
                    countDisplay.textContent = `${filtered.length} / ${industryIndicesData.length} 条`;
                } else {
                    countDisplay.textContent = `共 ${industryIndicesData.length} 条`;
                }
            }

            // 更新智能筛选面板匹配计数
            const screenerMatchEl = document.getElementById('screener-match-count');
            if (screenerMatchEl) {
                if (screenerActive) {
                    screenerMatchEl.textContent = `匹配 ${filtered.length} / 共 ${industryIndicesData.length} 个板块`;
                    screenerMatchEl.style.display = '';
                } else {
                    screenerMatchEl.textContent = '';
                    screenerMatchEl.style.display = 'none';
                }
            }

            // 更新关注计数徽章
            const followedCount = industryIndicesData.filter(idx => followedSet.has(idx.code)).length;
            if (followedBadge && followedNumEl) {
                if (followedCount > 0) {
                    followedBadge.style.display = 'inline-block';
                    followedNumEl.textContent = followedCount;
                } else {
                    followedBadge.style.display = 'none';
                }
            }

            // 格式化多日涨跌幅（带色深背景）
            const formatMultiDayChange = (val) => {
                if (val == null) return '<span class="index-flat">—</span>';
                const cls = formatChangeClass(val);
                const sign = val >= 0 ? '+' : '';
                const bg = getChangeDepthBg(val, 5, 0.08, 0.38);
                return `<span class="${cls}" style="padding:2px 6px;border-radius:3px;background:${bg};">${sign}${val.toFixed(2)}%</span>`;
            };

            if (sorted.length === 0) {
                tbody.innerHTML = '<tr><td colspan="16" class="index-loading">未找到匹配的数据</td></tr>';
            } else {
                tbody.innerHTML = sorted.map(idx => {
                    const changeClass = formatChangeClass(idx.change_pct);
                    const isFollowed = followedSet.has(idx.code);
                    const followedClass = isFollowed ? 'followed-row' : '';
                    const starClass = isFollowed ? 'follow-btn active' : 'follow-btn';
                    const starIcon = isFollowed ? '★' : '☆';
                    // 今日涨跌幅：带色深背景
                    const todayBg = getChangeDepthBg(idx.change_pct, 5, 0.10, 0.45);
                    const todayChangeHtml = `<span style="padding:2px 6px;border-radius:3px;background:${todayBg};">${formatChangeText(idx.change, idx.change_pct)}</span>`;
                    // 距高点回撤：回撤越深背景越红
                    let drawdownHtml = '<span class="index-flat">—</span>';
                    if (idx.drawdown) {
                        const dd = idx.drawdown.drawdown_pct;
                        // 回撤着色：0-20% 浅红，20-35% 中红，35-50% 深红，50%+ 极深红
                        let ddBg;
                        if (dd >= 50) ddBg = 'rgba(220,38,38,0.55)';
                        else if (dd >= 35) ddBg = 'rgba(220,38,38,0.38)';
                        else if (dd >= 20) ddBg = 'rgba(220,38,38,0.22)';
                        else ddBg = 'rgba(220,38,38,0.10)';
                        drawdownHtml = `<span class="index-down" style="padding:2px 6px;border-radius:3px;background:${ddBg};" title="最高 ${idx.drawdown.high_price} (${idx.drawdown.high_date})，距今 ${idx.drawdown.days_since_high} 天">-${dd.toFixed(2)}%</span>`;
                    }
                    // 合并轮动数据
                    const rot = rotationByCode[idx.code] || {};
                    const momentum = rot.momentum;
                    const rankToday = rot.rank_change_pct;
                    const rank3d = rot.rank_change_pct_3d;
                    const rank7d = rot.rank_change_pct_7d;
                    // 排名变化：7日排名 → 今日排名（数值变小=上升）
                    let rankChangeHtml = '<span class="rank-change-flat">—</span>';
                    if (rankToday != null && rank7d != null) {
                        const rankChange = rank7d - rankToday; // 正=上升
                        if (rankChange > 0) rankChangeHtml = `<span class="rank-change-up">↑${rankChange}</span>`;
                        else if (rankChange < 0) rankChangeHtml = `<span class="rank-change-down">↓${Math.abs(rankChange)}</span>`;
                    }
                    const momentumHtml = (momentum == null)
                        ? '<span class="index-flat">—</span>'
                        : `<span class="${momentum >= 60 ? 'index-up' : (momentum <= 40 ? 'index-down' : 'index-flat')}" title="${buildMomentumTooltip(rot)}">${momentum.toFixed(1)}</span>`;
                    const fmtRank = (v) => (v == null) ? '<span class="index-flat">—</span>' : v;
                    // 对比复选框：是否已选中
                    const isCompareSelected = compareSelectedSectors.some(s => s.code === idx.code);
                    return `
                        <tr class="${followedClass}">
                            <td class="compare-col"><input type="checkbox" class="compare-checkbox" ${isCompareSelected ? 'checked' : ''} onchange="toggleSectorCompare('${idx.code}', '${idx.name}')" title="勾选后可对比"></td>
                            <td><button class="${starClass}" onclick="toggleFollowIndex('${idx.code}')" title="${isFollowed ? '取消关注' : '关注'}">${starIcon}</button></td>
                            <td>${idx.code}</td>
                            <td>${idx.name}</td>
                            <td>${idx.price.toFixed(2)}</td>
                            <td>${todayChangeHtml}</td>
                            <td>${formatMultiDayChange(idx.change_pct_3d)}</td>
                            <td>${formatMultiDayChange(idx.change_pct_7d)}</td>
                            <td>${drawdownHtml}</td>
                            <td class="rotation-col">${momentumHtml}</td>
                            <td class="rotation-col">${fmtRank(rankToday)}</td>
                            <td class="rotation-col">${fmtRank(rank3d)}</td>
                            <td class="rotation-col">${fmtRank(rank7d)}</td>
                            <td class="rotation-col">${rankChangeHtml}</td>
                            <td class="rotation-col">${formatCrossoverText(idx.crossover)}</td>
                            <td>
                                <button class="kline-btn" onclick="showKline('${idx.code}', '${idx.name}')">K线</button>
                                <button class="radar-btn" onclick="showRadarDrawer('${idx.code}')" title="动量雷达图">📊</button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // 更新排序箭头
            document.querySelectorAll('.index-table th.sortable .sort-arrow').forEach(el => {
                el.className = 'sort-arrow';
            });
            const activeTh = document.querySelector(`.index-table th.sortable[onclick*="${industrySortField}"]`);
            if (activeTh) {
                activeTh.querySelector('.sort-arrow').className = `sort-arrow ${industrySortOrder}`;
            }
            if (window.perfMonitor) window.perfMonitor.end('renderIndustryIndices');
        }

        // 搜索过滤行业指数
        function filterIndustryIndices() {
            const searchInput = document.getElementById('index-search-input');
            const clearBtn = document.getElementById('index-search-clear');
            if (clearBtn) {
                clearBtn.style.display = searchInput.value ? 'block' : 'none';
            }
            renderIndustryIndices();
        }

        // 切换行业指数 / 概念板块 Tab
        function switchIndustryTab(tab) {
            if (currentIndustryTab === tab) return;
            currentIndustryTab = tab;
            document.querySelectorAll('.industry-tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tab);
            });
            // 切换 Tab 时重置排序为默认（按今日涨跌幅降序）
            industrySortField = 'followed';
            industrySortOrder = 'desc';
            renderIndustryIndices();
        }

        // 清除搜索
        function clearIndexSearch() {
            const searchInput = document.getElementById('index-search-input');
            const clearBtn = document.getElementById('index-search-clear');
            if (searchInput) searchInput.value = '';
            if (clearBtn) clearBtn.style.display = 'none';
            renderIndustryIndices();
        }

        // ========== 智能筛选器 ==========
        // 切换筛选面板展开/收起
        function toggleScreener() {
            const panel = document.getElementById('screener-panel');
            const btn = document.getElementById('screener-toggle-btn');
            if (!panel) return;
            panel.classList.toggle('expanded');
            const isExpanded = panel.classList.contains('expanded');
            if (btn) btn.classList.toggle('active', isExpanded);
        }

        // 读取 min-max 范围输入框
        function readScreenerRange(minId, maxId) {
            const minEl = document.getElementById(minId);
            const maxEl = document.getElementById(maxId);
            const min = (minEl && minEl.value !== '') ? parseFloat(minEl.value) : null;
            const max = (maxEl && maxEl.value !== '') ? parseFloat(maxEl.value) : null;
            return { min, max };
        }

        // 从 DOM 读取筛选条件并重新渲染
        function applyScreener() {
            screenerFilters.trends = Array.from(document.querySelectorAll('.screener-trend-cb'))
                .filter(cb => cb.checked).map(cb => cb.value);
            screenerFilters.crossovers = Array.from(document.querySelectorAll('.screener-crossover-cb'))
                .filter(cb => cb.checked).map(cb => cb.value);
            screenerFilters.changePctToday = readScreenerRange('screener-change-today-min', 'screener-change-today-max');
            screenerFilters.changePct3d = readScreenerRange('screener-change-3d-min', 'screener-change-3d-max');
            screenerFilters.changePct7d = readScreenerRange('screener-change-7d-min', 'screener-change-7d-max');
            screenerFilters.turnoverRate = readScreenerRange('screener-turnover-min', 'screener-turnover-max');
            screenerFilters.momentum = readScreenerRange('screener-momentum-min', 'screener-momentum-max');
            renderIndustryIndices();
        }

        // 判断筛选器是否有激活的条件
        function isScreenerActive() {
            const f = screenerFilters;
            return f.trends.length > 0 ||
                   f.crossovers.length > 0 ||
                   f.changePctToday.min != null || f.changePctToday.max != null ||
                   f.changePct3d.min != null || f.changePct3d.max != null ||
                   f.changePct7d.min != null || f.changePct7d.max != null ||
                   f.turnoverRate.min != null || f.turnoverRate.max != null ||
                   f.momentum.min != null || f.momentum.max != null;
        }

        // 判断数值是否在指定范围内（范围两端为空表示不限）
        function inScreenerRange(val, range) {
            if (range.min == null && range.max == null) return true;
            if (val == null) return false;
            if (range.min != null && val < range.min) return false;
            if (range.max != null && val > range.max) return false;
            return true;
        }

        // 判断单个板块是否匹配所有筛选条件
        function matchesScreener(idx) {
            const f = screenerFilters;
            // 趋势状态（多选 OR）
            if (f.trends.length > 0) {
                const trend = (idx.crossover && idx.crossover.trend) ? idx.crossover.trend.trend : null;
                if (!trend || !f.trends.includes(trend)) return false;
            }
            // 金叉信号（多选 OR）
            if (f.crossovers.length > 0) {
                const co = idx.crossover;
                let matched = false;
                for (const sig of f.crossovers) {
                    if (sig === 'none') {
                        const hasTrend = co && co.trend && co.trend.trend;
                        const hasMacd = co && (co.macd === 'golden' || co.macd === 'near_golden');
                        const hasMa = co && (co.ma === 'golden' || co.ma === 'near_golden');
                        if (!hasTrend && !hasMacd && !hasMa) { matched = true; break; }
                    } else if (sig === 'macd:golden') {
                        if (co && co.macd === 'golden') { matched = true; break; }
                    } else if (sig === 'ma:golden') {
                        if (co && co.ma === 'golden') { matched = true; break; }
                    } else if (sig === 'macd:near_golden') {
                        if (co && co.macd === 'near_golden') { matched = true; break; }
                    } else if (sig === 'ma:near_golden') {
                        if (co && co.ma === 'near_golden') { matched = true; break; }
                    }
                }
                if (!matched) return false;
            }
            // 涨跌幅范围（今日/3日/7日，AND）
            if (!inScreenerRange(idx.change_pct, f.changePctToday)) return false;
            if (!inScreenerRange(idx.change_pct_3d, f.changePct3d)) return false;
            if (!inScreenerRange(idx.change_pct_7d, f.changePct7d)) return false;
            // 换手率
            if (!inScreenerRange(idx.turnover_rate, f.turnoverRate)) return false;
            // 动量得分（优先取轮动数据，回退 idx 自身字段）
            const rot = rotationByCode[idx.code] || {};
            const momentum = (rot.momentum != null) ? rot.momentum : idx.momentum;
            if (!inScreenerRange(momentum, f.momentum)) return false;
            return true;
        }

        // 重置所有筛选条件
        function resetScreener() {
            screenerFilters = {
                trends: [],
                crossovers: [],
                changePctToday: { min: null, max: null },
                changePct3d: { min: null, max: null },
                changePct7d: { min: null, max: null },
                turnoverRate: { min: null, max: null },
                momentum: { min: null, max: null }
            };
            document.querySelectorAll('.screener-trend-cb, .screener-crossover-cb').forEach(cb => { cb.checked = false; });
            document.querySelectorAll('.screener-range-input').forEach(inp => { inp.value = ''; });
            renderIndustryIndices();
        }

        // 行业指数排序
        function sortIndustryTable(field) {
            if (industrySortField === field) {
                industrySortOrder = industrySortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                industrySortField = field;
                industrySortOrder = 'desc';
            }
            renderIndustryIndices();
        }

        // ========== 板块对比分析 ==========

        // 切换板块对比选中状态（最多 4 个）
        function toggleSectorCompare(code, name) {
            const idx = compareSelectedSectors.findIndex(s => s.code === code);
            if (idx >= 0) {
                // 已选中 → 取消选中
                compareSelectedSectors.splice(idx, 1);
            } else {
                // 未选中 → 添加（限制最多 4 个）
                if (compareSelectedSectors.length >= 4) {
                    alert('最多只能选择 4 个板块进行对比');
                    // 恢复复选框状态（阻止勾选）
                    renderIndustryIndices();
                    return;
                }
                compareSelectedSectors.push({ code: code, name: name });
            }
            updateCompareButton();
            renderIndustryIndices();
        }

        // 更新对比按钮状态（选中≥2 可用）
        function updateCompareButton() {
            const btn = document.getElementById('compare-btn');
            const badge = document.getElementById('compare-count-badge');
            if (!btn || !badge) return;
            const count = compareSelectedSectors.length;
            badge.textContent = count;
            btn.disabled = count < 2;
        }

        // 点击遮罩关闭模态框
        function onCompareOverlayClick(event) {
            if (event.target === event.currentTarget) {
                closeCompareModal();
            }
        }

        // 显示对比模态框
        async function showCompareModal() {
            if (compareSelectedSectors.length < 2) return;
            const modal = document.getElementById('compare-modal');
            const loadingEl = document.getElementById('compare-loading');
            const chartWrap = document.getElementById('compare-chart-wrap');
            const rsPanel = document.getElementById('compare-rs-panel');
            if (!modal) return;

            // 显示模态框 + 加载状态
            modal.classList.add('active');
            loadingEl.style.display = 'block';
            loadingEl.textContent = '加载中...';
            chartWrap.style.display = 'none';
            rsPanel.innerHTML = '';

            // 销毁旧图表
            if (compareChart) {
                compareChart.destroy();
                compareChart = null;
            }

            try {
                // 并行请求所有板块 + 沪深300 的 K 线数据（365 天）
                const sectorPromises = compareSelectedSectors.map(s =>
                    DataService.getKline(s.code, 365, false, 'day').then(data => ({
                        sector: s,
                        klines: (data && data.kline) || []
                    }))
                );
                const indexPromise = DataService.getKline(RS_BENCHMARK_CODE, 365, false, 'day').then(data => ({
                    klines: (data && data.kline) || []
                }));

                const [sectorResults, indexResult] = await Promise.all([
                    Promise.all(sectorPromises),
                    indexPromise
                ]);

                const indexKlines = indexResult.klines;

                // 检查数据有效性
                const validSectors = sectorResults.filter(r => r.klines.length > 0);
                if (validSectors.length === 0) {
                    loadingEl.textContent = '无法获取板块K线数据';
                    return;
                }
                if (indexKlines.length === 0) {
                    loadingEl.textContent = '无法获取沪深300基准数据';
                    return;
                }

                // 找出所有数据集的公共日期（按日期对齐）
                const dateSets = validSectors.map(r => new Set(r.klines.map(k => k.date)));
                dateSets.push(new Set(indexKlines.map(k => k.date)));
                // 取交集
                let commonDates = Array.from(dateSets[0]);
                for (let i = 1; i < dateSets.length; i++) {
                    commonDates = commonDates.filter(d => dateSets[i].has(d));
                }
                commonDates.sort();
                if (commonDates.length === 0) {
                    loadingEl.textContent = '无公共交易日数据';
                    return;
                }

                // 为每个板块构建按日期对齐的收盘价数组 + 归一化
                const sectorDataList = validSectors.map((result, i) => {
                    const closeByDate = {};
                    result.klines.forEach(k => { closeByDate[k.date] = k.close; });
                    const closes = commonDates.map(d => closeByDate[d]);
                    // 归一化：首日 = 100
                    const base = closes[0];
                    const normalized = closes.map(c => base > 0 ? (c / base * 100) : null);
                    // 计算 Mansfield RS
                    const indexCloseByDate = {};
                    indexKlines.forEach(k => { indexCloseByDate[k.date] = k.close; });
                    const indexCloses = commonDates.map(d => indexCloseByDate[d]);
                    const rs = calculateMansfieldRS(closes, indexCloses);
                    return {
                        sector: result.sector,
                        closes: closes,
                        normalized: normalized,
                        rs: rs,
                        color: COMPARE_COLORS[i % COMPARE_COLORS.length]
                    };
                });

                // 隐藏加载、显示图表
                loadingEl.style.display = 'none';
                chartWrap.style.display = 'block';

                // 渲染图表
                renderCompareChart(commonDates, sectorDataList);

                // 渲染 RS 面板
                renderRsPanel(sectorDataList);

            } catch (err) {
                console.error('加载对比数据失败:', err);
                loadingEl.textContent = '加载失败: ' + err.message;
            }
        }

        // 计算 Mansfield RS 比率
        // RS = (ratio[last] / MA(ratio, 250)) * 100
        function calculateMansfieldRS(sectorCloses, indexCloses) {
            const n = Math.min(sectorCloses.length, indexCloses.length);
            if (n === 0) return null;
            // 计算每日比率 ratio[i] = sectorClose[i] / indexClose[i]
            const ratio = [];
            for (let i = 0; i < n; i++) {
                if (sectorCloses[i] != null && indexCloses[i] != null && indexCloses[i] !== 0) {
                    ratio.push(sectorCloses[i] / indexCloses[i]);
                }
            }
            if (ratio.length === 0) return null;
            // 计算 ratio 的 52 周（约 250 交易日）移动平均
            // 数据不足 250 天时用现有全部数据计算
            const maPeriod = Math.min(250, ratio.length);
            let sum = 0;
            for (let i = ratio.length - maPeriod; i < ratio.length; i++) {
                sum += ratio[i];
            }
            const maRatio = sum / maPeriod;
            if (maRatio === 0) return null;
            // RS = (最后一天比率 / MA比率) * 100
            return (ratio[ratio.length - 1] / maRatio) * 100;
        }

        // 渲染对比折线图（归一化，首日 = 100）
        function renderCompareChart(dates, sectorDataList) {
            const canvas = document.getElementById('compare-chart-canvas');
            if (!canvas) return;

            const datasets = sectorDataList.map(sd => ({
                label: sd.sector.name,
                data: sd.normalized,
                borderColor: sd.color,
                backgroundColor: sd.color + '20',
                borderWidth: 2,
                fill: false,
                tension: 0.15,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: sd.color
            }));

            const ctx = canvas.getContext('2d');
            compareChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dates,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                color: ChartPresets.getThemeColors().flat,
                                usePointStyle: true,
                                boxWidth: 10,
                                font: { size: 12 }
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                label: function(context) {
                                    const val = context.parsed.y;
                                    if (val == null) return null;
                                    const sd = sectorDataList[context.datasetIndex];
                                    const rsStr = (sd && sd.rs != null) ? '  RS: ' + sd.rs.toFixed(1) : '';
                                    return context.dataset.label + ': ' + val.toFixed(2) + rsStr;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: { display: true, text: '日期' },
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                autoSkipPadding: 50,
                                color: ChartPresets.getThemeColors().flat
                            },
                            grid: { display: false }
                        },
                        y: {
                            display: true,
                            title: { display: true, text: '归一化价格（首日=100）' },
                            ticks: {
                                color: ChartPresets.getThemeColors().flat
                            },
                            grid: {
                                color: 'rgba(128,128,128,0.12)'
                            }
                        }
                    }
                }
            });
        }

        // 渲染 RS 值面板（右上角显示各板块 RS 值，>100 红，<100 绿）
        function renderRsPanel(sectorDataList) {
            const panel = document.getElementById('compare-rs-panel');
            if (!panel) return;
            panel.innerHTML = sectorDataList.map(sd => {
                const rs = sd.rs;
                const rsStr = rs != null ? rs.toFixed(1) : '—';
                const rsCls = rs != null ? (rs > 100 ? 'rs-up' : 'rs-down') : '';
                const rsLabel = rs != null ? (rs > 100 ? '跑赢大盘' : '跑输大盘') : '数据不足';
                return `
                    <div class="compare-rs-item">
                        <span class="compare-rs-dot" style="background:${sd.color};"></span>
                        <span class="compare-rs-name">${sd.sector.name}</span>
                        <span class="compare-rs-value ${rsCls}">RS: ${rsStr}</span>
                        <span class="compare-rs-label">${rsLabel}</span>
                    </div>
                `;
            }).join('');
        }

        // 关闭对比模态框
        function closeCompareModal() {
            const modal = document.getElementById('compare-modal');
            if (modal) modal.classList.remove('active');
            if (compareChart) {
                compareChart.destroy();
                compareChart = null;
            }
        }

        // 显示K线图
        function showKline(code, name) {
            currentKlineCode = code;
            currentKlineName = name;
            // K线图 section 在 index-market 子视图内，需先切换到该子视图
            var marketEl = document.getElementById('index-market');
            if (marketEl && !marketEl.classList.contains('active')) {
                switchIndexSubView('market');
            }
            document.getElementById('kline-title').textContent = `${name} (${code})`;
            document.getElementById('index-kline-section').style.display = 'block';
            loadKlineData();
            // 延迟滚动，确保子视图切换和布局完成后再滚动
            setTimeout(function() {
                var section = document.getElementById('index-kline-section');
                if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 150);
        }

        // 关闭K线图
        function closeKline() {
            document.getElementById('index-kline-section').style.display = 'none';
            if (klineChart) {
                klineChart.destroy();
                klineChart = null;
            }
            if (indicatorChart) {
                indicatorChart.destroy();
                indicatorChart = null;
            }
            if (volumeChart) {
                volumeChart.destroy();
                volumeChart = null;
            }
            currentKlineCode = '';
            currentKlineData = null;
            allKlineData = null;
            allCrossoverData = null;
        }

        // 加载K线数据
        let _klineReqId = 0;  // 请求版本号，防止快速切换股票时旧请求覆盖新渲染
        async function loadKlineData() {
            if (!currentKlineCode) return;
            const reqId = ++_klineReqId;  // 生成新版本号
            const displayDays = parseInt(document.getElementById('kline-days').value, 10) || 30;
            // 根据启用的指标动态计算前置预热天数（替代硬编码 +60），
            // 确保显示窗口内每个交易日的均线/指标都有完整数据支撑。
            // 主图始终启用 MA5/10/20/60 + BOLL；副图指标按 currentIndicator 动态加入。
            const enabledIndicators = ['ma5', 'ma10', 'ma20', 'ma60', 'boll', currentIndicator];
            const warmupDays = calcWarmupDays(enabledIndicators);
            const fetchDays = Math.min(displayDays + warmupDays, 365);
            try {
                const data = await DataService.getKline(currentKlineCode, fetchDays, false, 'day');
                // 检查版本号：如果已有更新的请求发出，丢弃本次过期结果
                if (reqId !== _klineReqId) return;
                if (data) {
                    const allKlines = data.kline || [];
                    const allCrossoverPoints = data.crossover_points || [];
                    // 保存完整历史数据，供 switchIndicator 切换 BOLL/MA 时重新渲染主图
                    allKlineData = allKlines;
                    allCrossoverData = allCrossoverPoints;
                    currentDisplayDays = displayDays;
                    // 主图：传完整数据 + displayDays，内部计算 MA 后切片显示
                    renderKlineChart(allKlines, allCrossoverPoints, displayDays);
                    // 副图/风险指标：只传显示窗口内的数据
                    const start = Math.max(0, allKlines.length - displayDays);
                    const klines = allKlines.slice(start);
                    renderVolumeChart(klines);
                    renderRiskMetrics(klines);
                    // 初始化指标描述和默认指标图
                    document.getElementById('indicator-desc').textContent = INDICATOR_DESCRIPTIONS[currentIndicator];
                    // 根据当前指标决定副图容器显示状态
                    const indContainer = document.querySelector('.kline-indicator-container');
                    if (indContainer) {
                        indContainer.style.display = (currentIndicator === 'boll' || currentIndicator === 'ma') ? 'none' : 'block';
                    }
                    renderIndicatorChart(klines);
                }
            } catch (err) {
                console.error('加载K线数据失败:', err);
            }
        }

        // 计算移动平均线
        function calculateMA(data, period) {
            const result = [];
            for (let i = 0; i < data.length; i++) {
                if (i < period - 1) {
                    result.push(null);
                } else {
                    let sum = 0;
                    for (let j = i - period + 1; j <= i; j++) {
                        sum += data[j];
                    }
                    result.push(sum / period);
                }
            }
            return result;
        }

        // 日期转周几
        function dateToWeekday(dateStr) {
            try {
                const date = new Date(dateStr);
                const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
                return weekdays[date.getDay()];
            } catch (e) {
                return dateStr;
            }
        }

        // 渲染K线图（使用 Chart.js）
        // allKlines: 完整历史数据（含 MA 计算所需的缓冲期）
        // allCrossoverPoints: 完整历史金叉点
        // displayDays: 实际显示的天数（只渲染 allKlines 的最后 displayDays 天）
        function renderKlineChart(allKlines, allCrossoverPoints, displayDays) {
            const canvas = document.getElementById('kline-canvas');
            if (!canvas || !allKlines || allKlines.length === 0) return;

            if (klineChart) {
                klineChart.destroy();
            }

            // 日期字符串 -> 时间戳（ms）。chartjs-chart-financial 0.2.1 candlestick 的
            // FinancialController 设置 parsing:false，要求 dataset 数据为对象格式，
            // x 轴为 timeseries，t 字段需要可排序的数值（时间戳）。
            const toTs = (dateStr) => {
                // dateStr 形如 'YYYY-MM-DD'，构造为 UTC 0 点避免时区偏移
                const parts = String(dateStr).split('-');
                if (parts.length !== 3) return Date.parse(dateStr);
                const [y, m, d] = parts.map(Number);
                return Date.UTC(y, m - 1, d);
            };

            // 用完整历史数据计算 MA / BOLL，确保显示窗口起始日的均线已有完整数据支撑。
            // calculateMA 在数据不足时返回 null，切片后 null 会被 toXY 过滤，不影响渲染。
            const allCloses = allKlines.map(k => k.close);
            const ma5Full = calculateMA(allCloses, 5);
            const ma10Full = calculateMA(allCloses, 10);
            const ma20Full = calculateMA(allCloses, 20);
            const ma60Full = calculateMA(allCloses, 60);

            // 切片：只渲染最后 displayDays 天
            const start = Math.max(0, allKlines.length - (displayDays || allKlines.length));
            const slice = (arr) => arr.slice(start);
            const klines = slice(allKlines);

            // 保存当前 K 线数据供其他函数访问（切片后的显示窗口数据）
            window.currentKlineData = klines;
            currentKlineData = klines;

            // 切片后的显示窗口数据（tooltip / crossover 构建使用）
            const labels = klines.map(k => k.date);
            const tsArr = klines.map(k => toTs(k.date));
            const closes = klines.map(k => k.close);
            const ma5 = slice(ma5Full);
            const ma10 = slice(ma10Full);
            const ma20 = slice(ma20Full);
            const ma60 = slice(ma60Full);

            // 将数值数组转为 {x: timestamp, y: value} 对象数组。
            // 注意：parsing:false 时 Chart.js 直接把 data[i] 作为 _parsed[i]，
            // scale 的 getMinMax 会访问 _parsed[i].x，因此不能含 null，需过滤掉。
            // 由于 x 为时间戳，过滤后仍能按日期正确对齐。
            const tc = ChartPresets.getThemeColors();
            const toXY = (arr) => {
                const out = [];
                for (let i = 0; i < arr.length; i++) {
                    const v = arr[i];
                    if (v !== null && v !== undefined) {
                        out.push({ x: tsArr[i], y: v });
                    }
                }
                return out;
            };

            // 金叉标记点：构建散点数据（仅包含金叉日，不含 null）
            // candlestick 不支持 pointStyle 数组，故拆出独立 scatter dataset。
            // parsing:false 下 data 与 pointStyle/pointRadius 等数组必须按索引对齐且不含 null。
            // 只保留显示窗口内的金叉点
            const windowStart = labels[0];
            const cpArr = (allCrossoverPoints || []).filter(p => p.date >= windowStart);
            const crossoverPointData = [];
            const crossoverPointStyles = [];
            const crossoverPointRadii = [];
            const crossoverPointBgColors = [];
            const crossoverPointBorderColors = [];
            for (let i = 0; i < closes.length; i++) {
                const pt = cpArr.find(p => p.date === labels[i]);
                if (pt && closes[i] != null) {
                    crossoverPointData.push({ x: tsArr[i], y: closes[i] });
                    crossoverPointStyles.push('triangle');
                    crossoverPointRadii.push(9);
                    crossoverPointBgColors.push(
                        pt.type === 'macd' ? tc.riseAlpha(0.95) :
                        pt.type === 'ma' ? 'rgba(52, 152, 219, 0.95)' : 'transparent'
                    );
                    crossoverPointBorderColors.push(
                        pt.type === 'macd' ? tc.macdCross :
                        pt.type === 'ma' ? tc.maCross : 'transparent'
                    );
                }
            }

            // 构建数据集（不含成交量，成交量独立副图）
            // 主图改为 candlestick（金融通用蜡烛图），MA 以 line 叠加
            // 注意：chartjs-chart-financial 0.2.1 candlestick 要求 parsing:false，
            // 为避免混合 parsing 模式冲突，所有 dataset 统一使用 parsing:false，
            // 数据全部采用对象格式 {x,y} / {x,o,h,l,c}，x 为时间戳数值(ms)。
            const datasets = [
                {
                    type: 'candlestick',
                    label: 'K线',
                    // candlestick 直接读取 data[i].o/h/l/c；x 为时间戳(ms)，供 timeseries 轴定位。
                    // 注意：FinancialController.overrides 设置 parsing:false，Chart.js 4.x
                    // 在 parsing:false 时 _parsed[i]=data[i]，timeseries 轴读取 _parsed[i].x，
                    // 因此必须用 x 字段而非 t 字段（t 字段仅在 parsing:true 时被自动解析）。
                    data: klines.map(k => ({ x: toTs(k.date), o: k.open, h: k.high, l: k.low, c: k.close })),
                    // 国内习惯：红涨绿跌（颜色读 CSS 变量，支持主题切换）
                    color: {
                        up: tc.rise,       // 收阳（上涨）实体颜色
                        down: tc.fall,     // 收阴（下跌）实体颜色
                        unchanged: tc.flat // 平盘
                    },
                    borderColor: {
                        up: tc.rise,
                        down: tc.fall,
                        unchanged: tc.flat
                    },
                    borderWidth: 1,
                    yAxisID: 'y',
                    order: 1  // 蜡烛主体绘制顺序（数值越大越靠下层）
                },
                {
                    type: 'line',
                    label: 'MA5',
                    data: toXY(ma5),
                    borderColor: tc.ma5,
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: 0,
                    parsing: false  // 统一 parsing:false，数据已是 {x,y} 对象
                },
                {
                    type: 'line',
                    label: 'MA10',
                    data: toXY(ma10),
                    borderColor: tc.ma10,
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: 0,
                    parsing: false
                },
                {
                    type: 'line',
                    label: 'MA20',
                    data: toXY(ma20),
                    borderColor: tc.ma20,
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: 0,
                    parsing: false
                },
                {
                    type: 'line',
                    label: 'MA60',
                    data: toXY(ma60),
                    borderColor: tc.ma60,
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    // MA60 数据较少时（< 60 日）全部为 null，不显示意义不大；保留以备长周期数据
                    hidden: currentIndicator !== 'ma',  // 非 MA 模式下默认隐藏
                    order: 0,
                    parsing: false
                }
            ];

            // 布林带指标：叠加在主图上（带半透明填充区域增强可视性）
            if (currentIndicator === 'boll') {
                // 用完整历史数据计算 BOLL，再切片，确保显示窗口起始日 BOLL 有值
                const bollFull = calculateBOLL(allCloses, 20, 2);
                const boll = {
                    upper: slice(bollFull.upper),
                    mid: slice(bollFull.mid),
                    lower: slice(bollFull.lower)
                };
                // 填充区域：上下轨之间的半透明背景
                const upperDataForFill = boll.upper;
                const lowerDataForFill = boll.lower;
                datasets.push({
                    type: 'line',  // 必须显式指定，否则继承 chart type(candlestick) 会导致 o/h/l/c 读取为 undefined
                    label: 'BOLL通道',
                    data: upperDataForFill.map((v, i) => (v !== null && lowerDataForFill[i] !== null) ? { x: tsArr[i], y: v } : null).filter(p => p !== null),
                    backgroundColor: 'rgba(155, 89, 182, 0.08)',  // BOLL 通道半透明背景（装饰性，非涨跌语义）
                    fill: '+3',  // 填充到 BOLL下轨（当前 dataset index 5 + 3 = index 8）
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: -1,  // 置于底层
                    parsing: false
                });
                datasets.push({
                    type: 'line',  // 必须显式指定，否则继承 candlestick 导致数据无法渲染
                    label: 'BOLL上轨',
                    data: toXY(boll.upper),
                    borderColor: tc.rise,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    borderDash: [5, 3],
                    parsing: false
                });
                datasets.push({
                    type: 'line',
                    label: 'BOLL中轨',
                    data: toXY(boll.mid),
                    borderColor: tc.bollMid,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    parsing: false
                });
                datasets.push({
                    type: 'line',
                    label: 'BOLL下轨',
                    data: toXY(boll.lower),
                    borderColor: tc.fall,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    borderDash: [5, 3],
                    parsing: false
                });
            }

            // 金叉标记点：独立 scatter dataset，叠加在所有图层最上方
            // （candlestick dataset 不支持 pointStyle 数组，故拆出）
            const hasCrossover = crossoverPointData.length > 0;
            if (hasCrossover) {
                datasets.push({
                    type: 'scatter',
                    label: '金叉信号',
                    data: crossoverPointData,
                    pointStyle: crossoverPointStyles,
                    pointRadius: crossoverPointRadii,
                    pointHoverRadius: 12,
                    pointBackgroundColor: crossoverPointBgColors,
                    pointBorderColor: crossoverPointBorderColors,
                    pointBorderWidth: 1.5,
                    yAxisID: 'y',
                    order: -1,  // 最上层
                    parsing: false
                });
            }

            const ctx = canvas.getContext('2d');
            _lastHoverX = null;  // 重置模块级变量（renderKlineChart 时清空）
            klineChart = new Chart(ctx, {
                type: 'candlestick',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    onHover: (event, elements) => {
                        _lastHoverX = event.x;  // 记录鼠标 x 位置供 tooltip 使用
                        handleChartHover(klineChart, event);
                    },
                    plugins: {
                        legend: {
                            // 点击图例：隔离显示该线条（隐藏其他所有线条）
                            onClick: function(e, legendItem, legend) {
                                const index = legendItem.datasetIndex;
                                const chart = legend.chart;
                                const meta = chart.getDatasetMeta(index);

                                // 如果当前点击的是隐藏的，显示它并隐藏其他
                                // 如果当前点击的是显示的，且只有它显示，则显示全部
                                // 否则隔离显示该线条
                                const visibleDatasets = chart.data.datasets.filter((ds, i) => {
                                    const m = chart.getDatasetMeta(i);
                                    return !m.hidden;
                                });

                                if (meta.hidden) {
                                    // 当前隐藏 → 显示它，隐藏其他
                                    chart.data.datasets.forEach((ds, i) => {
                                        chart.getDatasetMeta(i).hidden = (i !== index);
                                    });
                                } else if (visibleDatasets.length === 1) {
                                    // 只有它显示 → 显示全部
                                    chart.data.datasets.forEach((ds, i) => {
                                        chart.getDatasetMeta(i).hidden = false;
                                    });
                                } else {
                                    // 当前显示，且多个显示 → 隔离显示它
                                    chart.data.datasets.forEach((ds, i) => {
                                        chart.getDatasetMeta(i).hidden = (i !== index);
                                    });
                                }
                                chart.update();
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                // parsing:false + 混合长度 dataset 下 dataIndex 和 parsed.x 均不可靠
                                // （index mode 对所有 dataset 返回相同 dataIndex，但不同 dataset 的
                                //   相同 dataIndex 对应不同 x 值，如金叉信号 idx=5 是最后一天，
                                //   K线 idx=5 是第 6 天）。
                                // 改用 onHover 记录的鼠标 x 位置（_lastHoverX）在 x 轴上获取真实时间戳，
                                // 再在 tsArr 中近似查找索引。
                                title: function(items) {
                                    if (!items || items.length === 0) return '';
                                    const chart = this._chart || (items[0] && items[0].chart);
                                    let xVal = null;
                                    if (chart && chart.scales && chart.scales.x && _lastHoverX != null) {
                                        xVal = chart.scales.x.getValueForPixel(_lastHoverX);
                                    }
                                    if (xVal == null) xVal = items[0].parsed.x;
                                    // getValueForPixel 有精度误差，用近似匹配（最近时间戳）
                                    let idx = 0, bestDiff = Infinity;
                                    for (let i = 0; i < tsArr.length; i++) {
                                        const d = Math.abs(tsArr[i] - xVal);
                                        if (d < bestDiff) { bestDiff = d; idx = i; }
                                    }
                                    const k = klines[idx];
                                    return `${k.date} (${dateToWeekday(k.date)})`;
                                },
                                label: function(context) {
                                    const chart = context.chart;
                                    let xVal = null;
                                    if (chart.scales && chart.scales.x && _lastHoverX != null) {
                                        xVal = chart.scales.x.getValueForPixel(_lastHoverX);
                                    }
                                    if (xVal == null) xVal = context.parsed.x;
                                    let idx = 0, bestDiff = Infinity;
                                    for (let i = 0; i < tsArr.length; i++) {
                                        const d = Math.abs(tsArr[i] - xVal);
                                        if (d < bestDiff) { bestDiff = d; idx = i; }
                                    }
                                    const k = klines[idx];
                                    const label = context.dataset.label;
                                    const dsType = context.dataset.type;
                                    // candlestick：显示 OHLC + 涨跌幅 + 金叉提示
                                    if (dsType === 'candlestick') {
                                        const cp = cpArr.find(p => p.date === labels[idx]);
                                        let extra = `  涨跌幅: ${k.change_pct}%`;
                                        if (cp) {
                                            extra += cp.type === 'macd' ? '  ⬆MACD金叉' : '  ⬆MA金叉';
                                        }
                                        return `K线  开:${k.open.toFixed(2)}  高:${k.high.toFixed(2)}  低:${k.low.toFixed(2)}  收:${k.close.toFixed(2)}${extra}`;
                                    }
                                    // 金叉信号散点
                                    if (dsType === 'scatter') {
                                        const cp = cpArr.find(p => p.date === labels[idx]);
                                        if (cp) {
                                            return cp.type === 'macd' ? '⬆ MACD金叉' : '⬆ MA金叉';
                                        }
                                        return null;
                                    }
                                    // MA 等线型：用 idx 从原始切片数组取值
                                    // （context.parsed.y 基于错误 dataIndex，与 title 日期不对应）
                                    let val = null;
                                    if (label === 'MA5') val = ma5[idx];
                                    else if (label === 'MA10') val = ma10[idx];
                                    else if (label === 'MA20') val = ma20[idx];
                                    else if (label === 'MA60') val = ma60[idx];
                                    else {
                                        // BOLL 等其他 line dataset：在 data 中按 x 查找
                                        const dp = context.dataset.data.find(p => p && p.x === tsArr[idx]);
                                        val = dp ? dp.y : null;
                                    }
                                    if (val === null || val === undefined) return null;
                                    return `${label}: ${val.toFixed(2)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        // x 轴使用 timeseries 类型：candlestick FinancialController 的 overrides
                        // 默认就是 timeseries，这里显式声明并自定义 ticks 显示。
                        // timeseries 轴的 ticks.value 是时间戳（ms），用 label 回调转成 MM-DD/周几。
                        x: {
                            type: 'timeseries',
                            display: true,
                            title: { display: true, text: '日期' },
                            ticks: {
                                source: 'data',
                                maxRotation: 0,
                                autoSkip: true,
                                autoSkipPadding: 75,
                                callback: function(value, index, ticks) {
                                    // value 为时间戳(ms)，转成简短日期 + 周几
                                    const d = new Date(value);
                                    if (isNaN(d.getTime())) return '';
                                    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
                                    const dd = String(d.getUTCDate()).padStart(2, '0');
                                    const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getUTCDay()];
                                    return `${mm}-${dd} ${wd}`;
                                }
                            }
                        },
                        y: {
                            display: true,
                            position: 'left',
                            title: { display: true, text: '价格' }
                        }
                    },
                    // 鼠标离开时清除所有图表高亮
                    events: ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove']
                }
            });

            // 鼠标离开 K 线主图时清除联动高亮（先移除旧监听器避免内存泄漏）
            canvas.onmouseleave = null;
            canvas.addEventListener('mouseleave', _clearTooltipHandler);
        }

        // ========== 市场情绪看板 ==========
        let sentimentChart = null;

        async function loadSentimentData() {
            try {
                const data = await DataService.getSentiment();
                renderSentimentDashboard(data);
            } catch (err) {
                console.error('情绪数据加载失败:', err);
            }
        }

        function renderSentimentDashboard(data) {
            const today = data.today || {};
            const history = data.history || [];

            // 温度计
            const score = today.sentiment_score || 0;
            document.getElementById('sentiment-score').textContent = score.toFixed(1);
            document.getElementById('thermometer-bar').style.width = score + '%';
            let desc = '极度悲观';
            if (score >= 80) desc = '极度乐观';
            else if (score >= 60) desc = '情绪偏热';
            else if (score >= 40) desc = '情绪中性';
            else if (score >= 20) desc = '情绪偏冷';
            document.getElementById('sentiment-desc').textContent = desc;

            // 统计卡片
            document.getElementById('limit-up-count').textContent = today.limit_up_count || 0;
            document.getElementById('limit-down-count').textContent = today.limit_down_count || 0;
            document.getElementById('broken-count').textContent = today.broken_limit_count || 0;
            document.getElementById('broken-rate').textContent = (today.broken_rate || 0).toFixed(1) + '%';
            document.getElementById('max-consecutive').textContent = today.max_consecutive || 0;

            // 时序图
            renderSentimentHistoryChart(history);

            // 连板梯队
            renderConsecutiveTiers(today.consecutive_tiers || []);
        }

        function renderSentimentHistoryChart(history) {
            const canvas = document.getElementById('sentiment-history-chart');
            if (!canvas || !history.length) return;
            if (sentimentChart) sentimentChart.destroy();

            const sorted = [...history].reverse();  // 按日期升序
            const tc = ChartPresets.getThemeColors();

            sentimentChart = new Chart(canvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: sorted.map(h => h.date),
                    datasets: [
                        {
                            label: '涨停',
                            data: sorted.map(h => h.limit_up_count),
                            backgroundColor: tc.riseAlpha(0.7),
                            borderColor: tc.rise,
                            borderWidth: 1,
                        },
                        {
                            label: '跌停',
                            data: sorted.map(h => -h.limit_down_count),
                            backgroundColor: tc.fallAlpha(0.7),
                            borderColor: tc.fall,
                            borderWidth: 1,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { title: { display: true, text: '日期' } },
                        y: {
                            title: { display: true, text: '家数' },
                            ticks: {
                                callback: v => Math.abs(v)
                            }
                        }
                    },
                    plugins: {
                        legend: { display: true, position: 'top' },
                        tooltip: {
                            callbacks: {
                                label: c => `${c.dataset.label}: ${Math.abs(c.parsed.y)} 家`
                            }
                        }
                    }
                }
            });
        }

        function renderConsecutiveTiers(tiers) {
            const container = document.getElementById('consecutive-tier-list');
            if (!container) return;
            if (!tiers.length) {
                container.innerHTML = '<div class="index-loading">暂无连板数据</div>';
                return;
            }
            container.innerHTML = tiers.map(t => {
                const stocksHtml = t.stocks.map(s =>
                    `<span class="tier-stock" title="${s.reason}">${s.name}</span>`
                ).join('');
                return `
                    <div class="consecutive-tier-item">
                        <div class="tier-badge tier-${t.tier}">${t.tier}板</div>
                        <div class="tier-count">${t.count} 只</div>
                        <div class="tier-stocks">${stocksHtml}</div>
                    </div>
                `;
            }).join('');
        }

