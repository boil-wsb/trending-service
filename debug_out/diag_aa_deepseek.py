# 一次性诊断脚本：检查 AA 原始返回中 DeepSeek 的存在性与指数分
# 只读诊断，不改任何代码。每次页拉取消耗 1 次 AA 真实配额。
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r'D:\MYDATA\Include\trending-service')
import src.config  # noqa: F401  先加载 .env（AA_API_KEY）
from src.fetchers.aa_ranking import _fetch_all_models, _get_api_key, CATEGORY_TO_INDEX

key = _get_api_key()
print('api_key present:', bool(key))
if not key:
    sys.exit(1)

pages_to_check = [int(x) for x in sys.argv[1:]] or [1]
for page in pages_to_check:
    # _fetch_all_models 从 page=1 开始拉，这里直接用 requests 模拟指定页更省事
    import requests
    from src.fetchers.aa_ranking import _HEADERS
    r = requests.get(f"https://artificialanalysis.ai/api/v2/language/models/free?page={page}",
                     headers=dict(_HEADERS, **{'x-api-key': key}), timeout=20)
    print(f'--- page={page} status={r.status_code}')
    if r.status_code != 200:
        print('headers:', dict(r.headers))
        continue
    data = r.json()
    models = data.get('data') or []
    pagination = data.get('pagination') or {}
    print('models_in_page:', len(models), 'pagination:', pagination)

    idx_field = CATEGORY_TO_INDEX['general']
    scored = 0
    for m in models:
        ev = m.get('evaluations') or {}
        if ev.get(idx_field) is not None:
            scored += 1
    print(f'have intelligence_index: {scored}/{len(models)}')

    # DeepSeek 相关条目
    ds = [m for m in models if 'deepseek' in str(m.get('name','')).lower()
          or 'deepseek' in str((m.get('model_creator') or {}).get('name','')).lower()
          or 'deepseek' in str(m.get('slug','')).lower()]
    print('deepseek entries in page:', len(ds))
    for m in ds:
        ev = m.get('evaluations') or {}
        print('  -', m.get('name'), '| creator=', (m.get('model_creator') or {}).get('name'),
              '| intel=', ev.get(idx_field), '| code=', ev.get('artificial_analysis_coding_index'),
              '| agentic=', ev.get('artificial_analysis_agentic_index'))

    # 全部 creator 分布（看第一页覆盖了哪些厂商）
    creators = {}
    for m in models:
        c = (m.get('model_creator') or {}).get('name') or '?'
        creators[c] = creators.get(c, 0) + 1
    print('creators:', sorted(creators.items(), key=lambda x: -x[1]))

    # 计算综合指数排名（模拟 fetcher 的去重逻辑：同主名取最高分）
    base_seen, deduped = set(), []
    for m in sorted(models, key=lambda x: -((x.get('evaluations') or {}).get(idx_field) or -1)):
        s = (m.get('evaluations') or {}).get(idx_field)
        if s is None:
            continue
        name = m.get('name') or m.get('slug') or ''
        b = name.split(' (')[0].strip()
        if b in base_seen:
            continue
        base_seen.add(b)
        deduped.append((b, s, (m.get('model_creator') or {}).get('name')))
    print('deduped scored models in page1:', len(deduped))
    for i, (b, s, c) in enumerate(deduped):
        if 'deepseek' in b.lower():
            print(f'>>> DeepSeek best rank in page1: #{i+1}  {b}  score={s}  ({c})')
    print('--- around DeepSeek best:')
    for i, (b, s, c) in enumerate(deduped):
        if 'DeepSeek V3.1 Terminus' in b:
            for j in range(max(0, i-3), min(len(deduped), i+4)):
                mark = '>>' if j == i else '  '
                print(f'{mark} #{j+1} {deduped[j][0]}  {deduped[j][1]}  ({deduped[j][2]})')
            break
    print('--- top30 cutoff (rank30):', deduped[29] if len(deduped) >= 30 else None)
