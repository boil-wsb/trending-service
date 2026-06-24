        // ========== 指数行情相关 ==========
        let industryIndicesData = [];
        let industrySortField = 'followed';
        let industrySortOrder = 'desc';
        let currentKlineCode = '';
        let currentKlineName = '';
        let klineChart = null;
        let currentIndicator = 'macd';
        let indicatorChart = null;
        let volumeChart = null;
        let currentKlineData = null;

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

        // 手动触发重新拉取指数数据（调用 /api/index/trigger-fetch）
        async function refreshIndexData() {
            const btn = document.getElementById('refresh-index-btn');
            if (!btn) return;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ 拉取中...';
            try {
                const resp = await fetch('/api/index/trigger-fetch', { method: 'POST' });
                const json = await resp.json();
                if (!json.success) throw new Error(json.error || '拉取失败');
                const cnt = json.data && json.data.count ? json.data.count : 0;
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
            try {
                const [marketRes, industryRes] = await Promise.all([
                    fetch('/api/index/market'),
                    fetch('/api/index/industry?limit=1000')
                ]);
                const marketData = await marketRes.json();
                const industryData = await industryRes.json();

                if (marketData.success) {
                    renderMarketIndices(marketData.data.indices || []);
                }
                if (industryData.success) {
                    industryIndicesData = industryData.data.indices || [];
                    renderIndustryIndices();
                }
            } catch (err) {
                console.error('加载指数数据失败:', err);
                document.getElementById('market-indices-grid').innerHTML = '<div class="index-loading">加载失败</div>';
                document.getElementById('industry-indices-body').innerHTML = '<tr><td colspan="13" class="index-loading">加载失败</td></tr>';
            }

            // 加载行业轮动数据
            loadRotationData();
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
                const resp = await fetch('/api/index/rotation');
                const json = await resp.json();
                if (!json.success) throw new Error(json.error || '加载失败');

                rotationData = json.data;
                // 构建 code -> 轮动信息 索引
                rotationByCode = {};
                if (rotationData && rotationData.indices) {
                    rotationData.indices.forEach(item => {
                        rotationByCode[item.code] = item;
                    });
                }
                renderRotationRanking();
                renderRotationHeatmap();
                // 轮动数据已合并到行业指数表，刷新表格以显示动量/排名列
                renderIndustryIndices();
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

        function renderRotationHeatmap() {
            if (!rotationData) return;
            const container = document.getElementById('rotation-heatmap-container');
            if (!container) return;

            const indices = rotationData.indices;
            if (!indices || indices.length === 0) {
                container.innerHTML = '<div class="index-loading">暂无数据</div>';
                return;
            }

            // 按今日涨跌幅着色
            container.innerHTML = `<div class="heatmap-grid">` + indices.map(item => {
                const pct = item.change_pct || 0;
                // 颜色：红涨绿跌，深浅表示幅度
                let bg, color;
                if (pct >= 0) {
                    const intensity = Math.min(Math.abs(pct) / 5, 1);  // 5% 为最大强度
                    const alpha = 0.15 + intensity * 0.75;
                    bg = `rgba(231, 76, 60, ${alpha})`;
                    color = intensity > 0.5 ? '#fff' : '#333';
                } else {
                    const intensity = Math.min(Math.abs(pct) / 5, 1);
                    const alpha = 0.15 + intensity * 0.75;
                    bg = `rgba(39, 174, 96, ${alpha})`;
                    color = intensity > 0.5 ? '#fff' : '#333';
                }
                return `
                    <div class="heatmap-cell" style="background:${bg};color:${color}" 
                         title="${item.name}: ${pct >= 0 ? '+' : ''}${pct}%  成交额:${item.amount}亿"
                         onclick="showKline('${item.code}', '${item.name}')">
                        <div class="heatmap-cell-name">${item.name}</div>
                        <div class="heatmap-cell-value">${pct >= 0 ? '+' : ''}${pct}%</div>
                    </div>
                `;
            }).join('') + `</div>`;
        }

        // 涨跌幅色深：参照热力图，幅度越大颜色越深（红涨绿跌）
        function getChangeDepthBg(pct, maxPct, baseAlpha, peakAlpha) {
            maxPct = (maxPct == null) ? 5 : maxPct;
            baseAlpha = (baseAlpha == null) ? 0.10 : baseAlpha;
            peakAlpha = (peakAlpha == null) ? 0.50 : peakAlpha;
            if (pct == null || isNaN(pct)) return 'transparent';
            if (pct === 0) return 'rgba(149,165,166,0.12)';
            const intensity = Math.min(Math.abs(pct) / maxPct, 1);
            const alpha = baseAlpha + intensity * (peakAlpha - baseAlpha);
            const color = pct >= 0 ? '231, 76, 60' : '39, 174, 96';
            return `rgba(${color}, ${alpha})`;
        }

        // 渲染市场指数卡片
        let marketIndicesCache = [];
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
                return `
                    <div class="market-index-card" style="background:${depthBg}" onclick="showKline('${idx.code}', '${idx.name}')">
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

        // 行业热力图：展开/收起
        function toggleHeatmap() {
            const body = document.getElementById('rotation-heatmap-container');
            const btn = document.getElementById('heatmap-toggle-btn');
            if (!body || !btn) return;
            body.classList.toggle('expanded');
            const textEl = btn.querySelector('.toggle-text');
            if (textEl) textEl.textContent = body.classList.contains('expanded') ? '收起' : '展开';
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
        function renderIndustryIndices() {
            const tbody = document.getElementById('industry-indices-body');
            const countDisplay = document.getElementById('industry-count-display');
            const followedBadge = document.getElementById('followed-count-display');
            const followedNumEl = document.getElementById('followed-count-num');
            if (!industryIndicesData || industryIndicesData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="13" class="index-loading">暂无数据</td></tr>';
                if (countDisplay) countDisplay.textContent = '';
                if (followedBadge) followedBadge.style.display = 'none';
                return;
            }

            // 搜索过滤
            const searchInput = document.getElementById('index-search-input');
            const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
            let filtered = industryIndicesData;
            if (query) {
                filtered = industryIndicesData.filter(idx =>
                    idx.code.toLowerCase().includes(query) ||
                    idx.name.toLowerCase().includes(query)
                );
            }

            // 获取关注列表
            const followedSet = new Set(getFollowedIndices());

            // 排序
            const sorted = [...filtered].sort((a, b) => {
                // 如果排序字段是 'followed'，按关注状态排序（关注的在前）
                if (industrySortField === 'followed') {
                    const aFollowed = followedSet.has(a.code) ? 1 : 0;
                    const bFollowed = followedSet.has(b.code) ? 1 : 0;
                    return industrySortOrder === 'asc' ? aFollowed - bFollowed : bFollowed - aFollowed;
                }
                // 其他排序字段：关注的始终优先，组内按当前字段排序
                const aFollowed = followedSet.has(a.code) ? 1 : 0;
                const bFollowed = followedSet.has(b.code) ? 1 : 0;
                if (aFollowed !== bFollowed) {
                    return bFollowed - aFollowed;  // 关注的在前
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
                if (query) {
                    countDisplay.textContent = `${filtered.length} / ${industryIndicesData.length} 条`;
                } else {
                    countDisplay.textContent = `共 ${industryIndicesData.length} 条`;
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
                tbody.innerHTML = '<tr><td colspan="13" class="index-loading">未找到匹配的数据</td></tr>';
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
                        : `<span class="${momentum >= 0 ? 'index-up' : 'index-down'}">${momentum >= 0 ? '+' : ''}${momentum}</span>`;
                    const fmtRank = (v) => (v == null) ? '<span class="index-flat">—</span>' : v;
                    return `
                        <tr class="${followedClass}">
                            <td><button class="${starClass}" onclick="toggleFollowIndex('${idx.code}')" title="${isFollowed ? '取消关注' : '关注'}">${starIcon}</button></td>
                            <td>${idx.code}</td>
                            <td>${idx.name}</td>
                            <td>${idx.price.toFixed(2)}</td>
                            <td>${todayChangeHtml}</td>
                            <td>${formatMultiDayChange(idx.change_pct_3d)}</td>
                            <td>${formatMultiDayChange(idx.change_pct_7d)}</td>
                            <td class="rotation-col">${momentumHtml}</td>
                            <td class="rotation-col">${fmtRank(rankToday)}</td>
                            <td class="rotation-col">${fmtRank(rank3d)}</td>
                            <td class="rotation-col">${fmtRank(rank7d)}</td>
                            <td class="rotation-col">${rankChangeHtml}</td>
                            <td><button class="kline-btn" onclick="showKline('${idx.code}', '${idx.name}')">K线</button></td>
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

        // 清除搜索
        function clearIndexSearch() {
            const searchInput = document.getElementById('index-search-input');
            const clearBtn = document.getElementById('index-search-clear');
            if (searchInput) searchInput.value = '';
            if (clearBtn) clearBtn.style.display = 'none';
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

        // 显示K线图
        function showKline(code, name) {
            currentKlineCode = code;
            currentKlineName = name;
            document.getElementById('kline-title').textContent = `${name} (${code})`;
            document.getElementById('index-kline-section').style.display = 'block';
            loadKlineData();
            // 滚动到K线区域
            document.getElementById('index-kline-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        }

        // 加载K线数据
        async function loadKlineData() {
            if (!currentKlineCode) return;
            const days = document.getElementById('kline-days').value;
            try {
                const res = await fetch(`/api/index/kline?code=${currentKlineCode}&days=${days}`);
                const data = await res.json();
                if (data.success) {
                    const klines = data.data.kline || [];
                    renderKlineChart(klines);
                    renderVolumeChart(klines);
                    renderRiskMetrics(klines);
                    // 初始化指标描述和默认指标图
                    document.getElementById('indicator-desc').textContent = INDICATOR_DESCRIPTIONS[currentIndicator];
                    // 根据当前指标决定副图容器显示状态
                    const indContainer = document.querySelector('.kline-indicator-container');
                    if (indContainer) {
                        indContainer.style.display = (currentIndicator === 'boll') ? 'none' : 'block';
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
        function renderKlineChart(klines) {
            const canvas = document.getElementById('kline-canvas');
            if (!canvas || !klines || klines.length === 0) return;

            if (klineChart) {
                klineChart.destroy();
            }

            // 保存当前 K 线数据供其他函数访问
            window.currentKlineData = klines;
            currentKlineData = klines;

            const labels = klines.map(k => k.date);
            const opens = klines.map(k => k.open);
            const closes = klines.map(k => k.close);
            const highs = klines.map(k => k.high);
            const lows = klines.map(k => k.low);

            // 计算移动平均线
            const ma5 = calculateMA(closes, 5);
            const ma10 = calculateMA(closes, 10);
            const ma20 = calculateMA(closes, 20);

            // 构建数据集（不含成交量，成交量独立副图）
            const datasets = [
                {
                    label: '收盘价',
                    data: closes,
                    borderColor: '#4a90d9',
                    backgroundColor: 'rgba(74, 144, 217, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    yAxisID: 'y'
                },
                {
                    label: '开盘价',
                    data: opens,
                    borderColor: '#f39c12',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    hidden: true
                },
                {
                    label: '最高价',
                    data: highs,
                    borderColor: '#e74c3c',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    hidden: true
                },
                {
                    label: '最低价',
                    data: lows,
                    borderColor: '#27ae60',
                    borderWidth: 1,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    hidden: true
                },
                {
                    label: 'MA5',
                    data: ma5,
                    borderColor: '#9b59b6',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0
                },
                {
                    label: 'MA10',
                    data: ma10,
                    borderColor: '#e67e22',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0
                },
                {
                    label: 'MA20',
                    data: ma20,
                    borderColor: '#1abc9c',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0
                }
            ];

            // 布林带指标：叠加在主图上（带半透明填充区域增强可视性）
            if (currentIndicator === 'boll') {
                const boll = calculateBOLL(closes, 20, 2);
                // 填充区域：上下轨之间的半透明背景
                const upperDataForFill = boll.upper;
                const lowerDataForFill = boll.lower;
                datasets.push({
                    label: 'BOLL通道',
                    data: upperDataForFill.map((v, i) => v !== null && lowerDataForFill[i] !== null ? v : null),
                    backgroundColor: 'rgba(155, 89, 182, 0.08)',
                    fill: '-3',  // 填充到 BOLL下轨（当前 dataset index + 3）
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: -1  // 置于底层
                });
                datasets.push({
                    label: 'BOLL上轨',
                    data: boll.upper,
                    borderColor: '#e74c3c',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    borderDash: [5, 3]
                });
                datasets.push({
                    label: 'BOLL中轨',
                    data: boll.mid,
                    borderColor: '#f39c12',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0
                });
                datasets.push({
                    label: 'BOLL下轨',
                    data: boll.lower,
                    borderColor: '#27ae60',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    borderDash: [5, 3]
                });
            }

            const ctx = canvas.getContext('2d');
            klineChart = new Chart(ctx, {
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
                            syncChartsTooltip(klineChart, elements[0].index);
                        }
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
                            callbacks: {
                                title: function(items) {
                                    if (!items || items.length === 0) return '';
                                    const idx = items[0].dataIndex;
                                    const k = klines[idx];
                                    return `${k.date} (${dateToWeekday(k.date)})`;
                                },
                                label: function(context) {
                                    const idx = context.dataIndex;
                                    const k = klines[idx];
                                    const label = context.dataset.label;
                                    const val = context.parsed.y;
                                    if (val === null || val === undefined) return null;
                                    let extra = '';
                                    if (label === '收盘价') {
                                        extra = `  涨跌幅: ${k.change_pct}%`;
                                    }
                                    return `${label}: ${val.toFixed(2)}${extra}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: { display: true, text: '日期' },
                            ticks: {
                                // 显示周几
                                callback: function(value, index) {
                                    if (index % Math.ceil(labels.length / 15) !== 0 && labels.length > 15) return '';
                                    return dateToWeekday(labels[index]);
                                },
                                maxRotation: 0,
                                autoSkip: false
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

            // 鼠标离开 K 线主图时清除联动高亮
            canvas.addEventListener('mouseleave', () => {
                clearChartsTooltip();
            });
        }

