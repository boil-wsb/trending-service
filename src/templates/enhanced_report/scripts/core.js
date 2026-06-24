        // 报告数据
        window.REPORT_DATA = {};

        // UI 配置
        window.UI_CONFIG = { default_theme: 'light' };

        // 当前状态
        let currentView = 'overview';
        let currentSource = 'all';
        let currentCategory = 'all';

        // API 配置
        const API_BASE_URL = 'http://localhost:8888';

        // 数据源配置
        const sourceConfig = {
            'github': { icon: '🐙', name: 'GitHub', category: 'tech' },
            'github_ai': { icon: '🤖', name: 'GitHub AI', category: 'tech' },
            'hackernews': { icon: '📰', name: 'HackerNews', category: 'tech' },
            'bilibili': { icon: '📺', name: 'Bilibili', category: 'video' },
            'arxiv': { icon: '📚', name: 'ArXiv', category: 'academic' },
            'zhihu': { icon: '❓', name: '知乎', category: 'social' },
            'weibo': { icon: '📱', name: '微博', category: 'social' },
            'douyin': { icon: '🎵', name: '抖音', category: 'social' },
            'aihot': { icon: '🔥', name: 'AIHOT', category: 'tech' }
        };

        // 切换分析视图
        function switchView(viewName) {
            currentView = viewName;

            // 保存当前 tab 到 localStorage，报告刷新后恢复
            try { localStorage.setItem('trending_current_view', viewName); } catch(e) {}

            // 更新导航Tab样式
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.classList.remove('active');
                if (tab.dataset.view === viewName) {
                    tab.classList.add('active');
                }
            });

            // 更新内容区域显示
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            // 如果是数据源详情视图
            if (viewName === 'source-detail') {
                document.getElementById('source-detail').classList.add('active');
                renderSourceDetail();
            } else {
                document.getElementById(viewName).classList.add('active');
            }

            // 如果切换到关键词 tab，渲染词云
            if (viewName === 'keywords' && savedKeywordsData && Object.keys(savedKeywordsData).length > 0) {
                // 延迟渲染，确保 tab 完全显示
                setTimeout(() => {
                    renderWordCloud(savedKeywordsData);
                }, 100);
            }

            // 如果切换到综合分析 tab，渲染图表
            if (viewName === 'analysis') {
                setTimeout(() => {
                    renderAnalysis(window.REPORT_DATA);
                    // 渲染 Chart.js 图表
                    renderAllCharts();
                }, 100);
            }

            // 新增：风格+北向 / 主力资金 tab 懒加载
            if (typeof onTabShown === 'function') {
                try { onTabShown(viewName); } catch(e) { console.error('onTabShown error:', e); }
            }

            // 如果切换到指数 tab，加载数据
            if (viewName === 'index') {
                loadIndexData();
            }

            // 根据视图更新数据源筛选器可见性
            updateSourceFilterVisibility();
        }

        // 切换数据源
        function switchSource(sourceName) {
            currentSource = sourceName;
            
            // 更新标签样式
            document.querySelectorAll('.source-tag').forEach(tag => {
                tag.classList.remove('active');
                if (tag.dataset.source === sourceName) {
                    tag.classList.add('active');
                }
            });
            
            // 更新分类下拉框
            const categorySelect = document.getElementById('source-category');
            if (sourceName === 'all') {
                categorySelect.value = 'all';
            } else {
                const config = sourceConfig[sourceName];
                if (config) {
                    categorySelect.value = config.category;
                }
            }
            
            // 如果当前在数据源详情视图，刷新内容
            if (currentView === 'source-detail') {
                renderSourceDetail();
            } else if (currentView === 'overview') {
                // 在总览视图下，筛选显示的数据源
                renderOverview(window.REPORT_DATA);
            } else if (currentView === 'keywords') {
                renderKeywords(window.REPORT_DATA);
            } else if (currentView === 'analysis') {
                renderAnalysis(window.REPORT_DATA);
            }
        }

        // 根据分类筛选数据源
        function filterByCategory(category) {
            currentCategory = category;

            // 更新标签高亮状态
            document.querySelectorAll('.source-tag').forEach(tag => {
                const sourceName = tag.dataset.source;
                if (sourceName === 'all') {
                    tag.style.display = category === 'all' ? 'inline-block' : 'none';
                } else {
                    const config = sourceConfig[sourceName];
                    if (category === 'all' || (config && config.category === category)) {
                        tag.style.display = 'inline-block';
                    } else {
                        tag.style.display = 'none';
                    }
                }
            });

            // 如果当前选中的数据源被隐藏，切换到"全部"
            if (category !== 'all' && currentSource !== 'all') {
                const currentConfig = sourceConfig[currentSource];
                if (!currentConfig || currentConfig.category !== category) {
                    currentSource = 'all';
                }
            }

            // 重新渲染当前视图
            if (window.REPORT_DATA && window.REPORT_DATA.sources) {
                const filteredData = getFilteredDataByCategory(window.REPORT_DATA);

                if (currentView === 'overview') {
                    renderOverview(filteredData);
                } else if (currentView === 'keywords') {
                    renderKeywords(filteredData);
                } else if (currentView === 'analysis') {
                    renderAnalysis(filteredData);
                } else if (currentView === 'github-weekly') {
                    renderGitHubWeekly(filteredData);
                } else if (currentView === 'source-detail') {
                    renderSourceDetail();
                }
            }
        }

        // 根据分类获取筛选后的数据
        function getFilteredDataByCategory(data) {
            if (currentCategory === 'all') {
                return data;
            }

            const filteredSources = {};
            const sources = data.sources || {};

            Object.entries(sources).forEach(([sourceName, items]) => {
                const config = sourceConfig[sourceName];
                if (config && config.category === currentCategory) {
                    filteredSources[sourceName] = items;
                }
            });

            // 重新计算关键词（基于筛选后的数据）
            const filteredKeywords = {};
            Object.values(filteredSources).forEach(items => {
                items.forEach(item => {
                    if (item.keywords) {
                        item.keywords.forEach(keyword => {
                            filteredKeywords[keyword] = (filteredKeywords[keyword] || 0) + 1;
                        });
                    }
                });
            });

            return {
                ...data,
                sources: filteredSources,
                keywords: filteredKeywords
            };
        }

        // 更新数据源筛选器可见性
        function updateSourceFilterVisibility() {
            const navSecondary = document.querySelector('.nav-secondary');
            // 综合分析视图内部有自己的筛选器，指数视图不需要数据源筛选
            if (currentView === 'analysis' || currentView === 'index') {
                navSecondary.style.display = 'none';
            } else {
                navSecondary.style.display = 'flex';
            }
        }

        // 渲染数据源详情
        function renderSourceDetail() {
            const container = document.getElementById('source-detail-content');
            const titleEl = document.getElementById('source-detail-title');
            const sources = window.REPORT_DATA.sources || {};
            
            if (currentSource === 'all') {
                // 显示所有数据源的详细列表
                titleEl.textContent = '📡 全部数据源详情';
                let html = '';
                for (const [sourceName, items] of Object.entries(sources)) {
                    const config = sourceConfig[sourceName] || { icon: '📄', name: sourceName };
                    html += renderSourceSection(config.icon, config.name, items, sourceName);
                }
                container.innerHTML = html || '<div class="empty-state"><div class="emoji">📭</div><div>暂无数据</div></div>';
            } else {
                // 显示单个数据源
                const config = sourceConfig[currentSource] || { icon: '📄', name: currentSource };
                const items = sources[currentSource] || [];
                titleEl.textContent = `${config.icon} ${config.name}`;
                container.innerHTML = renderSourceCards(items, currentSource);
            }
        }

        // 渲染数据源区块
        function renderSourceSection(icon, name, items, sourceName) {
            if (!items || items.length === 0) return '';
            return `
                <div class="source-section" style="margin-bottom: 30px;">
                    <h3 style="font-size: 1.3em; color: #24292e; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #e1e4e8;">
                        ${icon} ${name}
                    </h3>
                    ${renderSourceCards(items, sourceName)}
                </div>
            `;
        }

        // 渲染数据源卡片网格
        function renderSourceCards(items, sourceName) {
            if (!items || items.length === 0) {
                const config = sourceConfig[sourceName] || { name: sourceName };
                return `
                    <div class="empty-state">
                        <div class="emoji">📭</div>
                        <div>暂无数据</div>
                        <button class="refresh-btn" data-source="${sourceName}" onclick="refreshSource('${sourceName}')" style="margin-top: 15px; padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; gap: 6px;">
                            <span>🔄</span>
                            <span>获取${config.name}数据</span>
                        </button>
                    </div>
                `;
            }
            return `
                <div class="items-card-grid">
                    ${items.map((item, index) => `
                        <div class="item-card">
                            <div class="item-card-header">
                                <div class="item-card-rank">${index + 1}</div>
                                <div class="item-card-score">${item.hot_score ? '🔥 ' + formatNumber(item.hot_score) : ''}</div>
                            </div>
                            <div class="item-card-body">
                                <a href="${item.url}" target="_blank" class="item-card-title">${item.title}</a>
                                <div class="item-card-meta">
                                    ${item.author ? `<span class="meta-tag">👤 ${item.author}</span>` : ''}
                                    ${item.category ? `<span class="meta-tag">🏷️ ${item.category}</span>` : ''}
                                </div>
                                ${renderDescription(item.description, sourceName, index)}
                                ${item.keywords && item.keywords.length > 0 ? `<div class="item-card-keywords">${item.keywords.map(k => `<span class="item-keyword">${k}</span>`).join('')}</div>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        // 切换暗色模式
        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            const btn = document.querySelector('.dark-mode-toggle');
            btn.textContent = document.body.classList.contains('dark-mode') ? '☀️' : '🌙';
        }

        // 默认启用深色模式
        if (window.UI_CONFIG && window.UI_CONFIG.default_theme === 'dark') {
            document.body.classList.add('dark-mode');
            document.querySelector('.dark-mode-toggle').textContent = '☀️';
        }

        // 数据框跳动效果 - 仅 hover 进入时跳动一次
        function initBounceEffects() {
            const bounceSelectors = ['.topic-card', '.source-card', '.item-card'];

            bounceSelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(card => {
                    card.addEventListener('mouseenter', function() {
                        this.classList.add('bouncing');
                    });
                    card.addEventListener('mouseleave', function() {
                        this.classList.remove('bouncing');
                    });
                });
            });
        }

        // 摘要悬浮窗 - 跟随鼠标显示
        function initDescriptionTooltip() {
            const tooltip = document.getElementById('description-tooltip');
            if (!tooltip) return;

            document.querySelectorAll('.overview-item').forEach(item => {
                item.addEventListener('mouseenter', (e) => {
                    const desc = item.querySelector('.item-description');
                    if (desc && desc.textContent.trim()) {
                        tooltip.textContent = desc.textContent;
                        tooltip.classList.add('visible');
                        positionTooltip(e.clientX, e.clientY);
                    }
                });

                item.addEventListener('mousemove', (e) => {
                    if (tooltip.classList.contains('visible')) {
                        positionTooltip(e.clientX, e.clientY);
                    }
                });

                item.addEventListener('mouseleave', () => {
                    tooltip.classList.remove('visible');
                });
            });
        }

        function positionTooltip(x, y) {
            const tooltip = document.getElementById('description-tooltip');
            if (!tooltip) return;
            const padding = 15;
            const tooltipRect = tooltip.getBoundingClientRect();

            let left = x + padding;
            let top = y + padding;

            if (left + tooltipRect.width > window.innerWidth) {
                left = x - tooltipRect.width - padding;
            }
            if (left < 0) left = padding;

            if (top + tooltipRect.height > window.innerHeight) {
                top = y - tooltipRect.height - padding;
            }
            if (top < 0) top = padding;

            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        }

        const SOURCE_STYLES = {
            github: { emoji: '🐙', label: 'GitHub', color: '#24292e', bg: '#f0f0f0' },
            github_ai: { emoji: '🤖', label: 'AI', color: '#6e40c9', bg: '#f5f0ff' },
            hackernews: { emoji: '📰', label: 'HN', color: '#ff6600', bg: '#fff5eb' },
            bilibili: { emoji: '📺', label: 'B站', color: '#00a1d6', bg: '#e6f7ff' },
            arxiv: { emoji: '📚', label: 'ArXiv', color: '#b31b1b', bg: '#fff0f0' },
            zhihu: { emoji: '❓', label: '知乎', color: '#0084ff', bg: '#e6f3ff' },
            weibo: { emoji: '📱', label: '微博', color: '#e6162d', bg: '#fff0f0' },
            douyin: { emoji: '🎵', label: '抖音', color: '#161823', bg: '#f0f0f5' },
            aihot: { emoji: '🔥', label: 'AIHOT', color: '#d29922', bg: '#fff8e6' }
        };

        function initSearch() {
            const searchInput = document.getElementById('search-input');
            const searchBtn = document.getElementById('search-btn');
            const searchClearBtn = document.getElementById('search-clear-btn');
            const searchPanel = document.getElementById('search-results-panel');
            const searchList = document.getElementById('search-results-list');
            const searchCount = document.getElementById('search-results-count');

            function highlightText(text, query) {
                if (!text || !query) return text || '';
                const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(`(${escaped})`, 'gi');
                return text.replace(regex, '<mark>$1</mark>');
            }

            function getSourceStyle(source) {
                return SOURCE_STYLES[source] || { emoji: '📌', label: source, color: '#666', bg: '#f5f5f5' };
            }

            function formatScore(score) {
                if (!score) return '';
                if (score >= 10000) return (score / 10000).toFixed(1) + '万';
                if (score >= 1000) return (score / 1000).toFixed(1) + 'k';
                return score.toString();
            }

            async function doSearch() {
                const query = searchInput.value.trim();
                if (!query) return;

                searchBtn.textContent = '...';
                searchList.innerHTML = '<div class="search-loading">搜索中...</div>';
                searchPanel.classList.add('visible');
                searchClearBtn.classList.add('visible');

                try {
                    const activeSource = document.querySelector('.source-tag.active');
                    const sourceParam = activeSource && activeSource.dataset.source !== 'all' ? `&source=${activeSource.dataset.source}` : '';
                    const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}${sourceParam}&limit=100`);
                    const data = await resp.json();

                    if (!data.success) {
                        searchList.innerHTML = `<div class="search-no-results">搜索失败: ${data.error}</div>`;
                        return;
                    }

                    const items = data.items || [];
                    searchCount.textContent = `共 ${items.length} 条结果`;

                    if (items.length === 0) {
                        searchList.innerHTML = `<div class="search-no-results">未找到与 "${query}" 相关的记录</div>`;
                        return;
                    }

                    searchList.innerHTML = items.map(item => {
                        const style = getSourceStyle(item.source);
                        const title = highlightText(item.title, query);
                        const desc = item.description ? highlightText(item.description.substring(0, 120), query) : '';
                        const date = item.fetched_at ? item.fetched_at.substring(0, 10) : '';
                        return `
                            <a href="${item.url || '#'}" target="_blank" class="search-result-item">
                                <span class="search-result-source" style="background:${style.bg};color:${style.color}">${style.emoji} ${style.label}</span>
                                <div class="search-result-info">
                                    <div class="search-result-title">${title}</div>
                                    ${desc ? `<div class="search-result-desc">${desc}</div>` : ''}
                                </div>
                                ${item.hot_score ? `<span class="search-result-score">🔥 ${formatScore(item.hot_score)}</span>` : ''}
                                ${date ? `<span class="search-result-date">${date}</span>` : ''}
                            </a>
                        `;
                    }).join('');
                } catch (e) {
                    searchList.innerHTML = `<div class="search-no-results">搜索出错: ${e.message}</div>`;
                } finally {
                    searchBtn.textContent = '搜索';
                }
            }

            function clearSearch() {
                searchInput.value = '';
                searchPanel.classList.remove('visible');
                searchClearBtn.classList.remove('visible');
                searchList.innerHTML = '';
                searchCount.textContent = '';
            }

            searchBtn.addEventListener('click', doSearch);
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') doSearch();
            });
            searchClearBtn.addEventListener('click', clearSearch);
        }

        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', () => {
            initBounceEffects();
            initDescriptionTooltip();
            initSearch();
        });

        // 渲染总览
        function renderOverview(data) {
            const container = document.getElementById('overview-content');
            let sources = data.sources || {};
            
            // 应用数据源筛选
            if (currentSource !== 'all') {
                const filtered = {};
                if (sources[currentSource]) {
                    filtered[currentSource] = sources[currentSource];
                }
                sources = filtered;
            }
            
            if (Object.keys(sources).length === 0) {
                container.innerHTML = '<div class="empty-state"><div class="emoji">📭</div><div>暂无数据</div></div>';
                return;
            }

            // 计算每个数据源前10项的热度总和并排序
            const sourceWithHeat = Object.entries(sources).map(([source, items]) => {
                const top10Items = items.slice(0, 10);
                const totalHeat = top10Items.reduce((sum, item) => sum + (item.hot_score || 0), 0);
                return { source, items, totalHeat };
            }).sort((a, b) => b.totalHeat - a.totalHeat);

            let html = '';
            for (const { source, items } of sourceWithHeat) {
                const config = sourceConfig[source] || { icon: '📄', name: source };
                
                html += `
                    <div class="source-card">
                        <div class="source-header">
                            <div class="source-name">${config.icon} ${config.name}</div>
                            <div class="source-count">${items.length} 条</div>
                        </div>
                        <div class="source-content">
                            <ul class="item-list overview-list">
                                ${items.slice(0, 10).map((item, index) => `
                                    <li class="overview-item">
                                        <div class="item-rank">${index + 1}</div>
                                        <div class="item-title">
                                            <a href="${item.url}" target="_blank">${item.title}</a>
                                            <div class="item-meta">
                                                ${item.author ? `<span class="meta-tag">👤 ${item.author}</span>` : ''}
                                            </div>
                                        </div>
                                        <div class="item-score">${item.hot_score ? '🔥 ' + formatNumber(item.hot_score) : ''}</div>
                                        ${item.description ? `<div class="item-description">${item.description}</div>` : ''}
                                    </li>
                                `).join('')}
                            </ul>
                        </div>
                    </div>
                `;
            }
            container.innerHTML = html;
            initDescriptionTooltip();
        }

        // 词云数据配置
        let savedKeywordsData = null;
        let wordCloudRendered = false;

        // 渲染词云 - 使用 HTML div
        function renderWordCloud(keywords) {
            const container = document.getElementById('word-cloud-container');
            if (!container || !keywords || Object.keys(keywords).length === 0) return;

            // 检查 container 是否可见
            if (container.offsetWidth === 0) {
                console.warn('词云容器不可见，稍后重试');
                return;
            }

            // 颜色方案
            const colors = [
                '#667eea', '#764ba2', '#f093fb', '#f5576c',
                '#4facfe', '#00f2fe', '#43e97b', '#38f9d7',
                '#ffecd2', '#fcb69f', '#ff8a80', '#ffab91',
                '#b9f6ca', '#a5d6a7', '#80cbc4', '#4db6ac'
            ];

            // 准备数据并排序
            const wordList = Object.entries(keywords)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 100); // 最多显示100个词

            // 计算最大和最小计数，用于字体大小映射
            const maxCount = Math.max(...wordList.map(w => w[1]));
            const minCount = Math.min(...wordList.map(w => w[1]));

            // 生成 HTML - 按频次分组显示
            let html = '';
            
            // 高频词（前20%）- 更大更突出
            const highFreqCount = Math.ceil(wordList.length * 0.2);
            const highFreqWords = wordList.slice(0, highFreqCount);
            
            // 中频词（20%-60%）
            const midFreqWords = wordList.slice(highFreqCount, Math.ceil(wordList.length * 0.6));
            
            // 低频词（剩余）
            const lowFreqWords = wordList.slice(Math.ceil(wordList.length * 0.6));
            
            // 渲染高频词 - 更大
            highFreqWords.forEach(([word, count]) => {
                const fontSize = 2.2 + (count - minCount) / (maxCount - minCount) * 1.0;
                const color = colors[Math.floor(Math.random() * colors.length)];
                html += renderWordItem(word, count, fontSize, color, 'high');
            });
            
            // 渲染中频词
            midFreqWords.forEach(([word, count]) => {
                const fontSize = 1.4 + (count - minCount) / (maxCount - minCount) * 0.8;
                const color = colors[Math.floor(Math.random() * colors.length)];
                html += renderWordItem(word, count, fontSize, color, 'medium');
            });
            
            // 渲染低频词
            lowFreqWords.forEach(([word, count]) => {
                const fontSize = 0.9 + (count - minCount) / (maxCount - minCount) * 0.5;
                const color = colors[Math.floor(Math.random() * colors.length)];
                html += renderWordItem(word, count, fontSize, color, 'low');
            });

            container.innerHTML = html;
            wordCloudRendered = true;
            
            // 更新统计信息
            updateKeywordStats(wordList, maxCount);
        }

        // 渲染单个词项
        function renderWordItem(word, count, fontSize, color, freqLevel) {
            const opacity = freqLevel === 'high' ? '30' : freqLevel === 'medium' ? '20' : '15';
            const borderOpacity = freqLevel === 'high' ? '60' : freqLevel === 'medium' ? '40' : '30';
            
            return `
                <span class="word-cloud-item word-cloud-${freqLevel}" 
                      style="font-size: ${fontSize.toFixed(2)}em; 
                             background: ${color}${opacity}; 
                             color: ${color}; 
                             border: 2px solid ${color}${borderOpacity};"
                      title="${word}: 出现 ${count} 次"
                      onclick="filterByKeyword('${word}')">
                    ${word}
                    <span class="word-cloud-count">${count}</span>
                </span>
            `;
        }

        // 更新关键词统计信息
        function updateKeywordStats(wordList, maxCount) {
            const totalCount = wordList.length;
            const avgCount = (wordList.reduce((sum, w) => sum + w[1], 0) / totalCount).toFixed(1);
            
            const totalEl = document.getElementById('keyword-total-count');
            const maxEl = document.getElementById('keyword-max-count');
            const avgEl = document.getElementById('keyword-avg-count');
            
            if (totalEl) totalEl.textContent = totalCount;
            if (maxEl) maxEl.textContent = maxCount;
            if (avgEl) avgEl.textContent = avgCount;
        }

        // 点击关键词筛选
        function filterByKeyword(keyword) {
            console.log('筛选关键词:', keyword);
            // 可以在这里添加筛选逻辑，比如高亮包含该关键词的内容
            showNotification(`已选择关键词: ${keyword}`, 'info');
        }



        // 渲染关键词 - 主入口
        function renderKeywords(data) {
            const keywords = data.keywords || {};
            savedKeywordsData = keywords;
            
            if (Object.keys(keywords).length === 0) {
                const container = document.getElementById('word-cloud-container');
                if (container) {
                    container.innerHTML = '<div class="empty-state"><div class="emoji">🏷️</div><div>暂无关键词数据</div></div>';
                }
                return;
            }

            // 检查是否在 keywords tab 中
            const keywordsTab = document.getElementById('keywords');
            if (keywordsTab && keywordsTab.classList.contains('active')) {
                // 如果在 keywords tab 中，立即渲染
                renderWordCloud(keywords);
            }
            // 否则等待 tab 切换时再渲染
        }

        // 渲染描述（支持展开/收起）
        function renderDescription(description, sourceName, index) {
            if (!description || description === '-') {
                return '';
            }

            // 只有知乎数据源且描述较长时才使用展开功能
            const isZhihu = sourceName === 'zhihu';
            const maxLength = 100;

            if (!isZhihu || description.length <= maxLength) {
                return `<div class="item-card-description">${description}</div>`;
            }

            const shortDesc = description.substring(0, maxLength) + '...';
            const descId = `desc-${sourceName}-${index}`;

            return `
                <div class="item-card-description expandable" id="${descId}">
                    <span class="desc-short">${shortDesc}</span>
                    <span class="desc-full" style="display: none;">${description}</span>
                    <button class="desc-toggle" onclick="toggleDescription('${descId}')">展开</button>
                </div>
            `;
        }

        // 切换描述展开/收起
        function toggleDescription(descId) {
            const descEl = document.getElementById(descId);
            const shortEl = descEl.querySelector('.desc-short');
            const fullEl = descEl.querySelector('.desc-full');
            const btnEl = descEl.querySelector('.desc-toggle');

            if (fullEl.style.display === 'none') {
                shortEl.style.display = 'none';
                fullEl.style.display = 'inline';
                btnEl.textContent = '收起';
            } else {
                shortEl.style.display = 'inline';
                fullEl.style.display = 'none';
                btnEl.textContent = '展开';
            }
        }

        // 格式化数字（添加千分位）
        function formatNumber(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return Math.round(num).toString();
        }

        // 渲染综合分析 - 合并 trends 和 dashboard
        function renderAnalysis(data) {
            const trends = data.trends || {};
            const sources = data.sources || {};

            // 正确合并数据，确保每个 item 都有 source 字段
            let allItems = [];
            for (const [sourceName, items] of Object.entries(sources)) {
                if (Array.isArray(items)) {
                    items.forEach(item => {
                        allItems.push({
                            ...item,
                            source: item.source || sourceName
                        });
                    });
                }
            }

            // 应用筛选
            if (dashboardFilter !== 'all') {
                allItems = allItems.filter(item => item.source === dashboardFilter);
            }

            // 应用排序
            allItems.sort((a, b) => {
                if (dashboardSort === 'hot') return (b.hot_score || 0) - (a.hot_score || 0);
                if (dashboardSort === 'time') return new Date(b.fetched_at) - new Date(a.fetched_at);
                return 0;
            });

            // 更新关键指标卡片
            updateAnalysisMetrics(allItems, trends.summary, data);

            // 渲染实时概览三列卡片
            renderOverviewCards(allItems, data);

            // 渲染趋势图表
            updateTrendSummary(trends.summary);
            renderTotalTrendChart(trends.summary);
            renderSourceTrendChart(trends.source_trends);
            renderKeywordTrendChart(trends.keyword_trends);
        }

        // 更新综合分析的关键指标
        function updateAnalysisMetrics(allItems, summary, data) {
            // 优先使用数据库全量统计数据
            const dbStats = data.db_stats || {};

            // 基础指标（优先使用数据库全量统计）
            document.getElementById('metric-total').textContent = formatNumber(dbStats.total_count || allItems.length);
            document.getElementById('metric-platforms').textContent = dbStats.sources_count || new Set(allItems.map(i => i.source)).size;

            const maxHeat = allItems.length > 0 ? Math.max(...allItems.map(i => i.hot_score || 0)) : 0;
            document.getElementById('metric-peak').textContent = formatNumber(maxHeat);

            if (allItems.length > 0) {
                const latest = new Date(allItems[0].fetched_at);
                document.getElementById('metric-update').textContent =
                    latest.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            }

            // 趋势指标（优先使用数据库全量统计）
            if (dbStats.daily_counts && dbStats.daily_counts.length > 0) {
                // 使用数据库统计的日趋势数据
                const dailyCounts = dbStats.daily_counts;

                // 计算增长率（最近3天 vs 前3天）
                const recent3 = dailyCounts.slice(-3);
                const previous3 = dailyCounts.slice(-6, -3);
                const recentSum = recent3.reduce((sum, day) => sum + (day.count || 0), 0);
                const previousSum = previous3.reduce((sum, day) => sum + (day.count || 0), 0);
                const growthRate = previousSum > 0 ? ((recentSum - previousSum) / previousSum * 100).toFixed(1) : 0;

                // 找出峰值日期
                const peakDay = dailyCounts.reduce((max, day) => (day.count || 0) > (max.count || 0) ? day : max, dailyCounts[0]);

                // 更新趋势指标卡片
                document.getElementById('trend-growth-rate').textContent = (growthRate > 0 ? '+' : '') + growthRate + '%';
                document.getElementById('trend-growth-rate').style.color = growthRate >= 0 ? '#43e97b' : '#ff6b6b';
                document.getElementById('trend-peak-day').textContent = peakDay.date ? new Date(peakDay.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'}) : '--';
                document.getElementById('trend-avg-daily').textContent = formatNumber(dbStats.avg_daily || 0);
            } else if (summary && summary.total_trend && summary.total_trend.length > 0) {
                // 回退到 trends 数据
                const trend = summary.total_trend;
                const total = trend.reduce((sum, day) => sum + day.count, 0);
                const avgDaily = Math.round(total / trend.length);

                // 计算增长率（最近7天 vs 前7天）
                const recent7 = trend.slice(-7);
                const previous7 = trend.slice(-14, -7);
                const recentSum = recent7.reduce((sum, day) => sum + day.count, 0);
                const previousSum = previous7.reduce((sum, day) => sum + day.count, 0);
                const growthRate = previousSum > 0 ? ((recentSum - previousSum) / previousSum * 100).toFixed(1) : 0;

                // 找出峰值日期
                const peakDay = trend.reduce((max, day) => day.count > max.count ? day : max, trend[0]);

                // 更新趋势指标卡片
                document.getElementById('trend-growth-rate').textContent = (growthRate > 0 ? '+' : '') + growthRate + '%';
                document.getElementById('trend-growth-rate').style.color = growthRate >= 0 ? '#43e97b' : '#ff6b6b';
                document.getElementById('trend-peak-day').textContent = new Date(peakDay.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'});
                document.getElementById('trend-avg-daily').textContent = formatNumber(avgDaily);
            }
        }

        // 渲染实时概览三列卡片
        function renderOverviewCards(allItems, data) {
            const platformColors = {
                'weibo': '#e74c3c', 'douyin': '#000000', 'zhihu': '#3498db',
                'bilibili': '#fb7299', 'github': '#333333', 'hackernews': '#ff6600',
                'arxiv': '#16a085', 'github_ai': '#9b59b6'
            };

            const platformNames = {
                'weibo': '📱 微博', 'douyin': '🎵 抖音', 'zhihu': '❓ 知乎',
                'bilibili': '📺 B站', 'github': '🐙 GitHub', 'hackernews': '📰 HN',
                'arxiv': '📚 ArXiv', 'github_ai': '🤖 GitHub AI'
            };

            // 平台分布 - 优先使用数据库全量统计
            const platformBars = document.getElementById('platform-bars');
            const dbStats = data.db_stats || {};
            const dbBySource = dbStats.by_source || {};

            let platformCounts = {};
            let total = allItems.length;

            // 如果有数据库全量统计，使用它
            if (Object.keys(dbBySource).length > 0) {
                Object.entries(dbBySource).forEach(([source, stats]) => {
                    platformCounts[source] = stats.count || 0;
                });
                total = dbStats.total_count || allItems.length;
            } else {
                // 回退到使用今日数据
                allItems.forEach(item => {
                    const source = item.source || 'unknown';
                    platformCounts[source] = (platformCounts[source] || 0) + 1;
                });
            }

            platformBars.innerHTML = Object.entries(platformCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([platform, count]) => {
                    const percent = total > 0 ? (count / total * 100).toFixed(1) : 0;
                    const color = platformColors[platform] || '#95a5a6';
                    const name = platformNames[platform] || platform;
                    return `
                        <div style="margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <span style="font-weight: 500;">${name}</span>
                                <span style="color: #666;">${count} (${percent}%)</span>
                            </div>
                            <div style="background: #ecf0f1; height: 8px; border-radius: 4px; overflow: hidden;">
                                <div style="background: ${color}; height: 100%; width: ${percent}%; transition: width 0.5s;"></div>
                            </div>
                        </div>
                    `;
                }).join('');

            // 每日趋势图 - 使用最近7天的数据，带折线效果
            const dailyTrendChart = document.getElementById('daily-trend-chart');
            const dailyCounts = dbStats.daily_counts || [];

            if (dailyCounts.length > 0) {
                const counts = dailyCounts.map(d => d.count || 0);
                const maxCount = Math.max(...counts, 1);
                const minCount = Math.min(...counts);
                const range = maxCount - minCount || 1;

                const svgWidth = 100;
                const chartHeight = 50;
                const chartTop = 5;
                const labelY = 72;
                const chartBottom = chartTop + chartHeight;

                const dataPoints = counts.map((count, i) => {
                    const x = counts.length === 1 ? svgWidth / 2 : (i / (counts.length - 1)) * svgWidth;
                    const normalizedY = (count - minCount) / range;
                    const y = chartBottom - normalizedY * chartHeight * 0.85 - chartHeight * 0.05;
                    return { x, y: Math.max(chartTop, Math.min(chartBottom, y)), count };
                });

                const linePoints = dataPoints.map(p => `${p.x},${p.y}`).join(' ');
                const areaPoints = `0,${chartBottom} ${linePoints} ${svgWidth},${chartBottom}`;

                dailyTrendChart.innerHTML = `
                    <svg viewBox="0 0 ${svgWidth} 80" style="width: 100%; height: 100%; overflow: hidden;" class="daily-trend-svg">
                        <defs>
                            <linearGradient id="trendGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" style="stop-color:#667eea;stop-opacity:0.3" />
                                <stop offset="100%" style="stop-color:#667eea;stop-opacity:0.05" />
                            </linearGradient>
                        </defs>
                        <polygon points="${areaPoints}" fill="url(#trendGradient)" />
                        <polyline points="${linePoints}" fill="none" stroke="#667eea" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                        ${dataPoints.map((p, i) => {
                            const dateLabel = dailyCounts[i].date ? new Date(dailyCounts[i].date).toLocaleDateString('zh-CN', {month: 'numeric', day: 'numeric'}) : '';
                            return `<g class="trend-data-point" data-count="${p.count}" data-date="${dateLabel}">
                                <circle cx="${p.x}" cy="${p.y}" r="8" fill="transparent" class="trend-hit-area" />
                                <circle cx="${p.x}" cy="${p.y}" r="3" fill="#667eea" stroke="white" stroke-width="1.5" class="trend-dot" />
                                <text x="${p.x}" y="${labelY}" text-anchor="middle" font-size="6" fill="#666">${dateLabel}</text>
                            </g>`;
                        }).join('')}
                    </svg>
                    <div class="trend-tooltip" id="daily-trend-tooltip"></div>
                `;

                const tooltip = document.getElementById('daily-trend-tooltip');
                const svgEl = dailyTrendChart.querySelector('.daily-trend-svg');
                dailyTrendChart.querySelectorAll('.trend-data-point').forEach(g => {
                    g.addEventListener('mouseenter', (e) => {
                        const count = g.dataset.count;
                        const date = g.dataset.date;
                        const dot = g.querySelector('.trend-dot');
                        dot.setAttribute('r', '5');
                        dot.setAttribute('fill', '#4f46e5');
                        tooltip.textContent = `${date}：${count} 条`;
                        tooltip.classList.add('visible');
                    });
                    g.addEventListener('mousemove', (e) => {
                        const rect = dailyTrendChart.getBoundingClientRect();
                        tooltip.style.left = (e.clientX - rect.left + 10) + 'px';
                        tooltip.style.top = (e.clientY - rect.top - 30) + 'px';
                    });
                    g.addEventListener('mouseleave', () => {
                        const dot = g.querySelector('.trend-dot');
                        dot.setAttribute('r', '3');
                        dot.setAttribute('fill', '#667eea');
                        tooltip.classList.remove('visible');
                    });
                });
            } else {
                dailyTrendChart.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">暂无趋势数据</div>';
            }

            // 每日数据量 - 显示最近7天的数据量列表，完全利用div空间
            const dailyCountsChart = document.getElementById('daily-counts-chart');

            if (dailyCounts.length > 0) {
                const maxCount = Math.max(...dailyCounts.map(d => d.count || 0), 1);
                const containerHeight = dailyCountsChart.clientHeight || 140;
                const itemHeight = Math.floor(containerHeight / dailyCounts.length);
                const barHeight = Math.max(itemHeight - 8, 16); // 进度条高度

                dailyCountsChart.innerHTML = dailyCounts.map((item, index) => {
                    const count = item.count || 0;
                    const percent = (count / maxCount * 100);
                    const dateLabel = item.date ? new Date(item.date).toLocaleDateString('zh-CN', {month: 'numeric', day: 'numeric'}) : '';
                    const dayName = item.date ? new Date(item.date).toLocaleDateString('zh-CN', {weekday: 'short'}) : '';
                    const isToday = index === dailyCounts.length - 1;
                    const isMax = count === maxCount;

                    return `
                        <div style="display: flex; align-items: center; gap: 8px; height: ${itemHeight}px; ${isToday ? 'background: rgba(102, 126, 234, 0.08); border-radius: 8px; margin: 0 -6px; padding: 0 6px;' : ''}">
                            <span style="width: 38px; color: ${isToday ? '#667eea' : '#555'}; font-weight: ${isToday ? '700' : '500'}; font-size: 0.9em; flex-shrink: 0;">${dateLabel}</span>
                            <span style="width: 26px; color: #888; font-size: 0.8em; flex-shrink: 0;">${dayName}</span>
                            <div style="flex: 1; background: #e8e8e8; height: ${barHeight}px; border-radius: ${barHeight/2}px; overflow: hidden; min-width: 60px;">
                                <div style="background: ${isMax ? 'linear-gradient(90deg, #ff6b6b, #feca57)' : isToday ? 'linear-gradient(90deg, #667eea, #764ba2)' : 'linear-gradient(90deg, #667eea, #764ba2)'}; height: 100%; width: ${percent}%; transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); border-radius: ${barHeight/2}px; box-shadow: ${isMax || isToday ? '0 2px 8px rgba(102, 126, 234, 0.3)' : 'none'};"></div>
                            </div>
                            <span style="width: 42px; text-align: right; font-weight: ${isToday || isMax ? '700' : '600'}; color: ${isToday ? '#667eea' : isMax ? '#ff6b6b' : '#444'}; font-size: 0.95em; flex-shrink: 0;">${count}</span>
                        </div>
                    `;
                }).join('');
            } else {
                dailyCountsChart.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">暂无数据</div>';
            }
        }

        // 更新趋势概览卡片
        function updateTrendSummary(summary) {
            if (!summary || !summary.total_trend || summary.total_trend.length === 0) {
                return;
            }

            const trend = summary.total_trend;
            const total = trend.reduce((sum, day) => sum + day.count, 0);
            const avgDaily = Math.round(total / trend.length);

            // 计算增长率（最近7天 vs 前7天）
            const recent7 = trend.slice(-7);
            const previous7 = trend.slice(-14, -7);
            const recentSum = recent7.reduce((sum, day) => sum + day.count, 0);
            const previousSum = previous7.reduce((sum, day) => sum + day.count, 0);
            const growthRate = previousSum > 0 ? ((recentSum - previousSum) / previousSum * 100).toFixed(1) : 0;

            // 找出峰值日期
            const peakDay = trend.reduce((max, day) => day.count > max.count ? day : max, trend[0]);

            // 更新卡片（如果元素存在）
            const trendTotalItems = document.getElementById('trend-total-items');
            const trendGrowthRate = document.getElementById('trend-growth-rate');
            const trendPeakDay = document.getElementById('trend-peak-day');
            const trendAvgDaily = document.getElementById('trend-avg-daily');

            if (trendTotalItems) trendTotalItems.textContent = formatNumber(total);
            if (trendGrowthRate) {
                trendGrowthRate.textContent = (growthRate > 0 ? '+' : '') + growthRate + '%';
                trendGrowthRate.style.color = growthRate >= 0 ? '#43e97b' : '#ff6b6b';
            }
            if (trendPeakDay) trendPeakDay.textContent = new Date(peakDay.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'});
            if (trendAvgDaily) trendAvgDaily.textContent = formatNumber(avgDaily);
        }

        // 计算移动平均线
        function calculateMovingAverage(data, period = 7) {
            const result = [];
            for (let i = 0; i < data.length; i++) {
                if (i < period - 1) {
                    result.push(null);
                } else {
                    let sum = 0;
                    for (let j = 0; j < period; j++) {
                        sum += data[i - j].count;
                    }
                    result.push(Math.round(sum / period));
                }
            }
            return result;
        }

        // 线性回归预测
        function linearRegressionPredict(data, daysToPredict = 3) {
            const n = data.length;
            if (n < 2) return [];

            // 计算均值
            let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
            for (let i = 0; i < n; i++) {
                sumX += i;
                sumY += data[i].count;
                sumXY += i * data[i].count;
                sumXX += i * i;
            }

            const meanX = sumX / n;
            const meanY = sumY / n;

            // 计算斜率和截距
            const slope = (sumXY - n * meanX * meanY) / (sumXX - n * meanX * meanX);
            const intercept = meanY - slope * meanX;

            // 生成预测
            const predictions = [];
            const lastDate = new Date(data[n - 1].date);

            for (let i = 1; i <= daysToPredict; i++) {
                const predictedValue = Math.round(slope * (n - 1 + i) + intercept);
                const predictedDate = new Date(lastDate);
                predictedDate.setDate(predictedDate.getDate() + i);

                predictions.push({
                    date: predictedDate.toISOString().split('T')[0],
                    count: Math.max(0, predictedValue),
                    isPrediction: true
                });
            }

            return predictions;
        }

        // 渲染总趋势图（含预测）
        function renderTotalTrendChart(summary) {
            const canvas = document.getElementById('total-trend-canvas');
            if (!canvas) {
                console.log('总趋势图 canvas 未找到');
                return;
            }
            if (!summary || !summary.total_trend || summary.total_trend.length === 0) {
                console.log('总趋势图数据为空', summary);
                return;
            }

            // 确保 canvas 有正确的尺寸
            const container = canvas.parentElement;
            if (container) {
                canvas.width = container.clientWidth;
                canvas.height = container.clientHeight || 300;
            }

            const trend = summary.total_trend;
            const labels = trend.map(d => new Date(d.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'}));
            const data = trend.map(d => d.count);

            // 计算移动平均线
            const movingAvg = calculateMovingAverage(trend, 7);

            // 生成预测
            const predictions = linearRegressionPredict(trend, 3);
            const predictionLabels = predictions.map(p => new Date(p.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'}));
            const predictionData = predictions.map(p => p.count);

            // 销毁旧图表
            if (window.totalTrendChart) {
                window.totalTrendChart.destroy();
            }

            // 创建新图表
            window.totalTrendChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: [...labels, ...predictionLabels],
                    datasets: [
                        {
                            label: '实际数据',
                            data: [...data, ...Array(predictions.length).fill(null)],
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#667eea'
                        },
                        {
                            label: '7日移动平均',
                            data: [...movingAvg, ...Array(predictions.length).fill(null)],
                            borderColor: '#f093fb',
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 0
                        },
                        {
                            label: '趋势预测',
                            data: [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictionData],
                            borderColor: '#ff6b6b',
                            borderDash: [10, 5],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#ff6b6b'
                        }
                    ]
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
                            position: 'top',
                            labels: {
                                usePointStyle: true,
                                padding: 15
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed.y !== null) {
                                        label += context.parsed.y + ' 条';
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        }

        // 渲染数据源趋势对比图
        function renderSourceTrendChart(sourceTrends) {
            const canvas = document.getElementById('source-trend-canvas');
            if (!canvas || !sourceTrends || Object.keys(sourceTrends).length === 0) {
                return;
            }

            // 计算每个数据源的总数据量并排序
            const sourceTotals = {};
            for (const [source, trend] of Object.entries(sourceTrends)) {
                sourceTotals[source] = trend.reduce((sum, day) => sum + day.count, 0);
            }

            const sortedSources = Object.entries(sourceTotals)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 5);

            const topSources = sortedSources.map(([source]) => source);

            // 获取日期标签（使用第一个数据源的日期）
            const firstSource = topSources[0];
            const labels = sourceTrends[firstSource].map(d =>
                new Date(d.date).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric'})
            );

            // 颜色方案
            const colors = [
                {border: '#667eea', bg: 'rgba(102, 126, 234, 0.1)'},
                {border: '#f093fb', bg: 'rgba(240, 147, 251, 0.1)'},
                {border: '#43e97b', bg: 'rgba(67, 233, 123, 0.1)'},
                {border: '#ff6b6b', bg: 'rgba(255, 107, 107, 0.1)'},
                {border: '#feca57', bg: 'rgba(254, 202, 87, 0.1)'}
            ];

            // 构建数据集
            const datasets = topSources.map((source, index) => {
                const color = colors[index % colors.length];
                return {
                    label: source.toUpperCase(),
                    data: sourceTrends[source].map(d => d.count),
                    borderColor: color.border,
                    backgroundColor: color.bg,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3
                };
            });

            // 销毁旧图表
            if (window.sourceTrendChart) {
                window.sourceTrendChart.destroy();
            }

            // 创建新图表
            window.sourceTrendChart = new Chart(canvas, {
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
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                usePointStyle: true,
                                padding: 15
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        }

        // 渲染关键词趋势图
        function renderKeywordTrendChart(keywordTrends) {
            const container = document.getElementById('keyword-trend-container');
            if (!container) {
                console.log('关键词趋势图容器不存在');
                return;
            }

            if (!keywordTrends || Object.keys(keywordTrends).length === 0) {
                container.innerHTML = '<div class="empty-state">暂无数据</div>';
                return;
            }

            // 计算每个关键词的总出现次数（限制在最近5天）
            const DAYS_LIMIT = 5;
            const keywordTotals = {};
            for (const [keyword, trend] of Object.entries(keywordTrends)) {
                // 按日期排序（最新的在前），取前5天
                const sortedTrend = trend.sort((a, b) => new Date(b.date) - new Date(a.date));
                const recentTrend = sortedTrend.slice(0, DAYS_LIMIT);
                keywordTotals[keyword] = recentTrend.reduce((sum, day) => sum + day.count, 0);
            }

            // 排序并取前8个
            const sortedKeywords = Object.entries(keywordTotals)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8);

            const maxValue = Math.max(...sortedKeywords.map(k => k[1])) || 1;

            let html = '<div class="simple-chart">';
            sortedKeywords.forEach(([keyword, total]) => {
                const height = (total / maxValue * 200) + 'px';
                html += `
                    <div class="chart-bar">
                        <div class="bar" style="height: ${height}; background: linear-gradient(to top, #ff6b6b 0%, #feca57 100%);">
                            <span class="bar-value">${total}</span>
                        </div>
                        <div class="bar-label">${keyword}</div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        }

        // 初始化页面
        function init() {
            const data = window.REPORT_DATA;

            // 设置生成时间
            document.getElementById('generated-time').textContent =
                data.generated_at ? new Date(data.generated_at).toLocaleString('zh-CN') : '--';

            // 设置统计数据 - 优先使用数据库全量统计
            const dbStats = data.db_stats || {};
            document.getElementById('total-items').textContent = formatNumber(dbStats.total_count || data.total_items || 0);
            document.getElementById('total-sources').textContent =
                dbStats.sources_count || (data.sources ? Object.keys(data.sources).length : 0);

            // 渲染各部分内容
            renderOverview(data);
            renderKeywords(data);
            renderGitHubWeekly(data);

            // 绑定导航Tab点击事件
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.addEventListener('click', function() {
                    const viewName = this.dataset.view;
                    if (viewName === 'source-detail' || currentView === 'source-detail') {
                        switchView(viewName);
                    } else {
                        switchView(viewName);
                    }
                });
            });

            // 绑定数据源标签点击事件
            document.querySelectorAll('.source-tag').forEach(tag => {
                tag.addEventListener('click', function() {
                    const sourceName = this.dataset.source;
                    switchSource(sourceName);
                    // 切换到数据源详情视图
                    switchView('source-detail');
                });
            });

            // 绑定分类下拉框事件
            document.getElementById('source-category').addEventListener('change', function() {
                filterByCategory(this.value);
            });

            // 初始化日期选择器
            initDatePicker();

            // 恢复上次查看的 tab（报告刷新后保留视图）
            try {
                const savedView = localStorage.getItem('trending_current_view');
                if (savedView && savedView !== 'overview') {
                    const tabExists = document.querySelector('.nav-tab[data-view="' + savedView + '"]');
                    if (tabExists) {
                        setTimeout(() => switchView(savedView), 50);
                    }
                }
            } catch(e) {}
        }

        // 当前选中的日期范围
        let currentDateRange = { start: null, end: null };

        // 初始化日期选择器
        function initDatePicker() {
            const dateStart = document.getElementById('date-start');
            const dateEnd = document.getElementById('date-end');
            const applyBtn = document.getElementById('date-apply-btn');
            const dateLoading = document.getElementById('date-loading');

            // 设置最大日期为今天
            const today = new Date().toISOString().split('T')[0];
            dateStart.max = today;
            dateEnd.max = today;

            // 默认选择当日（开始日期和结束日期都为今天）
            dateStart.value = today;
            dateEnd.value = today;
            currentDateRange = { start: today, end: today };

            // 绑定开始日期变化事件（限制结束日期不能早于开始日期）
            dateStart.addEventListener('change', function() {
                const startDate = this.value;
                if (startDate) {
                    dateEnd.min = startDate;
                    // 如果结束日期早于开始日期，自动调整
                    if (dateEnd.value && dateEnd.value < startDate) {
                        dateEnd.value = startDate;
                    }
                }
            });

            // 绑定结束日期变化事件（限制开始日期不能晚于结束日期）
            dateEnd.addEventListener('change', function() {
                const endDate = this.value;
                if (endDate) {
                    dateStart.max = endDate;
                    // 如果开始日期晚于结束日期，自动调整
                    if (dateStart.value && dateStart.value > endDate) {
                        dateStart.value = endDate;
                    }
                }
            });

            // 绑定应用按钮事件
            applyBtn.addEventListener('click', function() {
                const startDate = dateStart.value;
                const endDate = dateEnd.value;

                if (!startDate || !endDate) {
                    showToast('❌ 请选择开始和结束日期', 'error');
                    return;
                }

                if (startDate > endDate) {
                    showToast('❌ 开始日期不能晚于结束日期', 'error');
                    return;
                }

                currentDateRange = { start: startDate, end: endDate };
                loadDataForDateRange(startDate, endDate);
            });
        }

        // 加载指定日期范围的数据
        async function loadDataForDateRange(startDate, endDate) {
            const dateStart = document.getElementById('date-start');
            const dateEnd = document.getElementById('date-end');
            const applyBtn = document.getElementById('date-apply-btn');
            const dateLoading = document.getElementById('date-loading');

            // 显示加载状态
            dateLoading.classList.remove('hidden');
            dateStart.disabled = true;
            dateEnd.disabled = true;
            applyBtn.disabled = true;

            try {
                // 尝试从API加载数据（支持日期范围）
                const response = await fetch(`/api/data?start_date=${startDate}&end_date=${endDate}`);

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                if (data.success && data.data) {
                    // 更新全局数据
                    window.REPORT_DATA = data.data;

                    // 重新渲染页面
                    renderOverview(data.data);
                    renderKeywords(data.data);
                    renderGitHubWeekly(data.data);

                    // 更新统计信息
                    const dbStats = data.data.db_stats || {};
                    document.getElementById('total-items').textContent = formatNumber(dbStats.total_count || data.data.total_items || 0);
                    document.getElementById('total-sources').textContent =
                        dbStats.sources_count || (data.data.sources ? Object.keys(data.data.sources).length : 0);
                    showToast(`✅ 已加载 ${startDate} 至 ${endDate} 的数据`, 'success');
                } else {
                    throw new Error(data.message || '数据加载失败');
                }
            } catch (error) {
                console.error('加载日期范围数据失败:', error);

                // 如果API请求失败，检查是否是当前日期（默认当日）
                const today = new Date().toISOString().split('T')[0];

                if (startDate === today && endDate === today) {
                    // 如果是默认的当日，使用当前数据
                    showToast('📊 显示当前数据', 'info');
                } else {
                    // 如果是其他日期范围，显示错误
                    showToast(`❌ 无法加载该日期范围的数据: ${error.message}`, 'error');
                }
            } finally {
                // 隐藏加载状态
                dateLoading.classList.add('hidden');
                dateStart.disabled = false;
                dateEnd.disabled = false;
                applyBtn.disabled = false;
            }
        }

        // 显示提示消息
        function showToast(message, type = 'info') {
            // 创建提示元素
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 20px;
                border-radius: 8px;
                background: ${type === 'success' ? '#43e97b' : type === 'error' ? '#ff6b6b' : '#4facfe'};
                color: white;
                font-weight: 500;
                z-index: 10000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                animation: slideIn 0.3s ease;
            `;

            document.body.appendChild(toast);

            // 3秒后自动移除
            setTimeout(() => {
                toast.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        // 添加动画样式
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        // 渲染GitHub本周增长
        function renderGitHubWeekly(data) {
            const container = document.getElementById('github-weekly-content');
            const sources = data.sources || {};
            // 使用 github_ai 数据源（本周增长数据）
            const githubItems = sources.github_ai || [];

            if (githubItems.length === 0) {
                container.innerHTML = '<div class="empty-state"><div class="emoji">📭</div><div>暂无GitHub本周增长数据</div></div>';
                return;
            }

            // 按热度排序
            const sortedItems = [...githubItems].sort((a, b) => (b.hot_score || 0) - (a.hot_score || 0)).slice(0, 20);

            const html = `
                <div class="github-repo-list">
                    ${sortedItems.map((item, index) => {
                        const extra = item.extra || {};
                        const stars = extra.stars || 0;
                        const forks = extra.forks || 0;
                        const language = extra.language || item.category || 'Unknown';
                        const growth = item.hot_score || 0;

                        return `
                            <div class="github-repo-item">
                                <div class="github-repo-header">
                                    <div class="github-repo-rank">#${index + 1}</div>
                                    <div class="github-repo-info">
                                        <a href="${item.url}" target="_blank" class="github-repo-name">${item.title}</a>
                                        <div class="github-repo-desc">${item.description || '暂无描述'}</div>
                                    </div>
                                </div>
                                <div class="github-repo-stats">
                                    <div class="github-repo-stat growth">
                                        <span>🔥</span>
                                        <span>+${formatNumber(growth)} 本周增长</span>
                                    </div>
                                    <div class="github-repo-stat stars">
                                        <span>⭐</span>
                                        <span>${formatNumber(stars)} Stars</span>
                                    </div>
                                    <div class="github-repo-stat forks">
                                        <span>🍴</span>
                                        <span>${formatNumber(forks)} Forks</span>
                                    </div>
                                    <div class="github-repo-stat language">
                                        <span>💻</span>
                                        <span>${language}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;

            container.innerHTML = html;
        }

        // 仪表盘筛选状态
        let dashboardFilter = 'all';
        let dashboardSort = 'hot';

        // 仪表盘筛选事件
            document.addEventListener('DOMContentLoaded', function() {
                // 筛选按钮
                document.querySelectorAll('.dashboard-filter').forEach(btn => {
                    btn.addEventListener('click', function() {
                        document.querySelectorAll('.dashboard-filter').forEach(b => {
                            b.classList.remove('active');
                        });
                        this.classList.add('active');
                        dashboardFilter = this.dataset.filter;
                        if (typeof window.REPORT_DATA !== 'undefined' && currentView === 'analysis') {
                            renderAnalysis(window.REPORT_DATA);
                        }
                    });
                });

                // 排序选择
                document.getElementById('dashboard-sort').addEventListener('change', function() {
                    dashboardSort = this.value;
                    if (typeof window.REPORT_DATA !== 'undefined' && currentView === 'analysis') {
                        renderAnalysis(window.REPORT_DATA);
                    }
                });
            });

