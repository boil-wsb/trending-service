/**
 * Toast 通知管理器 - 借鉴 stock-dashboard Toast.tsx + toastContext.ts 设计
 *
 * 单例容器 + 命令式 API，替代 core.js 中每次新建 DOM 的 showToast 实现。
 * 优势：
 * 1. 统一容器，避免每次调用新建 DOM + 内联样式 + 重复注入 <style>
 * 2. 支持手动关闭、图标、退出动画
 * 3. CSS 类替代内联样式，跟随主题
 *
 * 用法：
 *   Toast.success('已加载');
 *   Toast.error('请求失败');
 *   Toast.info('提示');
 *   Toast.warning('警告');
 */
const Toast = (function () {
    'use strict';

    let container = null;
    let idCounter = 0;

    const ICONS = {
        success: '✓',
        error: '✕',
        info: 'ℹ',
        warning: '⚠',
    };

    // 确保容器存在（惰性创建）
    function ensureContainer() {
        if (container && document.body.contains(container)) return container;
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    // 创建单条 toast
    function show(type, message, duration) {
        duration = duration || 3000;
        const el = document.createElement('div');
        el.className = `toast toast--${type}`;
        el.innerHTML = `<span class="toast__icon">${ICONS[type] || ICONS.info}</span>` +
            `<span class="toast__msg"></span>` +
            `<button class="toast__close" aria-label="关闭">×</button>`;
        el.querySelector('.toast__msg').textContent = message;  // 防 XSS

        const toastId = ++idCounter;
        const close = function () {
            if (!el.parentNode) return;
            el.classList.add('toast--exit');
            setTimeout(() => { if (el.parentNode) el.remove(); }, 200);
        };
        el.querySelector('.toast__close').onclick = close;
        ensureContainer().appendChild(el);

        // 入场动画（下一帧添加 enter 类触发 transition）
        requestAnimationFrame(() => el.classList.add('toast--enter'));

        const timer = setTimeout(close, duration);
        // hover 时暂停自动关闭
        el.addEventListener('mouseenter', () => clearTimeout(timer));
        return toastId;
    }

    return {
        success: (m, d) => show('success', m, d),
        error: (m, d) => show('error', m, d),
        info: (m, d) => show('info', m, d),
        warning: (m, d) => show('warning', m, d),
    };
})();
