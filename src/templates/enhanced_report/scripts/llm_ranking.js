// ========= AI 模型排名（llm-stats.com）=========

let llmRankingChart = null;
// 当前类别 / 当前方向（vertical 竖柱 | horizontal 横条）/ 当前展示条数
let llmCurrentCategory = 'general';
let llmCurrentOrientation = 'vertical';
let llmCurrentLimit = 15;
const llmRankingCache = {};     // key: `${category}:${limit}`
const llmRankingPending = {};   // in-flight 去重：相同 key 并发请求复用同一 Promise
// 全部类别一次性并行预取，切换标签零延迟
const LLM_CATEGORIES = ['general', 'code', 'reasoning', 'math'];
const LLM_LIMITS = [15, 30];
const llmPrefetchedLimits = new Set();
const LLM_CHANGE_PANEL_MS = 10000;  // 排名变动提示自动消失时长

// ── 获取单类别数据（缓存 + in-flight 去重）──────────────────────
function getLlmCategoryData(category, limit) {
    limit = limit || llmCurrentLimit;
    const key = category + ':' + limit;
    if (llmRankingCache[key]) {
        return Promise.resolve(llmRankingCache[key]);
    }
    if (llmRankingPending[key]) {
        return llmRankingPending[key];
    }
    llmRankingPending[key] = fetch(`/api/llm/rankings?limit=${limit}&category=${encodeURIComponent(category)}`)
        .then(r => r.json())
        .then(json => {
            if (!json.success) throw new Error(json.error || '接口返回失败');
            llmRankingCache[key] = json.data;
            return json.data;
        })
        .finally(() => { delete llmRankingPending[key]; });
    return llmRankingPending[key];
}

// ── 等待 Chart.js 加载后拉取并渲染排名 ──────────────────────
function loadLlmRanking(category) {
    if (typeof Chart === 'undefined') {
        setTimeout(() => loadLlmRanking(category || llmCurrentCategory), 100);
        return;
    }
    category = category || llmCurrentCategory;
    llmCurrentCategory = category;
    getLlmCategoryData(category, llmCurrentLimit)
        .then(data => {
            if (category === llmCurrentCategory) {
                renderLlmRanking(category, data);
            }
        })
        .catch(err => {
            console.error('AI 模型排名加载失败:', err);
            showLlmRankingPlaceholder('⚠️ AI 模型排名加载失败: ' + err.message);
        });
}

// ── 一次性并行预取全部类别（页面加载时调用，切换标签零延迟）──────────────────────
function prefetchAllLlmCategories() {
    if (llmPrefetchedLimits.has(llmCurrentLimit)) return;
    llmPrefetchedLimits.add(llmCurrentLimit);
    LLM_CATEGORIES.forEach(cat => getLlmCategoryData(cat, llmCurrentLimit).catch(
        err => console.warn(`AI 排名类别 ${cat} 预取失败:`, err)
    ));
}

// ── Top N 条数切换 ──────────────────────
function switchLlmLimit(limit, btn) {
    limit = Number(limit);
    if (limit === llmCurrentLimit) return;
    llmCurrentLimit = limit;
    const titleEl = document.getElementById('llm-ranking-title');
    if (titleEl) titleEl.textContent = '🤖 AI 模型排名 TOP ' + limit;
    const parent = btn ? btn.parentElement : null;
    if (parent) {
        parent.querySelectorAll('.llm-orient-btn').forEach(b => b.classList.toggle('active', b === btn));
    }
    prefetchAllLlmCategories();  // 新条数的各类别并行预取
    loadLlmRanking(llmCurrentCategory);
}

// ── 类别标签切换 ──────────────────────
function switchLlmCategory(category) {
    if (category === llmCurrentCategory) return;
    document.querySelectorAll('#llm-ranking-tabs .llm-ranking-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.category === category);
    });
    loadLlmRanking(category);
}

// ── 横向/竖向视图切换 ──────────────────────
function switchLlmOrientation(orientation, btn) {
    if (orientation === llmCurrentOrientation) return;
    llmCurrentOrientation = orientation;
    const parent = btn ? btn.parentElement : null;
    if (parent) {
        parent.querySelectorAll('.llm-orient-btn').forEach(b => b.classList.toggle('active', b === btn));
    }
    loadLlmRanking(llmCurrentCategory);
}

// ── 排名变动对比（localStorage 记忆上次排名，按类别+条数区分基线）──────────────────────
function diffLlmRanks(category, models) {
    const key = 'llm_rank_prev_' + category + '_' + llmCurrentLimit;
    let prev = null;
    try {
        prev = JSON.parse(localStorage.getItem(key) || 'null');
    } catch (e) { /* ignore */ }

    const changes = [];
    if (prev && typeof prev === 'object') {
        models.forEach(m => {
            const old = prev[m.id];
            if (old == null) {
                changes.push({ name: m.name, domestic: m.is_domestic, type: 'new' });
            } else if (old > m.rank) {
                changes.push({ name: m.name, domestic: m.is_domestic, type: 'up', n: old - m.rank });
            } else if (old < m.rank) {
                changes.push({ name: m.name, domestic: m.is_domestic, type: 'down', n: m.rank - old });
            }
        });
    }
    // 保存本次排名作为下次对比基线
    const cur = {};
    models.forEach(m => { cur[m.id] = m.rank; });
    try { localStorage.setItem(key, JSON.stringify(cur)); } catch (e) { /* ignore */ }
    return changes;
}

let llmChangesTimer = null;

// ── 排名变动小窗提示 ──────────────────────
function showLlmRankChanges(changes) {
    const panel = document.getElementById('llm-ranking-changes');
    const list = document.getElementById('llm-changes-list');
    if (!panel || !list || !changes.length) return;

    const typeLabel = { up: '上升', down: '下降', new: '新上榜' };
    list.innerHTML = changes.map(c => {
        let arrow = '';
        if (c.type === 'up') arrow = `<span class="llm-chg-up">▲${c.n}</span>`;
        else if (c.type === 'down') arrow = `<span class="llm-chg-down">▼${c.n}</span>`;
        else arrow = '<span class="llm-chg-new">NEW</span>';
        const flag = c.domestic ? '🚩 ' : '';
        return `<div class="llm-chg-row">${flag}${c.name} <span class="llm-chg-type">${typeLabel[c.type]}</span> ${arrow}</div>`;
    }).join('');
    panel.style.display = 'block';

    if (llmChangesTimer) clearTimeout(llmChangesTimer);
    llmChangesTimer = setTimeout(closeLlmChanges, LLM_CHANGE_PANEL_MS);
}

function closeLlmChanges() {
    const panel = document.getElementById('llm-ranking-changes');
    if (panel) panel.style.display = 'none';
    if (llmChangesTimer) { clearTimeout(llmChangesTimer); llmChangesTimer = null; }
}

// ── 柱顶/条尾分数 + 柱内排名徽标插件（无第三方依赖，方向自适应）──────────────────────
const llmScoreLabelPlugin = {
    id: 'llmScoreLabel',
    afterDatasetsDraw(chart) {
        const { ctx } = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;
        const horizontal = chart.options.indexAxis === 'y';
        const ranks = (chart.options.plugins.llmScoreLabel || {}).ranks || [];

        // 分数标签（柱顶/条尾）
        ctx.save();
        ctx.font = '600 11px sans-serif';
        ctx.fillStyle = chart.options.plugins.llmScoreLabel.color || '#94a3b8';
        ctx.textBaseline = horizontal ? 'middle' : 'bottom';
        ctx.textAlign = horizontal ? 'left' : 'center';
        meta.data.forEach((bar, i) => {
            const v = chart.data.datasets[0].data[i];
            if (v == null) return;
            if (horizontal) {
                ctx.fillText(String(v), bar.x + 5, bar.y);
            } else {
                ctx.fillText(String(v), bar.x, bar.y - 3);
            }
        });
        ctx.restore();

        // 排名徽标（柱/条内部靠值端，白色加粗，醒目）
        ctx.save();
        ctx.font = '800 12px sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        meta.data.forEach((bar, i) => {
            const r = ranks[i];
            if (r == null) return;
            if (horizontal) {
                if (bar.x - bar.base > 34) ctx.fillText('#' + r, bar.base + 18, bar.y);
            } else {
                if (bar.base - bar.y > 24) ctx.fillText('#' + r, bar.x, bar.y + 13);
            }
        });
        ctx.restore();
    }
};

// ── 渲染（竖柱：模型横向左→右 / 横条：模型纵向自上而下）──────────────────────
function renderLlmRanking(category, data) {
    const models = (data && data.models) || [];

    // 更新数据时间
    const timeEl = document.getElementById('llm-ranking-time');
    if (timeEl) {
        timeEl.textContent = data.ranked_at
            ? new Date(data.ranked_at).toLocaleString('zh-CN', { hour12: false })
            : (data.unavailable_reason ? '不可用（' + data.unavailable_reason + '）' : '--');
    }

    if (!models.length) {
        const reason = (data && data.unavailable_reason) || '暂无数据';
        showLlmRankingPlaceholder('ℹ️ AI 模型排名暂不可用：' + reason);
        return;
    }

    const canvas = document.getElementById('llm-ranking-canvas');
    if (!canvas) return;
    hideLlmRankingPlaceholder();

    // 排名变动对比与提示（仅在本次与上次有差异时弹出）
    const changes = diffLlmRanks(category, models);
    if (changes.length) showLlmRankChanges(changes);

    // X/Y 轴均按 rank 升序：竖柱 #1 最左，横条 #1 最上（Chart.js 首元素渲染在起始侧）
    const sorted = models.slice().sort((a, b) => (a.rank || 0) - (b.rank || 0));
    const isDark = document.body.classList.contains('dark-mode');
    const horizontal = llmCurrentOrientation === 'horizontal';

    // Windows 无国旗 emoji（🇨🇳 显示为"cn"），🚩 为普通 emoji 可正常渲染
    // 排名已由柱内白色徽标展示，轴标签不再重复 #N 前缀
    const labels = sorted.map(m => (m.is_domestic ? '🚩' : '') + m.name);
    const scores = sorted.map(m => m.score);

    // 🚩 国产红色系，其他蓝色系
    const colors = sorted.map(m =>
        m.is_domestic ? 'rgba(229, 57, 53, 0.85)' : 'rgba(74, 144, 217, 0.85)'
    );
    const borderColors = sorted.map(m =>
        m.is_domestic ? 'rgba(183, 28, 28, 1)' : 'rgba(43, 108, 176, 1)'
    );

    // 容器高度：竖柱固定紧凑高度；横条按条数动态撑高
    const wrap = document.getElementById('llm-ranking-chart-wrap');
    if (wrap) {
        wrap.style.height = horizontal ? (sorted.length * 26 + 80) + 'px' : '360px';
    }

    if (llmRankingChart) llmRankingChart.destroy();

    llmRankingChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: scores,
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 3,
                maxBarThickness: horizontal ? 20 : 46,
                categoryPercentage: 0.92,
            }]
        },
        options: {
            indexAxis: horizontal ? 'y' : 'x',
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: horizontal ? { right: 34 } : { top: 14 } },
            plugins: {
                legend: { display: false },
                llmScoreLabel: { color: isDark ? '#cbd5e1' : '#475569', ranks: sorted.map(m => m.rank) },
                tooltip: {
                    callbacks: {
                        afterLabel: ctx => {
                            const m = sorted[ctx.dataIndex];
                            if (!m) return '';
                            const parts = [`组织: ${m.org_name || m.org_id || '--'}`];
                            if (m.open_weight) parts.push('开放权重: 是');
                            if (m.is_domestic) parts.push('🚩 国产大模型');
                            return parts;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: horizontal
                        ? { color: isDark ? '#94a3b8' : '#64748b', font: { size: 11 } }
                        : {
                            color: isDark ? '#cbd5e1' : '#334155',
                            font: { size: 11 },
                            maxRotation: 42, minRotation: 42, autoSkip: false,
                        },
                    grid: horizontal
                        ? { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }
                        : { display: false },
                },
                y: {
                    ticks: horizontal
                        ? { color: isDark ? '#cbd5e1' : '#334155', font: { size: 12 }, autoSkip: false }
                        : { color: isDark ? '#94a3b8' : '#64748b', font: { size: 11 } },
                    grid: horizontal
                        ? { display: false }
                        : { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' },
                },
            }
        },
        plugins: [llmScoreLabelPlugin]
    });
}

// ── 占位提示 ──────────────────────
function showLlmRankingPlaceholder(text) {
    const ph = document.getElementById('llm-ranking-placeholder');
    const canvas = document.getElementById('llm-ranking-canvas');
    if (!ph) return;
    if (canvas) canvas.style.display = 'none';
    ph.textContent = text;
    ph.style.display = 'flex';
}

function hideLlmRankingPlaceholder() {
    const ph = document.getElementById('llm-ranking-placeholder');
    const canvas = document.getElementById('llm-ranking-canvas');
    if (ph) ph.style.display = 'none';
    if (canvas) canvas.style.display = '';
}

// ── 页面加载即拉取（标题区在首屏；并行预取全部类别）──────────────────────
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        prefetchAllLlmCategories();
        loadLlmRanking(llmCurrentCategory);
    });
} else {
    prefetchAllLlmCategories();
    loadLlmRanking(llmCurrentCategory);
}
