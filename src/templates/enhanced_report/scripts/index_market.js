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
                    fetch('/api/index/industry?limit=10000')
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
                document.getElementById('industry-indices-body').innerHTML = '<tr><td colspan="14" class="index-loading">加载失败</td></tr>';
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
                tbody.innerHTML = '<tr><td colspan="14" class="index-loading">暂无数据</td></tr>';
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

            // 排序（三级优先级：关注状态 > 金叉标识置顶 > 正常排序）
            // 仅 MACD金叉 / MA金叉 视为金叉置顶；其他标识（趋势/即将金叉）按正常排序
            const isGolden = (co) => {
                if (!co) return false;
                return co.macd === 'golden' || co.ma === 'golden';
            };
            const sorted = [...filtered].sort((a, b) => {
                // 1) 关注状态优先（始终最优先）
                const aFollowed = followedSet.has(a.code) ? 1 : 0;
                const bFollowed = followedSet.has(b.code) ? 1 : 0;
                if (aFollowed !== bFollowed) {
                    return bFollowed - aFollowed;  // 关注的在前
                }
                // 2) 金叉标识置顶（仅 MACD金叉 / MA金叉），其他标识按正常排序
                const aGolden = isGolden(a.crossover) ? 1 : 0;
                const bGolden = isGolden(b.crossover) ? 1 : 0;
                if (aGolden !== bGolden) {
                    return bGolden - aGolden;
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
                tbody.innerHTML = '<tr><td colspan="15" class="index-loading">未找到匹配的数据</td></tr>';
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
                            <td>${drawdownHtml}</td>
                            <td class="rotation-col">${momentumHtml}</td>
                            <td class="rotation-col">${fmtRank(rankToday)}</td>
                            <td class="rotation-col">${fmtRank(rank3d)}</td>
                            <td class="rotation-col">${fmtRank(rank7d)}</td>
                            <td class="rotation-col">${rankChangeHtml}</td>
                            <td class="rotation-col">${formatCrossoverText(idx.crossover)}</td>
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
            const displayDays = parseInt(document.getElementById('kline-days').value, 10) || 30;
            // 多取 60 天历史用于 MA60 / BOLL(20) 等指标计算，
            // 确保显示窗口内每个交易日的均线都有完整数据支撑（避免起始段 MA 缺失）。
            const fetchDays = Math.min(displayDays + 60, 365);
            try {
                const res = await fetch(`/api/index/kline?code=${currentKlineCode}&days=${fetchDays}`);
                const data = await res.json();
                if (data.success) {
                    const allKlines = data.data.kline || [];
                    const allCrossoverPoints = data.data.crossover_points || [];
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
                        pt.type === 'macd' ? 'rgba(231, 76, 60, 0.95)' :
                        pt.type === 'ma' ? 'rgba(52, 152, 219, 0.95)' : 'transparent'
                    );
                    crossoverPointBorderColors.push(
                        pt.type === 'macd' ? '#c0392b' :
                        pt.type === 'ma' ? '#2471a3' : 'transparent'
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
                    // 国内习惯：红涨绿跌
                    color: {
                        up: '#e74c3c',       // 收阳（上涨）实体颜色
                        down: '#27ae60',     // 收阴（下跌）实体颜色
                        unchanged: '#95a5a6' // 平盘
                    },
                    borderColor: {
                        up: '#e74c3c',
                        down: '#27ae60',
                        unchanged: '#95a5a6'
                    },
                    borderWidth: 1,
                    yAxisID: 'y',
                    order: 1  // 蜡烛主体绘制顺序（数值越大越靠下层）
                },
                {
                    type: 'line',
                    label: 'MA5',
                    data: toXY(ma5),
                    borderColor: '#9b59b6',
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
                    borderColor: '#e67e22',
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
                    borderColor: '#1abc9c',
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
                    borderColor: '#34495e',
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
                    label: 'BOLL通道',
                    data: upperDataForFill.map((v, i) => (v !== null && lowerDataForFill[i] !== null) ? { x: tsArr[i], y: v } : null).filter(p => p !== null),
                    backgroundColor: 'rgba(155, 89, 182, 0.08)',
                    fill: '-3',  // 填充到 BOLL下轨（当前 dataset index + 3）
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    order: -1,  // 置于底层
                    parsing: false
                });
                datasets.push({
                    label: 'BOLL上轨',
                    data: toXY(boll.upper),
                    borderColor: '#e74c3c',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    borderDash: [5, 3],
                    parsing: false
                });
                datasets.push({
                    label: 'BOLL中轨',
                    data: toXY(boll.mid),
                    borderColor: '#f39c12',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y',
                    pointRadius: 0,
                    parsing: false
                });
                datasets.push({
                    label: 'BOLL下轨',
                    data: toXY(boll.lower),
                    borderColor: '#27ae60',
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
                                    // MA 等线型
                                    const val = context.parsed.y;
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

            // 鼠标离开 K 线主图时清除联动高亮
            canvas.addEventListener('mouseleave', () => {
                clearChartsTooltip();
            });
        }

