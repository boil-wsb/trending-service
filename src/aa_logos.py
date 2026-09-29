# -*- coding: utf-8 -*-
"""AA 模型公司 logo 代理（前端榜单图表 logo 显示）。

背景：
- AA API 响应本身没有 logo 字段（model_creator 仅 id/name），但 AA 官网
  使用固定规律的静态 logo：https://artificialanalysis.ai/img/logos/{slug}.{ext}
- 实测（2026-09-28，aa_raw_all.json 全量 58 家 creator + HEAD 探测）：
  slug 规律 = name 小写去空格（40/58 命中），其余按 LOGO_ALIASES 手工映射
  （再命中 14 家），最终覆盖 54/58；China Mobile / Korea Telecom / Naver /
  Thinking Machines 无公开 logo，走 404 → 前端文字降级。
- 后缀不统一（svg 为主，少量 png/jpg），按 svg→png→jpg 顺序探测。
- 服务端代理而非前端直连：同源加载无跨域/防盗链问题，且 AA 站点故障时
  磁盘缓存仍可用。

缓存策略：
- 命中文件永久使用（品牌 logo 几乎不变），负缓存 24h（给新 logo 补录机会）。
- SVG 若无 width/height 属性则注入 96x96（drawImage 需要固有尺寸）。
"""

import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

from src.utils import get_logger

logger = get_logger('aa_logos')

_BASE_URL = 'https://artificialanalysis.ai/img/logos/'
_EXTS = ('svg', 'png', 'jpg')
_CONTENT_TYPES = {
    'svg': 'image/svg+xml',
    'png': 'image/png',
    'jpg': 'image/jpeg',
}
_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)
_TIMEOUT = 10
_MAX_SIZE = 512 * 1024          # logo 不会超过 512KB，防御异常响应
_NEG_TTL = 24 * 3600            # 负缓存：24h 后允许重新探测

# 手工别名：slug 规律（name 小写去空格）命不中的公司（2026-09-28 实测）
LOGO_ALIASES = {
    'AI21 Labs': 'ai21',
    'Allen Institute for AI': 'ai2',
    'Amazon': 'aws',
    'Arcee AI': 'arcee',
    'ByteDance Seed': 'bytedance',
    'Inception': 'inceptionlabs',
    'Institute of Foundation Models': 'ifm',
    'LG AI Research': 'lg',
    'Motif Technologies': 'motif',
    'Nex AGI': 'nex',
    'Prime Intellect': 'prime-intellect',
    'Reka AI': 'reka',
    'Swiss AI Initiative': 'swiss-ai-initiative',
    'TII UAE': 'tii',
}

# 磁盘缓存目录：项目根/data/cache/aa_logos
_CACHE_DIR = Path(__file__).resolve().parent.parent / 'data' / 'cache' / 'aa_logos'

_slug_cache = {}        # creator name -> slug
_missing_cache = {}     # slug -> marker mtime（内存负缓存，与磁盘 marker 双保险）
_fetch_lock = threading.Lock()


def slugify_creator(name: str) -> str:
    """creator name → AA logo slug：别名优先，否则小写去非字母数字。"""
    if not name:
        return ''
    if name in LOGO_ALIASES:
        return LOGO_ALIASES[name]
    if name not in _slug_cache:
        _slug_cache[name] = re.sub(r'[^a-z0-9]', '', name.lower())
    return _slug_cache[name]


def _inject_svg_size(data: bytes) -> bytes:
    """SVG 无 width/height 时注入 96x96，保证 canvas drawImage 有固有尺寸。"""
    try:
        head = data[:600].decode('utf-8', errors='ignore')
    except Exception:  # noqa: BLE001
        return data
    m = re.search(r'<svg\b[^>]*>', head)
    if not m:
        return data
    tag = m.group(0)
    if re.search(r'\bwidth=', tag) and re.search(r'\bheight=', tag):
        return data
    patched = tag[:-1] + ' width="96" height="96">' if tag.endswith('>') else tag
    return data.replace(tag.encode('utf-8'), patched.encode('utf-8'), 1)


def _fetch_remote(slug: str, ext: str):
    url = f'{_BASE_URL}{slug}.{ext}'
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return None
            data = r.read(_MAX_SIZE + 1)
        if not data or len(data) > _MAX_SIZE:
            return None
    except urllib.error.HTTPError:
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f'logo 拉取异常 slug={slug}.{ext}: {type(e).__name__}: {e}')
        return None
    if ext == 'svg':
        data = _inject_svg_size(data)
    return data


def _mark_missing(slug: str):
    _missing_cache[slug] = time.time()
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        marker = _CACHE_DIR / f'{slug}.missing'
        marker.touch()
    except OSError:
        pass


def get_logo(creator_name: str):
    """获取公司 logo 二进制。

    返回 (bytes, content_type)；无 logo（负缓存/全部 404）返回 None。
    正缓存文件永久有效（品牌 logo 几乎不变）；负缓存 24h。
    """
    slug = slugify_creator(creator_name)
    if not slug or not re.fullmatch(r'[a-z0-9-]{1,64}', slug):
        return None

    # 内存负缓存
    miss_at = _missing_cache.get(slug)
    if miss_at and time.time() - miss_at < _NEG_TTL:
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 磁盘正缓存（永久）
    for ext in _EXTS:
        p = _CACHE_DIR / f'{slug}.{ext}'
        if p.is_file():
            try:
                return p.read_bytes(), _CONTENT_TYPES[ext]
            except OSError:
                break

    # 磁盘负缓存
    marker = _CACHE_DIR / f'{slug}.missing'
    try:
        if marker.is_file() and time.time() - marker.stat().st_mtime < _NEG_TTL:
            _missing_cache[slug] = marker.stat().st_mtime
            return None
    except OSError:
        pass

    # 加锁拉取（避免并发重复打 AA 静态站）
    with _fetch_lock:
        # 双检：等锁期间可能已被其他线程写入
        for ext in _EXTS:
            p = _CACHE_DIR / f'{slug}.{ext}'
            if p.is_file():
                try:
                    return p.read_bytes(), _CONTENT_TYPES[ext]
                except OSError:
                    break
        for ext in _EXTS:
            data = _fetch_remote(slug, ext)
            if data is not None:
                try:
                    (_CACHE_DIR / f'{slug}.{ext}').write_bytes(data)
                except OSError as e:
                    logger.warning(f'logo 缓存写入失败 slug={slug}.{ext}: {e}')
                _missing_cache.pop(slug, None)
                logger.info(f'logo 已缓存: {slug}.{ext} ({len(data)}B) creator={creator_name!r}')
                return data, _CONTENT_TYPES[ext]
    _mark_missing(slug)
    return None


# ── 刷新后全量预热 ──────────────────────────────────────────────────────
_WARMUP_GAP = 0.15        # 仅对发生网络拉取的公司之间加节流间隔（静态 CDN 礼貌）
_warmup_lock = threading.Lock()
_warming = False


def _on_disk(name: str) -> bool:
    """该公司的 logo 是否已在磁盘缓存（避免对已缓存公司做无谓 sleep）"""
    slug = slugify_creator(name)
    return any((_CACHE_DIR / f'{slug}.{ext}').is_file() for ext in _EXTS)


def warmup_logos(raw_models: list):
    """把 raw 模型涉及的全部公司 logo 预下载落盘（幂等、并发去重、节流）。

    由 aa_refresh_raw_models() 在每次成功刷新后异步触发：
    生产首屏即全本地命中，不依赖用户首次访问触发；AA 站故障不影响已缓存 logo。
    返回 {'total', 'hit', 'miss', 'skipped'}；已有预热在跑时 skipped=True。
    """
    global _warming
    creators = []
    seen = set()
    for m in raw_models or []:
        c = m.get('model_creator') or {}
        name = c.get('name') if isinstance(c, dict) else None
        if name and name not in seen:
            seen.add(name)
            creators.append(name)
    if not creators:
        return {'total': 0, 'hit': 0, 'miss': 0, 'skipped': False}

    # 并发去重：预热在跑则直接跳过（本轮磁盘缓存稍后自然补齐）
    if not _warmup_lock.acquire(blocking=False):
        return {'total': len(creators), 'hit': 0, 'miss': 0, 'skipped': True}
    _warming = True
    hit = miss = 0
    try:
        for name in creators:
            fresh = not _on_disk(name)
            got = get_logo(name)
            if got:
                hit += 1
            else:
                miss += 1
            if fresh:
                time.sleep(_WARMUP_GAP)
        logger.info(f'logo 预热完成: {hit} 已缓存 / {miss} 无公开 logo / 共 {len(creators)} 家')
        return {'total': len(creators), 'hit': hit, 'miss': miss, 'skipped': False}
    except Exception as e:  # noqa: BLE001
        logger.warning(f'logo 预热异常: {type(e).__name__}: {e}')
        return {'total': len(creators), 'hit': hit, 'miss': miss, 'skipped': False}
    finally:
        _warming = False
        _warmup_lock.release()


def warmup_logos_async(raw_models: list):
    """后台线程执行预热（daemon，不阻塞调用方；线程内吞掉全部异常）"""
    def _run():
        try:
            warmup_logos(raw_models)
        except Exception as e:  # noqa: BLE001
            logger.warning(f'logo 预热线程异常: {type(e).__name__}: {e}')

    t = threading.Thread(target=_run, name='aa-logo-warmup', daemon=True)
    t.start()
    return t
