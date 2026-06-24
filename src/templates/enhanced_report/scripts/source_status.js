        // ==================== 数据源状态管理 ====================
        
        // 数据源状态缓存
        let sourceStatusCache = {};
        let isRefreshing = false;
        
        // 获取数据源状态
        async function fetchSourceStatus() {
            try {
                const response = await fetch(`${API_BASE_URL}/api/status`);
                const result = await response.json();
                
                if (result.success && result.data) {
                    sourceStatusCache = result.data.sources || {};
                    renderSourceStatus();
                }
            } catch (error) {
                console.error('获取数据源状态失败:', error);
                // 使用报告数据作为备选
                generateStatusFromReport();
            }
        }
        
        // 从报告数据生成状态
        function generateStatusFromReport() {
            const data = window.REPORT_DATA;
            if (!data || !data.sources) return;
            
            for (const [source, items] of Object.entries(data.sources)) {
                sourceStatusCache[source] = {
                    success: items.length > 0,
                    item_count: items.length,
                    last_update: data.generated_at,
                    error_message: null,
                    retry_count: 0,
                    status: items.length > 0 ? 'success' : 'unknown'
                };
            }
            
            renderSourceStatus();
        }
        
        // 渲染数据源状态
        function renderSourceStatus() {
            const grid = document.getElementById('source-status-grid');
            const statusBar = document.getElementById('source-status-bar');
            if (!grid || !statusBar) return;

            // 从报告数据获取实际数据情况
            const reportData = window.REPORT_DATA || {};
            const reportSources = reportData.sources || {};

            const statusIcons = {
                'success': '✅',
                'failed': '❌',
                'pending': '⏳',
                'unknown': '❓'
            };

            const statusClasses = {
                'success': 'success',
                'failed': 'failed',
                'pending': 'pending',
                'unknown': 'unknown'
            };

            let html = '';
            let hasNeedsRefresh = false;

            for (const [source, config] of Object.entries(sourceConfig)) {
                const status = sourceStatusCache[source] || { status: 'unknown', item_count: 0 };

                // 获取报告中的实际数据条数
                const reportItems = reportSources[source] || [];
                const hasData = reportItems.length > 0;

                // 检查是否需要刷新 - 只有当状态失败或没有数据时才需要
                const needsRefresh = status.status === 'failed' || !hasData;

                if (needsRefresh) {
                    hasNeedsRefresh = true;
                } else {
                    // 有数据的数据源不显示在状态栏中
                    continue;
                }

                const icon = statusIcons[status.status] || '❓';
                const statusClass = statusClasses[status.status] || 'unknown';

                // 格式化最后更新时间
                let timeText = '';
                if (status.last_update) {
                    const date = new Date(status.last_update);
                    const now = new Date();
                    const diff = (now - date) / 1000; // 秒

                    if (diff < 60) {
                        timeText = '刚刚';
                    } else if (diff < 3600) {
                        timeText = `${Math.floor(diff / 60)}分钟前`;
                    } else if (diff < 86400) {
                        timeText = `${Math.floor(diff / 3600)}小时前`;
                    } else {
                        timeText = date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                    }
                } else {
                    timeText = '未知';
                }

                // 错误信息提示
                const errorText = status.error_message ?
                    `<span class="source-status-error" title="${status.error_message}">${status.error_message}</span>` : '';

                // 刷新按钮
                const refreshBtn = `<button class="refresh-btn" onclick="refreshSource('${source}')" data-source="${source}">刷新</button>`;

                html += `
                    <div class="source-status-item ${statusClass}">
                        <span class="source-status-icon">${config.icon}</span>
                        <span class="source-status-name">${config.name}</span>
                        <span class="source-status-time">${timeText}</span>
                        ${errorText}
                        ${refreshBtn}
                    </div>
                `;
            }

            grid.innerHTML = html;

            // 只在有需要刷新的数据源时显示状态栏
            statusBar.style.display = hasNeedsRefresh ? 'block' : 'none';
        }
        
        // 刷新单个数据源
        async function refreshSource(source) {
            if (isRefreshing) return;
            
            const btn = document.querySelector(`button[data-source="${source}"]`);
            if (btn) {
                btn.disabled = true;
                btn.textContent = '刷新中...';
                btn.classList.add('refreshing');
            }
            
            isRefreshing = true;
            
            try {
                const sourceName = sourceConfig[source]?.name || source;
                showNotification(`正在刷新 ${sourceName}...`, 'info');
                
                console.log(`刷新数据源: ${source}, URL: ${API_BASE_URL}/api/refresh/${source}`);
                
                const response = await fetch(`${API_BASE_URL}/api/refresh/${source}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                console.log(`响应状态: ${response.status}`);
                
                const result = await response.json();
                console.log('响应结果:', result);
                
                if (result.success) {
                    showNotification(`✅ ${result.message || '刷新成功'}`, 'success');
                    // 更新状态
                    await fetchSourceStatus();
                    // 刷新页面数据
                    location.reload();
                } else {
                    showNotification(`❌ ${result.message || result.error || '刷新失败'}`, 'error');
                }
            } catch (error) {
                console.error('刷新数据源失败:', error);
                showNotification(`❌ 刷新失败: ${error.message || error}`, 'error');
            } finally {
                isRefreshing = false;
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '刷新';
                    btn.classList.remove('refreshing');
                }
            }
        }
        
        // 刷新所有数据源
        async function refreshAllSources() {
            if (isRefreshing) return;
            
            const btn = document.getElementById('refresh-all-btn');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '刷新中...';
            }
            
            isRefreshing = true;
            
            try {
                showNotification('正在刷新所有数据源...', 'info');
                
                const response = await fetch(`${API_BASE_URL}/api/refresh-all`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showNotification('✅ ' + result.message, 'success');
                    // 等待几秒后刷新页面
                    setTimeout(() => location.reload(), 3000);
                } else {
                    showNotification('❌ ' + result.message, 'error');
                }
            } catch (error) {
                console.error('刷新所有数据源失败:', error);
                showNotification(`❌ 刷新失败: ${error.message}`, 'error');
            } finally {
                isRefreshing = false;
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '刷新全部';
                }
            }
        }
        
        // 显示通知
        function showNotification(message, type = 'info') {
            // 移除现有通知
            const existing = document.querySelector('.notification');
            if (existing) {
                existing.remove();
            }
            
            // 创建新通知
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;
            document.body.appendChild(notification);
            
            // 3秒后自动移除
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 3000);
        }
        
        // 渲染所有 Chart.js 图表
        function renderAllCharts() {
            if (typeof Chart === 'undefined') {
                console.log('Chart.js 未加载，等待中...');
                setTimeout(renderAllCharts, 100);
                return;
            }

            if (!window.REPORT_DATA) {
                console.log('报告数据未准备好');
                return;
            }

            console.log('开始渲染图表...');
            const trends = window.REPORT_DATA.trends || {};

            if (trends.summary && trends.summary.total_trend && trends.summary.total_trend.length > 0) {
                console.log('渲染总趋势图', trends.summary.total_trend);
                updateTrendSummary(trends.summary);
                renderTotalTrendChart(trends.summary);
            } else {
                console.log('总趋势图数据不足', trends.summary);
            }

            if (trends.source_trends && Object.keys(trends.source_trends).length > 0) {
                console.log('渲染数据源趋势图');
                renderSourceTrendChart(trends.source_trends);
            }

            if (trends.keyword_trends && Object.keys(trends.keyword_trends).length > 0) {
                console.log('渲染关键词趋势图');
                renderKeywordTrendChart(trends.keyword_trends);
            }
        }

