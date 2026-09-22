"""
AI 模型排名 Fetcher — Artificial Analysis
数据源：https://artificialanalysis.ai/api/v2/language/models/free（x-api-key 认证）
说明：免费社区版配额 100 次/24h（每次全量拉取 = 4 页调用），调用方（server.py）需做内存缓存。
注意：AA 提供 3 个综合指数（综合/代码/智能体），无时间戳，无 open_weight 字段。
"""

import logging
import os
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


def _fetch_all_models(api_key: str) -> Optional[List[dict]]:
    """拉取全量模型列表（AA 分页 page_size=200，循环直到 has_more=False，最多 4 页）
    返回原始 data 列表；任一页失败则返回 None。"""
    all_models: List[dict] = []
    page = 1
    headers = dict(_HEADERS, **{'x-api-key': api_key})
    while True:
        try:
            r = requests.get(f"{_AA_BASE_URL}?page={page}", headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            resp = getattr(e, 'response', None)
            resp_info = f" status={resp.status_code}" if resp is not None else ''
            logger.warning(f"AA 第{page}页拉取失败{resp_info} err={str(e)[:120]}")
            return None
        all_models.extend(data.get('data') or [])
        pagination = data.get('pagination') or {}
        if not pagination.get('has_more'):
            break
        page += 1
        if page > 5:  # 安全上限
            break
    return all_models


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

    raw_models = _fetch_all_models(api_key)
    if raw_models is None:
        result['unavailable_reason'] = 'API 拉取失败'
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
        result['unavailable_reason'] = 'API 返回空数据'
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
    logger.info(f"AA 排名解析完成 category={category} total={len(models)} "
                f"domestic={sum(1 for x in models if x['is_domestic'])}")
    return result