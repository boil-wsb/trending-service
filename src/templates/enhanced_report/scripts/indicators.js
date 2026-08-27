        // ========== 技术指标相关 ==========

        // ===== 指标预热天数注册表（借鉴 stock-sdk withIndicators 设计）=====
        // 每个指标所需的最小前置 K 线天数（不含当前日）。
        // loadKlineData 根据当前启用的指标动态计算总前置天数，替代硬编码 +60。
        const INDICATOR_WARMUP_DAYS = {
            ma5: 5,
            ma10: 10,
            ma20: 20,
            ma60: 60,
            boll: 20,       // BOLL(20, 2)
            macd: 35,       // EMA(26) + DEA(9) = 35
            kdj: 9,         // KDJ(9, 3, 3)
            rsi: 14,        // RSI(14)
            atr: 14,        // ATR(14, Wilder)
            cci: 14,        // CCI(14)
            obv: 0,         // 无前置需求
        };

        /**
         * 根据启用的指标列表计算 K 线请求所需的总前置天数
         * @param {string[]} enabledIndicators - 启用的指标名（如 ['ma5','ma10','ma20','ma60','boll','macd']）
         * @returns {number} 总前置天数
         */
        function calcWarmupDays(enabledIndicators) {
            if (!enabledIndicators || enabledIndicators.length === 0) return 0;
            return Math.max(...enabledIndicators.map(i => INDICATOR_WARMUP_DAYS[i] || 0));
        }

        // ===== 三图联动：K线/成交量/指标 副图 tooltip 同步 =====
        let _syncTooltipLock = false;  // 防止递归触发

        // 时间戳(ms) -> 'YYYY-MM-DD'（与主图 toTs 的 Date.UTC 对应，统一用 UTC 部分）
        function _tsToDateStr(ts) {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return null;
            const y = d.getUTCFullYear();
            const m = String(d.getUTCMonth() + 1).padStart(2, '0');
            const dd = String(d.getUTCDate()).padStart(2, '0');
            return `${y}-${m}-${dd}`;
        }

        /**
         * 从图表 hover 事件提取当前日期字符串（统一同步基准，替代不可靠的 dataIndex）。
         * 主图（timeseries 轴 + 混合长度 dataset）：dataIndex 不可靠，必须用鼠标 x 像素
         * 反查时间戳；副图（category 轴）：index 与 labels 一一对应，可直接取 label。
         */
        function _getHoverDate(chart, event) {
            if (!chart || !event || !chart.scales || !chart.scales.x) return null;
            const xType = chart.scales.x.type;
            if (xType === 'timeseries' || xType === 'time') {
                // 主图 K线：用鼠标 x 像素反查时间戳（getElementsAtEventForMode 的 index 不可靠）
                const ts = chart.scales.x.getValueForPixel(event.x);
                // 对齐到最近的交易日数据点，避免鼠标落在周末/节假日间隙时找不到精确日期
                const candleDs = (chart.data.datasets || []).find(d => d.type === 'candlestick');
                if (candleDs && candleDs.data && candleDs.data.length) {
                    let best = null, bestDiff = Infinity;
                    for (let i = 0; i < candleDs.data.length; i++) {
                        const p = candleDs.data[i];
                        if (!p) continue;
                        const diff = Math.abs(p.x - ts);
                        if (diff < bestDiff) { bestDiff = diff; best = p.x; }
                    }
                    if (best != null) return _tsToDateStr(best);
                }
                return _tsToDateStr(ts);
            }
            // 副图 category 轴：混合长度 dataset（如 DIF'金叉 scatter 仅少量点）下，
            // getElementsAtEventForMode 返回元素的 index 是 dataset 内索引，不可靠；
            // 统一改用鼠标 x 像素反查 category 索引（与主图 timeseries 轴处理一致）。
            const idx = Math.round(chart.scales.x.getValueForPixel(event.x));
            const labels = chart.data.labels || [];
            if (idx >= 0 && idx < labels.length) {
                return labels[idx];
            }
            return null;
        }

        /**
         * 在目标图表中按日期字符串查找数据索引。
         * 主图/副图的 labels 均为切片后日期数组，与 candlestick 数据一一对应，indexOf 即可。
         */
        function _findIndexByDate(chart, dateStr) {
            if (!chart || !dateStr) return -1;
            const labels = chart.data.labels;
            if (labels && labels.length) {
                const idx = labels.indexOf(dateStr);
                if (idx >= 0) return idx;
            }
            // 后备：candlestick 数据按时间戳匹配
            const candleDs = (chart.data.datasets || []).find(d => d.type === 'candlestick');
            if (candleDs && candleDs.data) {
                for (let i = 0; i < candleDs.data.length; i++) {
                    if (candleDs.data[i] && _tsToDateStr(candleDs.data[i].x) === dateStr) return i;
                }
            }
            return -1;
        }

        /**
         * 同步三个图表的 tooltip 高亮（按日期值对齐，而非 dataIndex）
         * @param {Chart} sourceChart  触发源图表
         * @param {string} dateStr     当前 hover 的日期 'YYYY-MM-DD'
         * @param {object} eventPos    源图表的鼠标位置（可选）
         */
        function syncChartsTooltip(sourceChart, dateStr, eventPos) {
            if (_syncTooltipLock || !dateStr) return;
            _syncTooltipLock = true;
            // 用 requestAnimationFrame 延迟同步，让源图表的原生 tooltip 先完成更新与渲染，
            // 避免同步调用 c.update('none') 阻塞 event 处理导致源图表 tooltip opacity 为 0。
            requestAnimationFrame(() => {
                try {
                    const charts = [klineChart, volumeChart, indicatorChart];
                    charts.forEach(c => {
                        if (!c || c === sourceChart) return;
                        // 按日期在目标图表中定位 index（解决混合长度 dataset 下 dataIndex 错位）
                        const dataIndex = _findIndexByDate(c, dateStr);
                        if (dataIndex < 0) return;  // 该图表无此日期，跳过
                        // 找到第一个非隐藏 dataset 来设置 active element
                        let dsIdx = 0;
                        for (let i = 0; i < c.data.datasets.length; i++) {
                            const meta = c.getDatasetMeta(i);
                            if (meta && !meta.hidden) { dsIdx = i; break; }
                        }
                        // 主图（klineChart）tooltip callback 依赖 _lastHoverX 定位，
                        // 副图联动时需根据日期更新 _lastHoverX，否则主图 tooltip 显示错误数据。
                        if (c === klineChart && typeof _lastHoverX !== 'undefined') {
                            try {
                                const candleDs = c.data.datasets.find(d => d.type === 'candlestick');
                                if (candleDs && candleDs.data[dataIndex] && c.scales && c.scales.x) {
                                    _lastHoverX = c.scales.x.getPixelForValue(candleDs.data[dataIndex].x);
                                }
                            } catch (e) {}
                            // 主图有混合长度 dataset（金叉信号 scatter 仅几个点），
                            // setActiveElements 传入的 index 会对 scatter 越界，触发
                            // hoverBorderColor 解析 t.toString 错误。跳过 setActiveElements，
                            // 只用 tooltip.setActiveElements + render 触发 tooltip callback。
                        } else {
                            c.setActiveElements([{ datasetIndex: dsIdx, index: dataIndex }]);
                        }
                        // 用目标 chart 的 canvas 中心作为 eventPosition，避免 (0,0) 导致 tooltip 不渲染
                        const canvas = c.canvas;
                        const xPos = canvas ? canvas.width / 2 : 0;
                        const yPos = canvas ? canvas.height / 2 : 0;
                        c.tooltip.setActiveElements([{ datasetIndex: dsIdx, index: dataIndex }], { x: xPos, y: yPos });
                        // 用 render() 代替 update('none')：只触发渲染，不重新计算数据集，更轻量
                        c.render();
                    });
                } finally {
                    _syncTooltipLock = false;
                }
            });
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
                    c.update('none');
                });
            } finally {
                _syncTooltipLock = false;
            }
        }

        // 具名 mouseleave handler，便于 addEventListener 前移除旧监听器（避免内存泄漏）
        const _clearTooltipHandler = () => clearChartsTooltip();

        /**
         * 通用 onHover 处理：提取当前 hover 的日期并同步三图 tooltip。
         * 主图（timeseries）用鼠标 x 像素反查日期；副图（category）用 index 查 labels。
         * 不用 getElementsAtEventForMode 的 index 直接同步，因混合长度 dataset 下该 index 不可靠。
         * @param {Chart} chart   当前图表实例
         * @param {Event} event   鼠标事件
         */
        function handleChartHover(chart, event) {
            if (!chart || !event) return;
            const dateStr = _getHoverDate(chart, event);
            if (dateStr) {
                syncChartsTooltip(chart, dateStr, { x: event.x, y: event.y });
            }
        }

        // 指标概念描述
        const INDICATOR_DESCRIPTIONS = {
            macd: "MACD（移动平均收敛发散指标）：反映价格趋势的强弱和方向。DIF 上穿 DEA 为金叉（买入信号），下穿为死叉（卖出信号）。DIF'/DEA'（虚线）为对应一阶导数（中心差分），反映变化率：导数由负转正=趋势向上加速，由正转负=趋势向下加速。DIF' 上穿 DEA' 为导数金叉（紫色菱形标记），比 MACD 金叉更灵敏，反映动量加速拐点。",
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
            // 必须用完整历史数据（allKlineData）而非切片数据（currentKlineData），
            // 否则 MA60/BOLL 等长周期指标因前置数据不足导致显示窗口内大量 null
            if ((ind === 'boll' || ind === 'ma') && allKlineData) {
                renderKlineChart(allKlineData, allCrossoverData, currentDisplayDays);
            }
            // 隐藏/显示指标副图容器（主图叠加型指标隐藏副图）
            const indContainer = document.querySelector('.kline-indicator-container');
            if (indContainer) {
                indContainer.style.display = (ind === 'boll' || ind === 'ma') ? 'none' : 'block';
            }
            // 重新渲染指标图（副图指标才需要）
            if (allKlineData && ind !== 'boll' && ind !== 'ma') {
                renderIndicatorChart(allKlineData);
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

            const labelsAll = klines.map(k => k.date);
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
                // DIF'/DEA' 导数金叉标记：DIF 导数上穿 DEA 导数（紫色菱形，叠加在 0 轴）
                // 使用等长对象数组（非交叉日 {x,y:null}）而非 null 元素：
                // 多个含 null 元素的 scatter 会触发 Chart.js ScatterController 解析 null.x 错误，
                // 导致整个副图渲染失败（图例/内容消失）；对象数组保持 dataIndex 与 category 对齐。
                const derivCrossData = labelsAll.map(d => ({ x: d, y: null }));
                for (let i = 1; i < difDiff.length; i++) {
                    if (difDiff[i] != null && deaDiff[i] != null &&
                        difDiff[i - 1] != null && deaDiff[i - 1] != null) {
                        if (difDiff[i] > deaDiff[i] && difDiff[i - 1] <= deaDiff[i - 1]) {
                            derivCrossData[i] = { x: labelsAll[i], y: 0 };
                        }
                    }
                }
                if (derivCrossData.some(v => v && v.y === 0)) {
                    datasets.push({
                        type: 'scatter',
                        label: "DIF'金叉",
                        data: derivCrossData,
                        pointStyle: 'rectRot',
                        pointRadius: 5,
                        pointBackgroundColor: 'rgba(142, 68, 173, 0.95)',
                        pointBorderColor: '#8e44ad',
                        order: 0
                    });
                }
                // MACD 死叉标记：DIF 下穿 DEA（绿色倒三角，叠加在 0 轴）
                const macdDeathData = labelsAll.map(d => ({ x: d, y: null }));
                for (let i = 1; i < macd.length; i++) {
                    if (dif[i] < dea[i] && dif[i - 1] >= dea[i - 1]) {
                        macdDeathData[i] = { x: labelsAll[i], y: 0 };
                    }
                }
                if (macdDeathData.some(v => v && v.y === 0)) {
                    datasets.push({
                        type: 'scatter',
                        label: 'MACD死叉',
                        data: macdDeathData,
                        pointStyle: 'triangle',
                        pointRotation: 180,
                        pointRadius: 5,
                        pointBackgroundColor: 'rgba(39, 174, 96, 0.95)',
                        pointBorderColor: '#27ae60',
                        order: 0
                    });
                }
                // DIF'/DEA' 导数死叉标记：DIF 导数下穿 DEA 导数（绿色菱形）
                const derivDeathData = labelsAll.map(d => ({ x: d, y: null }));
                for (let i = 1; i < difDiff.length; i++) {
                    if (difDiff[i] != null && deaDiff[i] != null &&
                        difDiff[i - 1] != null && deaDiff[i - 1] != null) {
                        if (difDiff[i] < deaDiff[i] && difDiff[i - 1] >= deaDiff[i - 1]) {
                            derivDeathData[i] = { x: labelsAll[i], y: 0 };
                        }
                    }
                }
                if (derivDeathData.some(v => v && v.y === 0)) {
                    datasets.push({
                        type: 'scatter',
                        label: "DIF'死叉",
                        data: derivDeathData,
                        pointStyle: 'rectRot',
                        pointRadius: 5,
                        pointBackgroundColor: 'rgba(39, 174, 96, 0.95)',
                        pointBorderColor: '#27ae60',
                        order: 0
                    });
                }
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

            // 显示窗口切片：指标基于完整历史（含预热期）计算，保证 DIF/DEA 等 EMA 递归
            // 指标与后端金叉检测使用的完整数据一致；仅渲染最后 currentDisplayDays 天。
            const start = Math.max(0, klines.length - currentDisplayDays);
            const labels = labelsAll.slice(start);
            datasets = datasets.map(ds => {
                const d = { ...ds };
                if (Array.isArray(d.data)) d.data = d.data.slice(start);
                // 与 data 等长的样式配置数组（如 MACD 柱的 backgroundColor/borderColor）必须同步切片，
                // 否则颜色数组仍是完整长度，与切片后的柱子索引错位，导致颜色与数值不匹配。
                for (const key of ['backgroundColor', 'borderColor', 'pointBackgroundColor',
                                   'pointBorderColor', 'pointStyle', 'pointRadius']) {
                    if (Array.isArray(d[key])) d[key] = d[key].slice(start);
                }
                return d;
            });

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
                        handleChartHover(indicatorChart, event);
                    },
                    plugins: {
                        legend: { display: true },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                title: function(items) {
                                    if (!items || !items.length) return '';
                                    return `${items[0].label} (${dateToWeekday(items[0].label)})`;
                                },
                                label: function(context) {
                                    const label = context.dataset.label || '';
                                    if (label === "DIF'金叉") return '⬆ DIF\'金叉';
                                    if (label === 'MACD死叉') return '⬇ MACD死叉';
                                    if (label === "DIF'死叉") return '⬇ DIF\'死叉';
                                    const val = context.parsed.y;
                                    if (val === null || val === undefined) return null;
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

            // 鼠标离开指标图时清除联动高亮（先移除旧监听器避免内存泄漏）
            canvas.onmouseleave = null;
            canvas.addEventListener('mouseleave', _clearTooltipHandler);
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
                        handleChartHover(volumeChart, event);
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
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

            // 鼠标离开成交量图时清除联动高亮（先移除旧监听器避免内存泄漏）
            canvas.onmouseleave = null;
            canvas.addEventListener('mouseleave', _clearTooltipHandler);
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

            // 加载数据源状态 + 启动轮询（借鉴 usePolling 的 pauseOnHidden）
            // 页面隐藏时自动暂停，恢复时若过期则立即刷新
            if (typeof DataService !== 'undefined' && DataService.createPoller) {
                DataService.createPoller(fetchSourceStatus, 30000).start();
            } else {
                // 兜底：DataService 未加载时降级到裸 setInterval
                fetchSourceStatus();
                setInterval(fetchSourceStatus, 30000);
            }

            // 渲染图表（会等待 Chart.js 加载）
            renderAllCharts();
        });
