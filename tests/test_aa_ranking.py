"""AA 排名 fetcher 单元测试（2026-09-28 重构：全量多页拉取 + 三类别共享 raw）

踩坑提醒（历史经验，勿删）：
- mock 响应必须实现 raise_for_status()，否则被测代码把它当网络异常吞掉
- evaluations 字段名须与 CATEGORY_TO_INDEX 对齐（无 _math_index）
- fetch_aa_raw / fetch_aa_rankings 不收 api_key，测试需 patch aa._get_api_key
- mock 睡眠的正确目标：mock.patch.object(aa.time, 'sleep', ...)
"""
import pytest
from unittest import mock

from src.fetchers import aa_ranking as aa


# ── fixtures / 工具 ──────────────────────────────────────────────

class FakeResp:
    """最小 mock 响应：必须实现 raise_for_status()"""

    def __init__(self, payload=None, status=200, headers=None):
        self._payload = payload or {}
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            e = Exception(f'{self.status_code} Error')
            e.response = self
            raise e

    def json(self):
        return self._payload


def page_payload(models, page_no, has_more):
    return {
        'data': models,
        'pagination': {'page': page_no, 'page_size': 200,
                       'total_pages': 4, 'has_more': has_more},
    }


def model(name, creator='DeepSeek', intel=None, code=None, agentic=None):
    ev = {}
    if intel is not None:
        ev['artificial_analysis_intelligence_index'] = intel
    if code is not None:
        ev['artificial_analysis_coding_index'] = code
    if agentic is not None:
        ev['artificial_analysis_agentic_index'] = agentic
    return {
        'name': name,
        'slug': name.lower().replace(' ', '-'),
        'model_creator': {'name': creator},
        'evaluations': ev,
    }


@pytest.fixture
def no_sleep():
    with mock.patch.object(aa.time, 'sleep', lambda s: None):
        yield


@pytest.fixture
def fake_key():
    with mock.patch.object(aa, '_get_api_key', lambda: 'test-key'):
        yield


# ── _fetch_all_models：多页聚合 / 截断 / 配额耗尽 ─────────────────

def test_fetch_all_models_follows_has_more(no_sleep, fake_key):
    """跟随 has_more 拉满 3 页，pages_fetched 正确记账"""
    p1 = page_payload([model('A1', 'OpenAI', intel=50)], 1, True)
    p2 = page_payload([model('B1', 'DeepSeek', intel=40)], 2, True)
    p3 = page_payload([model('C1', 'Google', intel=30)], 3, False)
    with mock.patch.object(aa.requests, 'get', side_effect=[
        FakeResp(p1), FakeResp(p2), FakeResp(p3),
    ]) as mg:
        models, partial, meta = aa._fetch_all_models('k')
    assert mg.call_count == 3
    assert len(models) == 3
    assert partial is False
    assert meta['pages_fetched'] == 3
    assert meta.get('truncated') is None
    # 请求的页码应依次递增
    called_pages = [c.args[0] for c in mg.call_args_list]
    assert called_pages == [f'{aa._AA_BASE_URL}?page=1',
                            f'{aa._AA_BASE_URL}?page=2',
                            f'{aa._AA_BASE_URL}?page=3']


def test_fetch_all_models_truncation_marks_meta(no_sleep, fake_key):
    """达到 max_pages 上限仍有 has_more → truncated=True（AA 分页增长场景）"""
    p1 = page_payload([model('A1', 'OpenAI', intel=50)], 1, True)
    p2 = page_payload([model('B1', 'DeepSeek', intel=40)], 2, True)
    with mock.patch.object(aa.requests, 'get', side_effect=[FakeResp(p1), FakeResp(p2)]):
        models, partial, meta = aa._fetch_all_models('k', max_pages=2)
    assert meta['truncated'] is True
    assert meta['pages_fetched'] == 2
    assert partial is False  # 网络层没有失败，截断≠partial
    assert len(models) == 2


def test_fetch_all_models_quota_exhausted_short_circuit(no_sleep, fake_key):
    """Retry-After > 900s → 判定配额耗尽，立即放弃且不重试"""
    r429 = FakeResp(status=429, headers={'Retry-After': '20000',
                                         'X-Ratelimit-Remaining': '0'})
    with mock.patch.object(aa.requests, 'get', side_effect=[r429]) as mg:
        models, partial, meta = aa._fetch_all_models('k')
    assert mg.call_count == 1  # 短路，无重试
    assert models == []
    assert partial is True
    assert meta['rate_limited'] is True
    assert meta['retry_after'] == 20000.0
    assert meta['pages_fetched'] == 0


def test_fetch_all_models_partial_keeps_successful_pages(no_sleep, fake_key):
    """第 2 页彻底失败 → 保住第 1 页数据，partial=True"""
    p1 = page_payload([model('A1', 'OpenAI', intel=50)], 1, True)
    fail = FakeResp(status=500)
    with mock.patch.object(aa.requests, 'get', side_effect=[
        FakeResp(p1), fail, fail, fail,   # 第 2 页重试 2 次共 3 次全失败
    ]):
        models, partial, meta = aa._fetch_all_models('k')
    assert len(models) == 1
    assert partial is True
    assert meta['pages_fetched'] == 1


# ── rank_models_from_raw：纯函数排名 ─────────────────────────────

RAW = [
    # 同主名变体：V4.1 Flash 两个变体，去重后应保留最高分 39.5
    model('DeepSeek V4.1 Flash (Reasoning, Max Effort)', 'DeepSeek', intel=39.5),
    model('DeepSeek V4.1 Flash (Non-Reasoning)', 'DeepSeek', intel=24.7),
    # 低分老模型（第 1 页之外的真实数据形态）
    model('DeepSeek V3.1 Terminus (Reasoning)', 'DeepSeek', intel=14.8),
    model('Claude Opus 5.5 (Adaptive Reasoning, Max Effort)', 'Anthropic', intel=57.6),
    model('MiMo-V2.6-Pro', 'Xiaomi', intel=46.3),
    # 无综合指数分的模型应被过滤
    model('Some Embedding Model', 'OpenAI', intel=None),
]


def test_rank_general_dedupe_and_order():
    r = aa.rank_models_from_raw(RAW, limit=10, category='general')
    names = [(m['rank'], m['name'], m['score']) for m in r['models']]
    # 降序 + 同主名去重取最高分变体
    assert names[0] == (1, 'Claude Opus 5.5', 57.6)
    assert names[1] == (2, 'MiMo-V2.6-Pro', 46.3)
    assert names[2] == (3, 'DeepSeek V4.1 Flash', 39.5)   # 24.7 变体被去重
    assert names[3] == (4, 'DeepSeek V3.1 Terminus', 14.8)
    assert len(names) == 4
    # 国产标记
    dom = {m['name']: m['is_domestic'] for m in r['models']}
    assert dom['DeepSeek V4.1 Flash'] is True
    assert dom['MiMo-V2.6-Pro'] is True
    assert dom['Claude Opus 5.5'] is False


def test_rank_code_category_uses_coding_index():
    """同一份 raw 派生 code 类别：应按 coding_index 排序（三类别共享的关键）"""
    raw = RAW + [
        model('DeepSeek V4 Flash 0731 (Reasoning, Max Effort)', 'DeepSeek',
              intel=34.3, code=69.1),
        model('Claude Opus 5.5 (Adaptive Reasoning, Max Effort)', 'Anthropic',
              intel=57.6, code=71.0),
    ]
    r = aa.rank_models_from_raw(raw, limit=10, category='code')
    names = [(m['name'], m['score']) for m in r['models']]
    assert names[0] == ('Claude Opus 5.5', 71.0)
    assert names[1] == ('DeepSeek V4 Flash 0731', 69.1)
    # 只有综合分的 MiMo 不应出现在 code 榜
    assert all('MiMo' not in n for n, _ in names)


def test_rank_empty_scored_inherits_flags_and_reason():
    """raw 整体失败（partial+限流）→ unavailable_reason 与标志位必须上抛"""
    raw_meta = {'partial': True, 'rate_limited': True,
                'unavailable_reason': 'API 配额已耗尽（限流）',
                'retry_after': 25306.0, 'fetched_at': None}
    r = aa.rank_models_from_raw([], limit=15, category='general', raw_meta=raw_meta)
    assert r['models'] == []
    assert r['partial'] is True
    assert r['rate_limited'] is True
    assert r['unavailable_reason'] == 'API 配额已耗尽（限流）'
    assert r['retry_after'] == 25306.0


def test_rank_invalid_category_falls_back_to_general():
    r = aa.rank_models_from_raw(RAW, limit=10, category='not-exist')
    assert r['category'] == 'general'


def test_rank_limit_clamp():
    raw = [model(f'M{i}', 'OpenAI', intel=100 - i) for i in range(50)]
    r = aa.rank_models_from_raw(raw, limit=30, category='general')
    assert len(r['models']) == 30
    assert r['models'][-1]['rank'] == 30


# ── fetch_aa_raw：整合（mock HTTP）───────────────────────────────

def test_fetch_aa_raw_aggregates_and_sets_meta(no_sleep, fake_key):
    p1 = page_payload([model('A1', 'OpenAI', intel=50)], 1, True)
    p2 = page_payload([model('B1', 'DeepSeek', intel=40)], 2, False)
    with mock.patch.object(aa.requests, 'get', side_effect=[FakeResp(p1), FakeResp(p2)]):
        raw = aa.fetch_aa_raw()
    assert len(raw['models']) == 2
    assert raw['partial'] is False
    assert raw['pages_fetched'] == 2
    assert raw['fetched_at'] is not None
    assert raw['unavailable_reason'] is None

    # 全链路：raw → 单类别排名（DeepSeek 应出现在 general 榜）
    r = aa.rank_models_from_raw(raw['models'], limit=15, category='general', raw_meta=raw)
    assert any(m['name'] == 'B1' and m['is_domestic'] for m in r['models'])


def test_fetch_aa_raw_no_key():
    with mock.patch.object(aa, '_get_api_key', lambda: None):
        raw = aa.fetch_aa_raw()
    assert raw['models'] == []
    assert raw['unavailable_reason'] == '未配置 API Key'


def test_compat_wrapper_still_works(no_sleep, fake_key):
    """fetch_aa_rankings 兼容入口：返回结构与旧版一致"""
    p1 = page_payload([model('A1', 'OpenAI', intel=50)], 1, False)
    with mock.patch.object(aa.requests, 'get', side_effect=[FakeResp(p1)]):
        r = aa.fetch_aa_rankings(limit=5, category='general')
    assert r['category'] == 'general'
    assert r['models'][0]['rank'] == 1
    assert r['models'][0]['name'] == 'A1'
    assert 'partial' in r and 'rate_limited' in r and 'fetched_at' in r
