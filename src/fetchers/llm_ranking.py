"""
AI 模型排名 Fetcher — llm-stats.com
数据源：https://api.zeroeval.com/stats/v1/rankings（Bearer API Key 认证）
说明：免费社区版配额 250 次/天，调用方（server.py）需做 1 小时内存缓存。
"""

import logging
import os
from typing import List, Dict, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("trending_service.llm_ranking")  # 挂到服务 logger 层级，写入服务日志文件

_BASE_URL = "https://api.zeroeval.com/stats/v1/rankings"
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# 国产大模型厂商关键词（匹配 organization / model_id / model_name，小写比较）
# 注意：避免过泛词干（如 spark 会误伤 Meta Muse Spark，nemo 会误伤 NVIDIA Nemotron）
DOMESTIC_KEYWORDS = (
    'deepseek', 'qwen', 'alibaba', 'tongyi', 'zhipu', 'glm', 'chatglm',
    'moonshotai', 'moonshot', 'kimi', 'minimax', 'abab', 'baichuan',
    'stepfun', '01-ai', '01ai', 'iflytek', 'sparkdesk', 'xinghuo',
    'tencent', 'hunyuan', 'baidu', 'ernie', 'wenxin',
    'bytedance', 'doubao', 'skylark', 'sensenova', 'sensetime',
    'shanghai-ai-lab', 'internlm', 'huawei', 'pangu', 'xiaomi', 'mimo',
)

# 默认排名类别（/rankings 端点必填 category；general 为综合类别）
DEFAULT_CATEGORY = 'general'


def _get_api_key() -> Optional[str]:
    """读取 API Key：优先环境变量 LLM_STATS_API_KEY，其次 config.yaml llm_stats.api_key"""
    key = os.environ.get('LLM_STATS_API_KEY')
    if key:
        return key.strip()
    try:
        from src.config import get as get_config
        key = get_config('llm_stats.api_key')
        return key.strip() if isinstance(key, str) and key.strip() else None
    except Exception:
        return None


def _is_domestic(org: str, model_id: str, model_name: str) -> bool:
    """根据组织/模型名关键词判断是否国产大模型"""
    text = f"{org} {model_id} {model_name}".lower()
    return any(kw in text for kw in DOMESTIC_KEYWORDS)


def _fetch_rankings(api_key: str, category: str, limit: int, retries: int = 2) -> Optional[tuple]:
    """请求 /rankings 端点，返回 (原始 models 列表, ranked_at)；失败返回 None"""
    url = f"{_BASE_URL}?category={category}&limit={limit}"
    headers = dict(_HEADERS, Authorization=f"Bearer {api_key}")
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            models = data.get('models') or []
            logger.info(f"llm-stats rankings 拉取成功 category={category} count={len(models)} "
                        f"ranked_at={data.get('ranked_at', '')} attempt={attempt}")
            return models, data.get('ranked_at')
        except Exception as e:
            resp_info = ''
            resp = getattr(e, 'response', None)
            if resp is not None:
                resp_info = f" status={resp.status_code}"
            logger.warning(f"llm-stats rankings 第{attempt}次拉取失败{resp_info} err={str(e)[:120]}")
    return None


def fetch_llm_rankings(limit: int = 15, category: str = DEFAULT_CATEGORY) -> Dict:
    """获取 AI 模型排名（TrueSkill 保守评分排序）

    Args:
        limit: 返回条数（默认 15）
        category: 排名类别（默认 general 综合）

    Returns:
        {
            'models': [
                {'rank': 1, 'id': 'gpt-6-astra', 'name': 'GPT-6 Astra',
                 'org_id': 'openai', 'org_name': 'openai',
                 'score': 59.71,           # conservative_rating（TrueSkill 保守评分，值域一致）
                 'open_weight': False,
                 'is_domestic': False},
                ...
            ],
            'category': 'general',
            'ranked_at': '2026-09-22T03:56:52Z',
            'unavailable_reason': None,   # 无 Key / 拉取失败时的提示文案
        }
    """
    result = {
        'models': [],
        'category': category,
        'ranked_at': None,
        'unavailable_reason': None,
    }

    api_key = _get_api_key()
    if not api_key:
        logger.warning("llm-stats API Key 未配置（llm_stats.api_key / LLM_STATS_API_KEY）")
        result['unavailable_reason'] = '未配置 API Key'
        return result

    if not HAS_REQUESTS:
        logger.error("requests 库未安装，无法调用 llm-stats API")
        result['unavailable_reason'] = 'requests 库未安装'
        return result

    raw = _fetch_rankings(api_key, category, limit)
    if raw is None:
        result['unavailable_reason'] = 'API 拉取失败'
        return result
    raw_models, ranked_at = raw
    if not raw_models:
        result['unavailable_reason'] = 'API 返回空数据'
        return result

    models = []
    for i, m in enumerate(raw_models):
        model_id = str(m.get('model_id') or m.get('id') or '')
        model_name = str(m.get('model_name') or m.get('name') or model_id)
        org = str(m.get('organization') or '')
        # organization 可能是字符串 id 或 dict {"id","name"}
        if isinstance(m.get('organization'), dict):
            org = str(m['organization'].get('id') or m['organization'].get('name') or '')
        org_name = str(m.get('organization_name') or org)
        # 图表取值：conservative_rating 值域一致（~25-60），score 各基准值域混乱
        score = m.get('conservative_rating')
        if score is None:
            score = m.get('score')
        try:
            score = round(float(score), 2)
        except (TypeError, ValueError):
            score = None
        rank = m.get('rank') or (i + 1)
        models.append({
            'rank': int(rank) if rank is not None else None,
            'id': model_id,
            'name': model_name,
            'org_id': org,
            'org_name': org_name,
            'score': score,
            'open_weight': bool(m.get('open_weight', False)),
            'is_domestic': _is_domestic(org, model_id, model_name),
        })

    result['models'] = models
    result['ranked_at'] = ranked_at
    logger.info(f"llm-stats 排名解析完成 total={len(models)} "
                f"domestic={sum(1 for x in models if x['is_domestic'])}")
    return result
