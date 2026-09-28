# 一次性诊断：AA 全量 4 页 -> 真实综合指数 TOP30 + DeepSeek 全家排名
# 保存原始 JSON 到 debug_out/aa_raw_all.json，后续分析可离线复用（不再耗配额）
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r'D:\MYDATA\Include\trending-service')
import src.config  # noqa: F401  先加载 .env（AA_API_KEY）
from src.fetchers.aa_ranking import _HEADERS, _get_api_key, CATEGORY_TO_INDEX
import requests

IDX = CATEGORY_TO_INDEX['general']
key = _get_api_key()
assert key, 'no api key'

all_models = []
for page in range(1, 5):
    r = requests.get(f"https://artificialanalysis.ai/api/v2/language/models/free?page={page}",
                     headers=dict(_HEADERS, **{'x-api-key': key}), timeout=20)
    assert r.status_code == 200, f'page {page} status {r.status_code}'
    d = r.json()
    models = d.get('data') or []
    all_models.extend(models)
    print(f'page={page} got={len(models)} pagination={d.get("pagination")}')

with open(r'D:\MYDATA\Include\trending-service\debug_out\aa_raw_all.json', 'w', encoding='utf-8') as f:
    json.dump(all_models, f, ensure_ascii=False)
print('total models:', len(all_models), '(saved to debug_out/aa_raw_all.json)')

# 模拟 fetcher 逻辑：有综合指数分 -> 按分降序 -> 同主名去重取最高分
scored = []
for m in all_models:
    s = (m.get('evaluations') or {}).get(IDX)
    if s is None:
        continue
    try:
        s = round(float(s), 2)
    except (TypeError, ValueError):
        continue
    name = m.get('name') or m.get('slug') or ''
    creator = (m.get('model_creator') or {}).get('name') or ''
    scored.append({'name': name, 'base': (name.split(' (')[0] or name).strip(),
                   'creator': creator, 'score': s})
print('models with intelligence index:', len(scored))
scored.sort(key=lambda x: -x['score'])

seen, deduped = set(), []
for m in scored:
    if m['base'] in seen:
        continue
    seen.add(m['base'])
    deduped.append(m)
print('after dedupe:', len(deduped))

print('\n===== 真实综合指数 TOP30（全量 4 页） =====')
for i, m in enumerate(deduped[:30]):
    dom = '*' if m['creator'] in {
        'Alibaba','Baidu','ByteDance Seed','China Mobile','DeepSeek','InclusionAI',
        'Kimi','KwaiKAT','LongCat','MiniMax','Nanbeige','OpenBMB','StepFun','Tencent',
        'Xiaomi','Z AI'} else ' '
    print(f'{dom} #{i+1:2d} {m["score"]:5.1f}  {m["name"]}  ({m["creator"]})')

print('\n===== DeepSeek 全家真实名次 =====')
for i, m in enumerate(deduped):
    if 'deepseek' in m['base'].lower():
        print(f'#{i+1:3d} {m["score"]:5.1f}  {m["name"]}')

# 对比：只拉第 1 页时的 TOP30 有多少是错的
page1_names = set()
print('\n===== 当前线上 TOP30 里「真实排名 > 30」的条目 =====')
for i, m in enumerate(deduped):
    if i < 30:
        page1_names.add(m['base'])
for i, m in enumerate(deduped):
    if i >= 30 and m['base'] in page1_names:
        pass
# 直接算：page1-only top30
seen1, deduped1 = set(), []
for m in scored:
    if m['base'] in seen1:
        continue
    seen1.add(m['base'])
    deduped1.append(m)
# scored 已全量排序，无法直接还原 page1 子集，改为标注全量视角下的错位条目
fake = [m for i, m in enumerate(deduped) if i < 30]
real_gt30_in_current = []
# 当前线上 TOP30（来自 DB 快照 general:30）
import sqlite3
con = sqlite3.connect(r'D:\MYDATA\Include\trending-service\data\db\trending.db')
row = con.execute('select models_json from aa_ranking_snapshot where category="general" and "limit"=30').fetchone()
cur = json.loads(row[0])
rank_of = {m['base']: i + 1 for i, m in enumerate(deduped)}
print('当前线上榜 vs 真实排名：')
for m in cur:
    base = (m['name'].split(' (')[0] or m['name']).strip()
    rr = rank_of.get(base, '?')
    mark = '  <-- 应为更高/不在真实TOP30' if isinstance(rr, int) and rr > 30 else ''
    print(f'  线上#{m["rank"]:2d} {m["score"]:5.1f} {m["name"]:38s} 真实#{rr}{mark}')
print('\n真实 TOP30 中被第 1 页截断漏掉的：')
for i, m in enumerate(deduped[:30]):
    if m['base'] not in { (x['name'].split(' (')[0] or x['name']).strip() for x in cur }:
        print(f'  漏掉: #{i+1:2d} {m["score"]:5.1f}  {m["name"]}  ({m["creator"]})')
