// ========= AI 模型排名（数据源可切换：llm-stats.com | Artificial Analysis）=========

let llmRankingChart = null;
// 当前数据源（llm | aa）/ 当前类别 / 当前方向 / 当前展示条数
let llmSource = 'aa';
let llmCurrentCategory = 'general';
let llmCurrentOrientation = 'vertical';
let llmCurrentLimit = 15;
const llmRankingCache = {};     // key: `${source}:${category}:${limit}`
const llmRankingPending = {};   // in-flight 去重：相同 key 并发请求复用同一 Promise
const LLM_LIMITS = [15, 30];
const llmPrefetchedLimits = new Set();
const LLM_CHANGE_PANEL_MS = 10000;  // 排名变动提示自动消失时长

// 数据源配置：端点、类别（[key, 标签]）
const RANKING_SOURCES = {
    llm: {
        endpoint: '/api/llm/rankings',
        categories: [
            ['general', '综合'], ['code', '代码'],
            ['reasoning', '推理'], ['math', '数学'],
        ],
    },
    aa: {
        endpoint: '/api/aa/rankings',
        categories: [
            ['general', '综合'], ['code', '代码'], ['agentic', '智能体'],
        ],
    },
};

// ── 获取单类别数据（缓存 + in-flight 去重，key 带数据源前缀）──────────────────────
// 数据源降级：AA 因配额/限流无数据时，自动回退显示 llm-stats 数据，避免图表空白。
function getRankingSourceData(source, category, limit) {
    limit = limit || llmCurrentLimit;
    const src = RANKING_SOURCES[source] || RANKING_SOURCES.llm;
    const key = source + ':' + category + ':' + limit;
    if (llmRankingCache[key]) {
        return Promise.resolve(llmRankingCache[key]);
    }
    if (llmRankingPending[key]) {
        return llmRankingPending[key];
    }
    llmRankingPending[key] = fetch(src.endpoint + `?limit=${limit}&category=${encodeURIComponent(category)}`)
        .then(r => r.json())
        .then(async json => {
            if (!json.success) throw new Error(json.error || '接口返回失败');
            let data = json.data;
            // AA 无数据（配额耗尽/限流/success 但空）→ 自动回退 llm-stats，并打降级标记
            if (source === 'aa' && (!data.models || data.models.length === 0)) {
                const llmSrc = RANKING_SOURCES.llm;
                const fallback = await fetch(llmSrc.endpoint + `?limit=${limit}&category=${encodeURIComponent(category)}`)
                    .then(r => r.json())
                    .catch(() => ({ success: false }));
                if (fallback.success && fallback.data && fallback.data.models && fallback.data.models.length) {
                    const fb = fallback.data;
                    fb.fallback_from = 'aa';
                    fb.fallback_reason = data.unavailable_reason || (data.rate_limited ? 'AA 限流' : 'AA 无数据');
                    data = fb;
                    // 回退成功后，把数据源 tab 也定位到 llm-stats，
                    // 避免「显示 llm 数据但 tab 却停留在 AA」的不一致
                    applyLlmFallbackSource(category);
                }
            }
            llmRankingCache[key] = data;
            return data;
        })
        .finally(() => { delete llmRankingPending[key]; });
    return llmRankingPending[key];
}

// ── 轴标签截断：AA 模型名极长，取主名并限长；llm 原样 ──────────────────────
function shortModelName(model) {
    if (llmSource !== 'aa') return model.name;
    const main = (model.name || '').split(' (')[0] || model.name;
    return main.length > 24 ? main.slice(0, 24) + '…' : main;
}

// ── 重建类别 tab（两数据源类别数不同，随源动态生成）──────────────────────
function rebuildCategoryTabs() {
    const container = document.getElementById('llm-ranking-tabs');
    if (!container) return;
    const src = RANKING_SOURCES[llmSource];
    container.innerHTML = src.categories.map(([cat, label]) =>
        `<button class="llm-ranking-tab${cat === llmCurrentCategory ? ' active' : ''}" ` +
        `data-category="${cat}" onclick="switchLlmCategory('${cat}')">${label}</button>`
    ).join('');
}

// ── 等待 Chart.js 加载后拉取并渲染排名 ──────────────────────
function loadLlmRanking(category) {
    if (typeof Chart === 'undefined') {
        setTimeout(() => loadLlmRanking(category || llmCurrentCategory), 100);
        return;
    }
    category = category || llmCurrentCategory;
    llmCurrentCategory = category;
    getRankingSourceData(llmSource, category, llmCurrentLimit)
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

// ── 懒加载 + 空闲预取（关键：AA 免费配额仅 100 次/24h，一次全量 = 4 页调用）─────────
// 旧实现首屏并行预取全部类别（3 类 × 4 页 = 12 次/页面加载），一天就能烧穿配额。
// 现改为：首屏只拉当前类别（4 次），其余类别在 requestIdleCallback 空闲时逐个预取，
// 且预取带节流间隔，避免瞬间并发打满配额。
const LLM_IDLE_PREFETCH_DELAY = 3000;   // 首屏渲染完成后再等 3s 才启动空闲预取
const LLM_IDLE_PREFETCH_GAP = 1500;     // 相邻类别预取之间的间隔

/**
 * 空闲预取剩余类别（不阻塞首屏）
 * 已加载/在途的类别会自动跳过（getRankingSourceData 内部去重）。
 */
function scheduleIdlePrefetch() {
    const preKey = llmSource + ':' + llmCurrentLimit;
    if (llmPrefetchedLimits.has(preKey)) return;
    llmPrefetchedLimits.add(preKey);

    const src = RANKING_SOURCES[llmSource];
    const current = llmCurrentCategory;
    // 排除当前类别（首屏已在拉）与已缓存类别
    const pending = src.categories
        .map(([cat]) => cat)
        .filter(cat => cat !== current && !llmRankingCache[llmSource + ':' + cat + ':' + llmCurrentLimit]);

    if (!pending.length) return;

    const runNext = (idx) => {
        if (idx >= pending.length) return;
        // 若期间用户切了源/条数，放弃本轮预取（新的一轮会重新调度）
        if (llmSource !== src.__owner) return;
        const cat = pending[idx];
        getRankingSourceData(llmSource, cat, llmCurrentLimit)
            .catch(err => console.warn(`排名类别 ${cat} 空闲预取失败:`, err))
            .finally(() => {
                // 逐个串行 + 间隔，避免并发冲击配额
                setTimeout(() => runNext(idx + 1), LLM_IDLE_PREFETCH_GAP);
            });
    };

    src.__owner = llmSource;   // 记录发起时的源，用于失效判断
    const kick = () => setTimeout(() => runNext(0), LLM_IDLE_PREFETCH_DELAY);
    if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(kick, { timeout: 5000 });
    } else {
        setTimeout(kick, LLM_IDLE_PREFETCH_DELAY);
    }
}

// 兼容旧调用点：保留函数名，内部改为「空闲预取」语义（首屏不再并行拉全部类别）
function prefetchAllLlmCategories() {
    scheduleIdlePrefetch();
}

// ── 数据源切换 ──────────────────────
function switchLlmSource(source) {
    if (!RANKING_SOURCES[source] || source === llmSource) return;
    llmSource = source;
    // 切换后类别重置为当前源的默认类（general 综合）
    llmCurrentCategory = 'general';
    document.querySelectorAll('#llm-ranking-source .llm-ranking-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.source === source);
    });
    rebuildCategoryTabs();
    prefetchAllLlmCategories();
    loadLlmRanking(llmCurrentCategory);
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

// ── 排名变动对比（localStorage 记忆上次排名，按源+类别+条数区分基线）──────────────────────
function diffLlmRanks(category, models) {
    const key = 'llm_rank_prev_' + llmSource + '_' + category + '_' + llmCurrentLimit;
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

// ── 按厂商品牌配色（国产优先红色；知名海外厂商用各自品牌色）──────────────────────
// 色板：以匹配到的厂商 → [填充, 边框]
const VENDOR_PALETTES = [
    { match: ['openai', 'gpt', 'chatgpt'], fill: 'rgba(16, 185, 129, 0.85)',  border: 'rgba(6, 95, 70, 1)' },   // OpenAI 绿
    { match: ['anthropic', 'claude'],     fill: 'rgba(217, 119, 6, 0.85)',  border: 'rgba(120, 53, 15, 1)' },  // Anthropic 橙
    { match: ['google', 'gemini'],        fill: 'rgba(59, 130, 246, 0.85)', border: 'rgba(30, 64, 175, 1)' },  // Google 蓝
    { match: ['meta', 'llama'],           fill: 'rgba(14, 165, 233, 0.85)', border: 'rgba(3, 105, 161, 1)' },  // Meta 天空蓝
    { match: ['microsoft', 'phi'],        fill: 'rgba(99, 102, 241, 0.85)', border: 'rgba(67, 56, 202, 1)' },  // Microsoft 靛
    { match: ['xai', 'grok'],             fill: 'rgba(236, 72, 153, 0.85)', border: 'rgba(157, 23, 77, 1)' },  // xAI 粉
    { match: ['mistral'],                 fill: 'rgba(245, 158, 11, 0.9)',  border: 'rgba(146, 64, 14, 1)' },  // Mistral 琥珀
    { match: ['amazon', 'cosmos'],        fill: 'rgba(52, 211, 153, 0.85)', border: 'rgba(6, 95, 70, 1)' },    // Amazon 翠绿
    { match: ['ibm', 'nvidia', 'nemotron', 'nemo'], fill: 'rgba(148, 163, 184, 0.85)', border: 'rgba(71, 85, 105, 1)' }, // 灰蓝
];
const defaultFill = 'rgba(74, 144, 217, 0.85)';
const defaultBorder = 'rgba(43, 108, 176, 1)';
const domesticFill = 'rgba(229, 57, 53, 0.85)';
const domesticBorder = 'rgba(183, 28, 28, 1)';

function colorForModel(m) {
    if (m.is_domestic) return { fill: domesticFill, border: domesticBorder };  // 国产优先红
    const text = ((m.org_name || '') + ' ' + (m.name || '')).toLowerCase();
    for (const p of VENDOR_PALETTES) {
        if (p.match.some(kw => text.includes(kw))) return { fill: p.fill, border: p.border };
    }
    return { fill: defaultFill, border: defaultBorder };
}

// ── 分组分割线插件：横向视图每 5 名画一条细分隔线，提升梯队可读性 ──────────────────────
const llmGroupDivider = {
    id: 'llmGroupDivider',
    afterDatasetsDraw(chart) {
        const horizontal = chart.options.indexAxis === 'y';
        if (!horizontal) return;
        const xScale = chart.scales.x;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;
        const { ctx } = chart;
        const idx = chart.options.plugins.llmGroupDivider || {};
        if (!idx.thicknesses) return;
        // 每 5 名之后画一条分隔线（即第 5、10、15... 名与下一名之间）。
        // 必须判断 i + 1 < length：总条数为 5 的倍数时，最后一个分组后已无下一条，
        // 再画会在图表底部留下一条多余的分隔线。
        const total = idx.thicknesses.length;
        for (let i = 4; i < total; i += 5) {
            if (i + 1 >= total) break;   // 末组之后无下一根条，跳过
            const bar = meta.data[i];
            if (!bar) continue;
            ctx.save();
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.22)';
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(xScale.left, bar.y + idx.height / 2 + 3);
            ctx.lineTo(xScale.right, bar.y + idx.height / 2 + 3);
            ctx.stroke();
            ctx.restore();
        }
    }
};

// ── 渲染（竖柱：模型横向左→右 / 横条：模型纵向自上而下）──────────────────────
function renderLlmRanking(category, data) {
    const models = (data && data.models) || [];

    // 数据时间：AA 无时间戳，退化为「本次拉取时间」；限流降级时标注 stale
    const timeEl = document.getElementById('llm-ranking-time');
    if (timeEl) {
        let label = '--';
        if (data.fetched_at) {
            label = new Date(data.fetched_at).toLocaleString('zh-CN', { hour12: false });
        } else if (data.ranked_at) {
            label = new Date(data.ranked_at).toLocaleString('zh-CN', { hour12: false });
        } else if (data.unavailable_reason) {
            label = '不可用（' + data.unavailable_reason + '）';
        }
        timeEl.textContent = label;
        timeEl.title = data.stale
            ? `数据为最近一次成功拉取结果（${data.stale_reason || 'API 限流'}）`
            : '';
    }

    // 限流降级提示（非阻塞，不遮挡图表）
    showLlmStaleNotice(data);

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
    const labels = sorted.map(m => (m.is_domestic ? '🚩' : '') + shortModelName(m));
    const scores = sorted.map(m => m.score);

    // 按厂商品牌配色（国产优先红色）
    const paletteMap = sorted.map(m => colorForModel(m));
    const colors = paletteMap.map(p => p.fill);
    const borderColors = paletteMap.map(p => p.border);
    // Top 3 加粗描边高亮，凸显领先梯队（borderWidth 为 scriptable，可按点设数组）
    const borderWidths = sorted.map(m => (m.rank <= 3 ? 2 : 1));

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
                borderWidth: borderWidths,
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
                llmGroupDivider: { height: horizontal ? 20 : 0, thicknesses: scores },
                tooltip: {
                    callbacks: {
                        afterLabel: ctx => {
                            const m = sorted[ctx.dataIndex];
                            if (!m) return '';
                            const parts = [`组织: ${m.org_name || m.org_id || '--'}`];
                            // AA 模型名被轴标签截断，此处补全原名
                            if (llmSource === 'aa' && m.name && m.name !== shortModelName(m)) {
                                parts.push(`模型: ${m.name}`);
                            }
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
        plugins: [llmScoreLabelPlugin, llmGroupDivider]
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

// ── 限流降级提示条：显示缓存结果时给出轻量说明，不遮挡图表 ──────────────────
function showLlmStaleNotice(data) {
    // 惰性创建容器，挂在标题行下方
    let el = document.getElementById('llm-ranking-stale-notice');
    const anchor = document.getElementById('llm-ranking-chart-wrap');
    if (!el && anchor && anchor.parentElement) {
        el = document.createElement('div');
        el.id = 'llm-ranking-stale-notice';
        el.className = 'llm-stale-notice';
        anchor.parentElement.insertBefore(el, anchor);
    }
    if (!el) return;

    if (!data || (!data.stale && !data.fallback_from)) {
        el.style.display = 'none';
        el.textContent = '';
        return;
    }

    // 优先体现「回退到 llm-stats」
    if (data.fallback_from) {
        el.textContent = `⚠️ ${data.fallback_reason || 'AA 数据源不可用'}，当前显示 llm-stats 排名`;
        el.style.display = 'block';
        return;
    }

    const when = data.fetched_at
        ? new Date(data.fetched_at).toLocaleString('zh-CN', { hour12: false })
        : '最近一次成功拉取';
    // 冷却时长可能是数小时（配额耗尽时 AA 的 Retry-After 实测可达 7 小时），
    // 因此按量级选择「分钟 / 小时」展示，避免出现「约 422 分钟后重试」这种难读文案。
    const secs = data.cooldown_left || 0;
    let waitText = '';
    if (secs >= 3600) {
        const h = Math.floor(secs / 3600);
        const m = Math.round((secs % 3600) / 60);
        waitText = `，约 ${h} 小时${m ? ' ' + m + ' 分钟' : ''}后恢复`;
    } else if (secs > 0) {
        waitText = `，约 ${Math.ceil(secs / 60)} 分钟后恢复`;
    }
    el.textContent = `⚠️ 数据源限流，显示 ${when} 的缓存结果${waitText}`;
    el.style.display = 'block';
}

// ── 应用当前数据源的 UI 状态（源按钮 active）──────────────────────
function applyLlmSourceUI() {
    document.querySelectorAll('#llm-ranking-source .llm-ranking-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.source === llmSource);
    });
}

// ── AA 限流回退到 llm-stats 后，同步把数据源 tab 定位到 llm-stats ──────────────
// 否则会出现「显示 llm-stats 排名但 tab 却停留在 AA」的不一致。
function applyLlmFallbackSource(currentCategory) {
    if (llmSource !== 'aa') return;   // 幂等：首个回退成功后 llmSource 已翻转，其余并发回退直接忽略
    llmSource = 'llm';
    applyLlmSourceUI();
    const validInLlm = RANKING_SOURCES.llm.categories.some(([c]) => c === currentCategory);
    if (validInLlm) {
        // 当前类别 llm 也支持（general/code）：仅重建类别 tab 高亮，渲染交由调用方继续
        rebuildCategoryTabs();
    } else {
        // llm 独有类别之外的 aa 独有类别（agentic）在 llm 无对应，重置到 general 并重拉
        llmCurrentCategory = 'general';
        rebuildCategoryTabs();
        loadLlmRanking('general');
    }
}

// ── 页面加载即拉取（首屏只拉当前类别，其余类别空闲时懒预取）──────────────────────
function initLlmRanking() {
    applyLlmSourceUI();
    rebuildCategoryTabs();
    // 首屏只拉 general（4 次调用）；其余类别由 scheduleIdlePrefetch 空闲时逐个补齐
    loadLlmRanking(llmCurrentCategory);
    scheduleIdlePrefetch();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLlmRanking);
} else {
    initLlmRanking();
}