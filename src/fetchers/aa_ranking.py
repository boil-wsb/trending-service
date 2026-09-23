"""
AI 模型排名 Fetcher — Artificial Analysis
数据源：https://artificialanalysis.ai/api/v2/language/models/free（x-api-key 认证）
说明：免费社区版配额 100 次/24h（每次全量拉取 = 最多 4 页调用），调用方（server.py）需做内存缓存。
注意：AA 提供 3 个综合指数（综合/代码/智能体），无时间戳，无 open_weight 字段。

限流容错：429 时按 Retry-After 退避重试，仍失败则保留已成功页的数据并标记
partial/rate_limited（不再整体返回 None），由调用方决定回退到上次成功快照。
"""

import logging
import os
import time
from typing import List, Dict, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("trending_service.llm_ranking")  # 与 llm-stats 同层级，写入服务日志文件

_AA_BASE_URL = "https://artificialanalysis.ai/api/v2/language/models/free"
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# ── 限流保护（免费社区版配额 100 次/24h，每次全量拉取 = 最多 4 次调用）────────
_MAX_RETRIES = 2          # 429/5xx 最大重试次数
_MAX_RETRY_WAIT = 30      # 短时限流的单次退避上限（秒），避免请求线程长时间阻塞
_DEFAULT_RETRY_WAIT = 5   # 无 Retry-After 头时的基础退避
# ★ 关键阈值：当 Retry-After 超过此值时，说明配额已彻底耗尽（AA 实测可达 25306s≈7h），
#   此时「重试」毫无意义 —— 只会在配额为 0 的情况下反复白撞。
#   正确做法：立即放弃重试，把 Retry-After 上抛，由 server.py 进入等长的全局冷却 + 快照降级。
_LONG_COOLDOWN_THRESHOLD = 900   # 15 分钟：超过即视为「配额耗尽」而非「瞬时限流」


def _parse_retry_after(resp):
    """原始解析 Retry-After（不封顶），返回 float 或 None"""
    try:
        raw = resp.headers.get('Retry-After') if resp is not None else None
        if raw:
            v = float(str(raw).strip())
            return v if v > 0 else None
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def _extract_ratelimit_meta(resp) -> dict:
    """提取限流相关响应头（AA 实测提供 X-Ratelimit-Limit/Remaining/Reset）

    这些是判断「配额是否耗尽」的权威依据：
    - X-Ratelimit-Remaining: 0  → 配额归零
    - X-Ratelimit-Reset:  Unix 时间戳，配额重置时刻
    """
    meta = {}
    if resp is None:
        return meta
    try:
        h = resp.headers
    except AttributeError:
        return meta
    for src, dst, cast in (
        ('X-Ratelimit-Limit', 'ratelimit_limit', int),
        ('X-Ratelimit-Remaining', 'ratelimit_remaining', int),
        ('X-Ratelimit-Reset', 'ratelimit_reset', int),
        ('Retry-After', 'retry_after', float),
    ):
        raw = h.get(src)
        if raw is None:
            continue
        try:
            meta[dst] = cast(str(raw).strip())
        except (TypeError, ValueError):
            continue
    return meta


def _retry_after_seconds(resp, attempt: int) -> float:
    """短时限流的退避秒数（封顶 _MAX_RETRY_WAIT）

    仅用于「可重试」的短时限流/5xx。配额耗尽（Retry-After 超阈值）不走此路径。
    """
    v = _parse_retry_after(resp)
    if v is not None:
        return min(v, _MAX_RETRY_WAIT)
    return min(_DEFAULT_RETRY_WAIT * (2 ** attempt), _MAX_RETRY_WAIT)


def datetime_now_iso() -> str:
    """当前本地时间 ISO 字符串（秒精度），供前端展示数据拉取时间"""
    from datetime import datetime
    return datetime.now().isoformat(timespec='seconds')


# 指数类别 → 响应字段映射（AA 仅提供这 3 个综合指数）
CATEGORY_TO_INDEX = {
    'general': 'artificial_analysis_intelligence_index',
    'code': 'artificial_analysis_coding_index',
    'agentic': 'artificial_analysis_agentic_index',
}
DEFAULT_CATEGORY = 'general'

# 国产大模型厂商（AA model_creator.name 精确匹配，驼峰格式）
# 经全量 59 个 creator 实测核对；含 "AI" 的韩/印/以等厂商不在其中，精确集合最稳。
AA_DOMESTIC_CREATORS = {
    'Alibaba',              # 阿里 Qwen
    'Baidu',                # 百度
    'ByteDance Seed',       # 字节
    'China Mobile',         # 中国移动
    'DeepSeek',             # 深度求索
    'InclusionAI',          # 阶跃星辰
    'Kimi',                 # 月之暗面
    'KwaiKAT',              # 快手
    'LongCat',              # 长猫
    'MiniMax',              # MiniMax
    'Nanbeige',             # 商汤
    'OpenBMB',              # 面壁智能
    'StepFun',              # 阶跃
    'Tencent',              # 腾讯
    'Xiaomi',               # 小米
    'Z AI',                 # 智谱 GLM
}


def _get_api_key() -> Optional[str]:
    """读取 API Key：优先环境变量 AA_API_KEY，其次 config.yaml aa_ranking.api_key"""
    key = os.environ.get('AA_API_KEY')
    if key:
        return key.strip()
    try:
        from src.config import get as get_config
        key = get_config('aa_ranking.api_key')
        return key.strip() if isinstance(key, str) and key.strip() else None
    except Exception:
        return None


def _is_domestic(creator: str) -> bool:
    """根据 model_creator.name 判断是否国产大模型（精确集合匹配）"""
    return creator in AA_DOMESTIC_CREATORS


def _fetch_all_models(api_key: str, max_pages: int = 4) -> tuple:
    """拉取全量模型列表（AA 分页 page_size=200，跟随 has_more，最多 max_pages 页）

    容错策略（免费配额 100 次/24h，429 是常态）：
    - **配额耗尽短路**：若 429 的 Retry-After 超过 _LONG_COOLDOWN_THRESHOLD，
      说明额度已彻底用尽（实测可达 25306s≈7h）。此时**立即放弃、不再重试**，
      把 Retry-After / X-Ratelimit-* 上抛给调用方进入等长的全局冷却。
      旧实现「封顶 30s 后重试」在配额为 0 时纯属白撞。
    - **短时限流**：Retry-After 较小时按退避重试（最多 _MAX_RETRIES 次）。
    - **保住已成功页**：单页最终失败时保留已拿到的数据，不再整体丢弃。

    Returns:
        (all_models, partial, meta)
        - all_models: 已成功获取的模型列表
        - partial: True 表示结果不完整
        - meta: 限流元信息 dict，可能含 retry_after / ratelimit_limit /
                ratelimit_remaining / ratelimit_reset / rate_limited
    """
    all_models: List[dict] = []
    page = 1
    headers = dict(_HEADERS, **{'x-api-key': api_key})
    meta: Dict = {}

    while True:
        # 单页拉取 + 429/5xx 退避重试
        data = None
        last_err = ''
        for attempt in range(_MAX_RETRIES + 1):
            try:
                r = requests.get(f"{_AA_BASE_URL}?page={page}", headers=headers, timeout=20)
                if r.status_code == 429:
                    rl = _extract_ratelimit_meta(r)
                    raw_wait = _parse_retry_after(r)
                    # ★ 配额耗尽：不做无意义重试，直接短路上抛限流信息
                    if raw_wait is not None and raw_wait > _LONG_COOLDOWN_THRESHOLD:
                        meta.update(rl)
                        meta['rate_limited'] = True
                        meta.setdefault('retry_after', raw_wait)
                        logger.warning(
                            f"AA 第{page}页 429 且 Retry-After={raw_wait:.0f}s "
                            f"（>{_LONG_COOLDOWN_THRESHOLD}s），判定为配额耗尽，"
                            f"放弃重试；remaining={rl.get('ratelimit_remaining')} "
                            f"reset={rl.get('ratelimit_reset')}"
                        )
                        return all_models, True, meta
                    wait = _retry_after_seconds(r, attempt)
                    last_err = f"status=429 wait={wait:.0f}s"
                    logger.warning(f"AA 第{page}页限流(429)，{wait:.0f}s 后重试 "
                                   f"({attempt + 1}/{_MAX_RETRIES + 1})")
                    if attempt >= _MAX_RETRIES:
                        meta.update(rl)
                        meta['rate_limited'] = True
                        break
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                resp = getattr(e, 'response', None)
                status = getattr(resp, 'status_code', None)
                last_err = f"status={status}" if status else ''
                # 4xx（非 429）属确定性错误，重试无意义；5xx/网络异常可重试
                retriable = status is None or status >= 500
                logger.warning(f"AA 第{page}页拉取失败 {last_err} err={str(e)[:120]}")
                if not retriable or attempt >= _MAX_RETRIES:
                    break
                time.sleep(min(2 ** attempt, 5))

        if data is None:
            # 该页彻底失败：保住已拿到的数据，标记 partial
            logger.warning(f"AA 第{page}页最终失败（{last_err}），"
                           f"已获取 {len(all_models)} 条模型，返回部分结果")
            return all_models, True, meta

        all_models.extend(data.get('data') or [])
        pagination = data.get('pagination') or {}
        if not pagination.get('has_more'):
            break
        page += 1
        if page > max_pages:  # 安全上限，与「最多 4 页」的说明保持一致
            logger.warning(f"AA 分页已达安全上限 {max_pages} 页，停止拉取")
            break

    return all_models, False, meta


def fetch_aa_rankings(limit: int = 15, category: str = DEFAULT_CATEGORY) -> Dict:
    """获取 AI 模型排名（Artificial Analysis 综合指数降序）

    Args:
        limit: 返回条数（默认 15）
        category: 指数类别（general 综合 / code 代码 / agentic 智能体）

    Returns:
        {
            'models': [
                {'rank': 1, 'name': 'Claude Fable 5.1', 'org_name': 'Anthropic',
                 'score': 53.40, 'is_domestic': False, 'open_weight': False},
                ...
            ],
            'category': 'general',
            'ranked_at': None,        # AA 无时间戳
            'unavailable_reason': None,  # 无 Key / 拉取失败时的提示文案
        }
    """
    result = {
        'models': [],
        'category': category,
        'ranked_at': None,
        'unavailable_reason': None,
        'partial': False,        # 结果是否不完整（分页中途失败/限流）
        'rate_limited': False,   # 是否遭遇 429（前端据此提示"数据可能偏旧"）
        'fetched_at': None,      # 本次数据拉取时间（ISO），供前端展示"更新于"
    }

    index_field = CATEGORY_TO_INDEX.get(category)
    # 非法类别回退到综合
    if index_field is None:
        category = DEFAULT_CATEGORY
        index_field = CATEGORY_TO_INDEX[category]
        result['category'] = category

    api_key = _get_api_key()
    if not api_key:
        logger.warning("AA API Key 未配置（aa_ranking.api_key / AA_API_KEY）")
        result['unavailable_reason'] = '未配置 API Key'
        return result

    if not HAS_REQUESTS:
        logger.error("requests 库未安装，无法调用 AA API")
        result['unavailable_reason'] = 'requests 库未安装'
        return result

    # 只取第一页（约 200 条候选，排序后取 TOP 条数足够；调用次数 4→1，大幅省配额）
    raw_models, partial, meta = _fetch_all_models(api_key, max_pages=1)
    # 限流元信息上抛（供 server.py 决定全局冷却时长）
    for k in ('retry_after', 'ratelimit_limit', 'ratelimit_remaining', 'ratelimit_reset'):
        if meta.get(k) is not None:
            result[k] = meta[k]
    if meta.get('rate_limited'):
        result['rate_limited'] = True

    if partial and not raw_models:
        # 区分「配额耗尽」与「一般拉取失败」，让前端提示更准确
        result['unavailable_reason'] = (
            'API 配额已耗尽（限流）' if meta.get('rate_limited') else 'API 拉取失败'
        )
        result['partial'] = True
        if meta.get('rate_limited'):
            result['rate_limited'] = True
        return result

    # 过滤有指数值的模型，按指数降序排序
    scored = []
    for m in raw_models:
        evals = m.get('evaluations') or {}
        raw_score = evals.get(index_field)
        if raw_score is None:
            continue
        try:
            score = round(float(raw_score), 2)
        except (TypeError, ValueError):
            continue
        creator_obj = m.get('model_creator') or {}
        creator = creator_obj.get('name') if isinstance(creator_obj, dict) else ''
        raw_name = m.get('name') or m.get('slug') or ''
        scored.append({
            'id': m.get('slug') or m.get('id') or m.get('name'),  # slug 稳定唯一，供前端排名变动基线
            'name': raw_name,
            '_base': (raw_name.split(' (')[0] or raw_name).strip(),
            'org_name': creator,
            'score': score,
            'is_domestic': _is_domestic(creator),
            'open_weight': False,
        })

    if not scored:
        # 分页中途失败时（partial=True）虽已有原始数据但可能全部缺该指数字段，
        # 必须把 partial / rate_limited 一并上抛，否则调用方会把「部分失败」误判为「完整成功但无数据」
        result['unavailable_reason'] = (
            'API 配额已耗尽（限流）' if meta.get('rate_limited')
            else ('API 拉取不完整，且无匹配数据' if partial else 'API 返回空数据')
        )
        result['partial'] = bool(partial)
        if partial:
            result['rate_limited'] = True
        return result

    # 按分数降序
    scored.sort(key=lambda x: x['score'], reverse=True)

    # 去重：同一模型系列（主名，含配置变体如 Max/Xhigh）只保留最高分一个
    # 主名 = "Claude Fable 5.1 (Max Effort...)" 拆分取 "Claude Fable 5.1"
    seen = set()
    deduped = []
    for m in scored:
        base = m['_base'] if '_base' in m else None
        if base in seen:
            continue
        seen.add(base)
        deduped.append(m)
    deduped = deduped[:limit]

    models = []
    for i, m in enumerate(deduped):
        # 显示名用主名（去版本变体后缀），保持清爽
        entry = dict(m)
        if '_base' in entry:
            entry['name'] = entry.pop('_base')
        models.append({
            'rank': i + 1,
            **entry,
        })

    result['models'] = models
    result['partial'] = partial
    # 不要覆盖 meta 带来的 rate_limited：部分成功也可能由限流造成
    result['rate_limited'] = bool(result.get('rate_limited') or partial)
    result['fetched_at'] = datetime_now_iso()
    logger.info(f"AA 排名解析完成 category={category} total={len(models)} "
                f"domestic={sum(1 for x in models if x['is_domestic'])} partial={partial} "
                f"remaining={result.get('ratelimit_remaining')}")
    return result
