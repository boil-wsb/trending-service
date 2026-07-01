        // ========== 技术指标相关 ==========

        // ===== 三图联动：K线/成交量/指标 副图 tooltip 同步 =====
        let _syncTooltipLock = false;  // 防止递归触发

        /**
         * 同步三个图表的 tooltip 高亮
         * @param {Chart} sourceChart  触发源图表
         * @param {number} dataIndex   数据索引
         */
        function syncChartsTooltip(sourceChart, dataIndex) {
            if (_syncTooltipLock) return;
            _syncTooltipLock = true;
            try {
                const charts = [klineChart, volumeChart, indicatorChart];
                charts.forEach(c => {
                    if (!c || c === sourceChart) return;
                    // 找到第一个非隐藏 dataset 来设置 active element
                    let dsIdx = 0;
                    for (let i = 0; i < c.data.datasets.length; i++) {
                        const meta = c.getDatasetMeta(i);
                        if (meta && !meta.hidden) { dsIdx = i; break; }
                    }
                    c.setActiveElements([{ datasetIndex: dsIdx, index: dataIndex }]);
                    c.tooltip.setActiveElements([{ datasetIndex: dsIdx, index: dataIndex }], { x: 0, y: 0 });
                    c.update();
                });
            } finally {
                _syncTooltipLock = false;
            }
        }

        /** 清除所有图表的 active 高亮 */
        function clearChartsTooltip() {
            if (_syncTooltipLock) return;
            _syncTooltipLock = true;
            try {
                [klineChart, volumeChart, indicatorChart].forEach(c => {
                    if (!c) return;
                    c.setActiveElements([]);
                    c.tooltip.setActiveElements([], { x: 0, y: 0 });
                    c.update();
                });
            } finally {
                _syncTooltipLock = false;
            }
        }

        // 指标概念描述
        const INDICATOR_DESCRIPTIONS = {
            macd: "MACD（移动平均收敛发散指标）：反映价格趋势的强弱和方向。DIF 上穿 DEA 为金叉（买入信号），下穿为死叉（卖出信号）。DIF'/DEA'（虚线）为对应一阶导数（中心差分），反映变化率：导数由负转正=趋势向上加速，由正转负=趋势向下加速。",
            rsi: 'RSI（相对强弱指标）：衡量价格超买超卖程度，0-100。RSI>70 超买，<30 超卖。',
            kdj: 'KDJ（随机指标）：反映价格位置相对高低。K>D 金叉买入，K<D 死叉卖出。J>100 超买，J<0 超卖。',
            boll: '布林带（Bollinger Bands）：反映价格波动范围。价格触及上轨可能回调，触及下轨可能反弹。',
            ma: '均线系统（MA5/10/20/60）：多周期简单移动平均。多头排列（MA5>MA10>MA20>MA60）为强势趋势，空头排列为弱势。MA60 为中长期支撑/压力线。',
            obv: 'OBV（能量潮指标）：量价关系。价涨量加、价跌量减。OBV 上升=资金净流入，下降=资金净流出。价涨 OBV 跌=顶背离（卖出），价跌 OBV 涨=底背离（买入）。',
            atr: 'ATR（平均真实波幅）：波动率指标。ATR 上升=波动加剧，下降=波动收敛。常用于动态止损（止损=入场价−2×ATR）和仓位管理。',
            cci: 'CCI（顺势指标）：捕捉极端拐点。CCI>+100 超买，<−100 超卖。CCI 从极端区域回到 ±100 内常预示反转。'
        };

        // EMA 计算
        function calculateEMA(data, period) {
            const result = [];
            const k = 2 / (period + 1);
            let ema = data[0];
            for (let i = 0; i < data.length; i++) {
                if (i === 0) {
                    ema = data[0];
                } else {
                    ema = data[i] * k + ema * (1 - k);
                }
                result.push(ema);
            }
            return result;
        }

        // MACD 计算
        function calculateMACD(closes) {
            const ema12 = calculateEMA(closes, 12);
            const ema26 = calculateEMA(closes, 26);
            const dif = closes.map((c, i) => ema12[i] - ema26[i]);
            const dea = calculateEMA(dif, 9);
            const macd = dif.map((d, i) => (d - dea[i]) * 2);
            return { dif, dea, macd };
        }

        // 一阶导数（中心差分）：f'(i) = (f(i+1) - f(i-1)) / 2
        // 首点无前值置 null，末点无后值用简单差分兜底 f'(n-1) = f(n-1) - f(n-2)
        function calculateDerivative(data) {
            const n = data.length;
            if (n === 0) return [];
            if (n === 1) return [null];
            const result = new Array(n).fill(null);
            for (let i = 1; i < n - 1; i++) {
                if (data[i - 1] == null || data[i + 1] == null) {
                    result[i] = null;
                } else {
                    result[i] = (data[i + 1] - data[i - 1]) / 2;
                }
            }
            // 末点兜底：简单差分
            if (data[n - 1] != null && data[n - 2] != null) {
                result[n - 1] = data[n - 1] - data[n - 2];
            }
            return result;
        }

        // RSI 计算
        function calculateRSI(closes, period = 14) {
            const result = [];
            for (let i = 0; i < closes.length; i++) {
                if (i < period) {
                    result.push(null);
                    continue;
                }
                let gains = 0, losses = 0;
                for (let j = i - period + 1; j <= i; j++) {
                    const diff = closes[j] - closes[j - 1];
                    if (diff >= 0) gains += diff;
                    else losses -= diff;
                }
                const avgGain = gains / period;
                const avgLoss = losses / period;
                if (avgLoss === 0) result.push(100);
                else {
                    const rs = avgGain / avgLoss;
                    result.push(100 - 100 / (1 + rs));
                }
            }
            return result;
        }

        // KDJ 计算
        function calculateKDJ(highs, lows, closes, n = 9) {
            let k = 50, d = 50;
            const kArr = [], dArr = [], jArr = [];
            for (let i = 0; i < closes.length; i++) {
                if (i < n - 1) {
                    kArr.push(null); dArr.push(null); jArr.push(null);
                    continue;
                }
                const start = Math.max(0, i - n + 1);
                const highN = Math.max(...highs.slice(start, i + 1));
                const lowN = Math.min(...lows.slice(start, i + 1));
                const rsv = highN === lowN ? 0 : (closes[i] - lowN) / (highN - lowN) * 100;
                k = 2 / 3 * k + 1 / 3 * rsv;
                d = 2 / 3 * d + 1 / 3 * k;
                const j = 3 * k - 2 * d;
                kArr.push(k); dArr.push(d); jArr.push(j);
            }
            return { k: kArr, d: dArr, j: jArr };
        }

        // 布林带计算
        function calculateBOLL(closes, period = 20, multiplier = 2) {
            const mid = [], upper = [], lower = [];
            for (let i = 0; i < closes.length; i++) {
                if (i < period - 1) {
                    mid.push(null); upper.push(null); lower.push(null);
                    continue;
                }
                const start = i - period + 1;
                const slice = closes.slice(start, i + 1);
                const mean = slice.reduce((a, b) => a + b, 0) / period;
                const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period;
                const std = Math.sqrt(variance);
                mid.push(mean);
                upper.push(mean + multiplier * std);
                lower.push(mean - multiplier * std);
            }
            return { mid, upper, lower };
        }

        // 简单移动平均（SMA）—— 复用 index_market.js 中的 calculateMA
        // OBV（能量潮）：价涨量加，价跌量减，价平不变
        function calculateOBV(closes, volumes) {
            if (closes.length === 0) return [];
            const obv = [volumes[0] || 0];
            for (let i = 1; i < closes.length; i++) {
                if (closes[i] > closes[i - 1]) {
                    obv.push(obv[i - 1] + (volumes[i] || 0));
                } else if (closes[i] < closes[i - 1]) {
                    obv.push(obv[i - 1] - (volumes[i] || 0));
                } else {
                    obv.push(obv[i - 1]);
                }
            }
            return obv;
        }

        // ATR（平均真实波幅）
        function calculateATR(highs, lows, closes, period = 14) {
            const n = highs.length;
            if (n === 0) return [];
            const tr = new Array(n).fill(null);
            tr[0] = highs[0] - lows[0];
            for (let i = 1; i < n; i++) {
                const h_l = highs[i] - lows[i];
                const h_pc = Math.abs(highs[i] - closes[i - 1]);
                const l_pc = Math.abs(lows[i] - closes[i - 1]);
                tr[i] = Math.max(h_l, h_pc, l_pc);
            }
            // Wilder 平滑：首点为前 period 个 TR 的简单平均，后续用指数平滑
            const atr = new Array(n).fill(null);
            if (n < period) return atr;
            let sum = 0;
            for (let i = 0; i < period; i++) sum += tr[i];
            atr[period - 1] = sum / period;
            for (let i = period; i < n; i++) {
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period;
            }
            return atr;
        }

        // CCI（顺势指标）
        function calculateCCI(highs, lows, closes, period = 14) {
            const n = highs.length;
            const cci = new Array(n).fill(null);
            if (n < period) return cci;
            for (let i = period - 1; i < n; i++) {
                // 典型价 TP = (高+低+收)/3
                const tpSlice = [];
                for (let j = 0; j < period; j++) {
                    const idx = i - j;
                    tpSlice.push((highs[idx] + lows[idx] + closes[idx]) / 3);
                }
                const tp = (highs[i] + lows[i] + closes[i]) / 3;
                const maTp = tpSlice.reduce((a, b) => a + b, 0) / period;
                const meanDev = tpSlice.reduce((a, b) => a + Math.abs(b - maTp), 0) / period;
                if (meanDev === 0) {
                    cci[i] = 0;
                } else {
                    cci[i] = (tp - maTp) / (0.015 * meanDev);
                }
            }
            return cci;
        }

        // 切换技术指标
        function switchIndicator(ind) {
            currentIndicator = ind;
            document.querySelectorAll('.indicator-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.indicator === ind);
            });
            const descEl = document.getElementById('indicator-desc');
            if (descEl) {
                descEl.textContent = INDICATOR_DESCRIPTIONS[ind] || '';
                // 布林带/均线：主图叠加型指标，添加醒目提示
                if (ind === 'boll') {
                    descEl.innerHTML += ' <span style="color:#9b59b6;font-weight:600;margin-left:8px;">↑ 布林带已叠加在上方K线主图中 ↑</span>';
                } else if (ind === 'ma') {
                    descEl.innerHTML += ' <span style="color:#34495e;font-weight:600;margin-left:8px;">↑ 均线系统已叠加在上方K线主图中（含 MA60 中长期线） ↑</span>';
                }
            }
            // 布林带/均线叠加在主图上，需要重新渲染主图
            if ((ind === 'boll' || ind === 'ma') && currentKlineData) {
                renderKlineChart(currentKlineData);
            }
            // 隐藏/显示指标副图容器（主图叠加型指标隐藏副图）
            const indContainer = document.querySelector('.kline-indicator-container');
            if (indContainer) {
                indContainer.style.display = (ind === 'boll' || ind === 'ma') ? 'none' : 'block';
            }
            // 重新渲染指标图（副图指标才需要）
            if (currentKlineData && ind !== 'boll' && ind !== 'ma') {
                renderIndicatorChart(currentKlineData);
            }
        }

        // 渲染技术指标副图
        function renderIndicatorChart(klines) {
            const canvas = document.getElementById('kline-indicator-canvas');
            if (!canvas || !klines || klines.length === 0) return;
            if (indicatorChart) {
                indicatorChart.destroy();
                indicatorChart = null;
            }
            // 布林带不需要副图
            if (currentIndicator === 'boll') {
                return;
            }

            const labels = klines.map(k => k.date);
            const closes = klines.map(k => k.close);
            const ctx = canvas.getContext('2d');
            let datasets = [];
            let yMin = null, yMax = null;

            if (currentIndicator === 'macd') {
                const { dif, dea, macd } = calculateMACD(closes);
                // DIF / DEA 一阶导数（中心差分），叠加在右侧 Y 轴
                const difDiff = calculateDerivative(dif);
                const deaDiff = calculateDerivative(dea);
                // MACD 柱状图红绿
                const barColors = macd.map(v => v >= 0 ? 'rgba(231, 76, 60, 0.6)' : 'rgba(39, 174, 96, 0.6)');
                datasets = [
                    {
                        label: 'MACD',
                        data: macd,
                        type: 'bar',
                        backgroundColor: barColors,
                        borderColor: barColors.map(c => c.replace('0.6', '1')),
                        borderWidth: 1,
                        order: 3
                    },
                    {
                        label: 'DIF',
                        data: dif,
                        borderColor: '#4a90d9',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        order: 1
                    },
                    {
                        label: 'DEA',
                        data: dea,
                        borderColor: '#f39c12',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        order: 2
                    },
                    {
                        label: "DIF'",
                        data: difDiff,
                        borderColor: 'rgba(74, 144, 217, 0.85)',
                        borderWidth: 1.2,
                        borderDash: [5, 3],
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        yAxisID: 'y1',
                        order: 4
                    },
                    {
                        label: "DEA'",
                        data: deaDiff,
                        borderColor: 'rgba(243, 156, 18, 0.85)',
                        borderWidth: 1.2,
                        borderDash: [5, 3],
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        yAxisID: 'y1',
                        order: 5
                    }
                ];
            } else if (currentIndicator === 'rsi') {
                const rsi = calculateRSI(closes, 14);
                datasets = [
                    {
                        label: 'RSI(14)',
                        data: rsi,
                        borderColor: '#9b59b6',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    }
                ];
                yMin = 0;
                yMax = 100;
            } else if (currentIndicator === 'kdj') {
                const highs = klines.map(k => k.high);
                const lows = klines.map(k => k.low);
                const { k, d, j } = calculateKDJ(highs, lows, closes, 9);
                datasets = [
                    {
                        label: 'K',
                        data: k,
                        borderColor: '#4a90d9',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    },
                    {
                        label: 'D',
                        data: d,
                        borderColor: '#f39c12',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    },
                    {
                        label: 'J',
                        data: j,
                        borderColor: '#e74c3c',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    }
                ];
                // KDJ：J 值可能超出 [0,100]，手动计算实际数据范围并扩展 Y 轴
                // 下限 = min(0, 实际最小值)，上限 = max(100, 实际最大值)
                const kdjAll = [...k, ...d, ...j].filter(v => v !== null && v !== undefined && !isNaN(v));
                if (kdjAll.length > 0) {
                    const dataMin = Math.min(...kdjAll);
                    const dataMax = Math.max(...kdjAll);
                    yMin = Math.min(0, dataMin);
                    yMax = Math.max(100, dataMax);
                }
            } else if (currentIndicator === 'obv') {
                // OBV（能量潮）：量价关系指标
                const volumes = klines.map(k => k.volume || 0);
                const obv = calculateOBV(closes, volumes);
                datasets = [
                    {
                        label: 'OBV',
                        data: obv,
                        borderColor: '#9b59b6',
                        backgroundColor: 'rgba(155, 89, 182, 0.08)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 0
                    }
                ];
            } else if (currentIndicator === 'atr') {
                // ATR（平均真实波幅）：波动率指标
                const highs = klines.map(k => k.high);
                const lows = klines.map(k => k.low);
                const atr = calculateATR(highs, lows, closes, 14);
                datasets = [
                    {
                        label: 'ATR(14)',
                        data: atr,
                        borderColor: '#e67e22',
                        backgroundColor: 'rgba(230, 126, 34, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 0
                    }
                ];
            } else if (currentIndicator === 'cci') {
                // CCI（顺势指标）：拐点识别
                const highs = klines.map(k => k.high);
                const lows = klines.map(k => k.low);
                const cci = calculateCCI(highs, lows, closes, 14);
                datasets = [
                    {
                        label: 'CCI(14)',
                        data: cci,
                        borderColor: '#16a085',
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    }
                ];
                // CCI 参考线在 +100 / -100
                [100, -100].forEach(v => {
                    datasets.push({
                        label: `参考线${v}`,
                        data: closes.map(() => v),
                        borderColor: 'rgba(128, 128, 128, 0.4)',
                        borderWidth: 1,
                        borderDash: [4, 4],
                        fill: false,
                        pointRadius: 0
                    });
                });
                // CCI Y 轴范围固定 ±200，数据超出时自动扩展
                const cciValid = cci.filter(v => v !== null && v !== undefined && !isNaN(v));
                if (cciValid.length > 0) {
                    yMin = Math.min(-200, Math.min(...cciValid));
                    yMax = Math.max(200, Math.max(...cciValid));
                }
            }

            // 参考线（RSI 30/70，KDJ 20/80）
            if (currentIndicator === 'rsi' || currentIndicator === 'kdj') {
                const lines = currentIndicator === 'rsi' ? [30, 70] : [20, 80];
                lines.forEach(v => {
                    datasets.push({
                        label: `参考线${v}`,
                        data: closes.map(() => v),
                        borderColor: 'rgba(128, 128, 128, 0.4)',
                        borderWidth: 1,
                        borderDash: [4, 4],
                        fill: false,
                        pointRadius: 0
                    });
                });
            }

            indicatorChart = new Chart(ctx, {
                type: 'line',
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
                        if (elements && elements.length > 0) {
                            syncChartsTooltip(indicatorChart, elements[0].index);
                        }
                    },
                    plugins: {
                        legend: { display: true },
                        tooltip: {
                            callbacks: {
                                title: function(items) {
                                    if (!items || !items.length) return '';
                                    return `${items[0].label} (${dateToWeekday(items[0].label)})`;
                                },
                                label: function(context) {
                                    const val = context.parsed.y;
                                    if (val === null || val === undefined) return null;
                                    const label = context.dataset.label || '';
                                    if (label.startsWith('参考线')) return null;
                                    return `${label}: ${val.toFixed(3)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: false
                        },
                        y: {
                            position: 'left',
                            ...(yMin !== null ? { min: yMin } : {}),
                            ...(yMax !== null ? { max: yMax } : {})
                        },
                        // 右侧 Y 轴：用于 DIF/DEA 导数（仅 MACD 指标时显示）
                        y1: {
                            position: 'right',
                            display: currentIndicator === 'macd',
                            grid: {
                                drawOnChartArea: false  // 不画水平网格线，避免干扰主轴
                            },
                            ticks: {
                                color: 'rgba(127, 140, 141, 0.85)',
                                font: { size: 10 }
                            },
                            title: {
                                display: currentIndicator === 'macd',
                                text: "DIF' / DEA' 导数",
                                color: 'rgba(127, 140, 141, 0.85)',
                                font: { size: 11 }
                            }
                        }
                    }
                }
            });

            // 鼠标离开指标图时清除联动高亮
            canvas.addEventListener('mouseleave', () => {
                clearChartsTooltip();
            });
        }

        // 渲染成交量副图
        function renderVolumeChart(klines) {
            const canvas = document.getElementById('kline-volume-canvas');
            if (!canvas || !klines || klines.length === 0) return;
            if (volumeChart) volumeChart.destroy();

            const labels = klines.map(k => k.date);
            const volumes = klines.map(k => k.volume || 0);
            // 红绿色：收盘 >= 开盘为红，否则为绿
            const colors = klines.map(k => k.close >= k.open ? 'rgba(231, 76, 60, 0.6)' : 'rgba(39, 174, 96, 0.6)');

            volumeChart = new Chart(canvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '成交量',
                        data: volumes,
                        backgroundColor: colors,
                        borderColor: colors.map(c => c.replace('0.6', '1')),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    onHover: (event, elements) => {
                        if (elements && elements.length > 0) {
                            syncChartsTooltip(volumeChart, elements[0].index);
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                title: function(items) {
                                    if (!items || !items.length) return '';
                                    return `${items[0].label} (${dateToWeekday(items[0].label)})`;
                                },
                                label: function(context) {
                                    return `成交量: ${context.parsed.y.toLocaleString()}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: false  // X 轴标签由主图显示
                        },
                        y: {
                            ticks: {
                                callback: function(value) {
                                    if (value >= 100000000) return (value / 100000000).toFixed(1) + '亿';
                                    if (value >= 10000) return (value / 10000).toFixed(0) + '万';
                                    return value;
                                }
                            }
                        }
                    }
                }
            });

            // 鼠标离开成交量图时清除联动高亮
            canvas.addEventListener('mouseleave', () => {
                clearChartsTooltip();
            });
        }

        // 渲染风险指标卡片
        function renderRiskMetrics(klines) {
            const card = document.getElementById('risk-metrics-card');
            if (!card || !klines || klines.length < 2) return;

            const closes = klines.map(k => k.close);
            // 日收益率
            const returns = [];
            for (let i = 1; i < closes.length; i++) {
                returns.push((closes[i] - closes[i - 1]) / closes[i - 1]);
            }

            // 波动率（年化）
            const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
            const variance = returns.reduce((a, b) => a + Math.pow(b - meanReturn, 2), 0) / returns.length;
            const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100;

            // 最大回撤
            let peak = closes[0], maxDrawdown = 0;
            for (const c of closes) {
                if (c > peak) peak = c;
                const dd = (peak - c) / peak;
                if (dd > maxDrawdown) maxDrawdown = dd;
            }
            maxDrawdown *= 100;

            // 夏普比率（无风险利率 2%）
            const annualReturn = meanReturn * 252 * 100;
            const sharpe = volatility > 0 ? (annualReturn - 2) / volatility : 0;

            // 日均收益率
            const avgDailyReturn = meanReturn * 100;

            // 涨跌比
            const upDays = returns.filter(r => r > 0).length;
            const downDays = returns.filter(r => r < 0).length;
            const upDownRatio = downDays > 0 ? (upDays / downDays).toFixed(2) : '∞';

            const metrics = [
                { label: '年化波动率', value: volatility.toFixed(2) + '%', desc: '价格波动剧烈程度', color: volatility > 30 ? '#e74c3c' : '#333' },
                { label: '最大回撤', value: '-' + maxDrawdown.toFixed(2) + '%', desc: '从最高点到最低点的最大跌幅', color: '#e74c3c' },
                { label: '夏普比率', value: sharpe.toFixed(2), desc: '单位风险的超额回报，>1 为好', color: sharpe > 1 ? '#27ae60' : sharpe < 0 ? '#e74c3c' : '#333' },
                { label: '日均收益率', value: avgDailyReturn.toFixed(3) + '%', desc: '平均每日收益率', color: avgDailyReturn >= 0 ? '#27ae60' : '#e74c3c' },
                { label: '涨跌比', value: upDownRatio, desc: '上涨天数/下跌天数', color: upDays >= downDays ? '#27ae60' : '#e74c3c' }
            ];

            card.innerHTML = metrics.map(m => `
                <div class="risk-metric-item">
                    <div class="risk-metric-label">${m.label}</div>
                    <div class="risk-metric-value" style="color:${m.color}">${m.value}</div>
                    <div class="risk-metric-desc">${m.desc}</div>
                </div>
            `).join('');
        }

        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            init();

            // 加载数据源状态
            fetchSourceStatus();

            // 每30秒刷新一次状态
            setInterval(fetchSourceStatus, 30000);

            // 渲染图表（会等待 Chart.js 加载）
            renderAllCharts();
        });
