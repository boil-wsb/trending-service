# 一次性端到端验证：8899 临时实例跑新 AA 排名链路
# 验证点：全量 4 页拉取 → 三类别共享 raw（只耗 4 次配额）→ DeepSeek V4.1 Flash 回到综合榜
# 用后即弃，不影响 8888 生产实例
import sys, io, time, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'D:\MYDATA\Include\trending-service')

BASE = 'http://localhost:8899'

def get(path, timeout=240):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())

from src.server import TrendingServer
from src.scheduler import TrendingTaskScheduler
srv = TrendingServer(port=8899)
srv.start(blocking=False)
# 构造调度器即触发 _setup_tasks → 启动预热线程（与 main.py 生产行为一致）；
# 不调用 sched.start()，避免 cron 轮询在验证窗口触发其它任务
sched = TrendingTaskScheduler()
print('server starting on 8899 (with AA preheat) ...')

try:
    # 等服务就绪（含金叉缓存预热，约 20s）
    ready = False
    for _ in range(60):
        time.sleep(2)
        try:
            get('/api/aa/quota', timeout=5)
            ready = True
            break
        except Exception:
            continue
    assert ready, 'server not ready in 120s'
    print('server ready.\n')

    # 1) 综合（首刷：应消耗 4 次配额）
    d = get('/api/aa/rankings?category=general&limit=30')['data']
    used1 = d.get('quota_used')
    names = [m['name'] for m in d['models']]
    ds = [(m['rank'], m['name'], m['score']) for m in d['models'] if 'deepseek' in m['name'].lower()]
    print(f'[general]  quota_used={used1}  fetched_at={d.get("fetched_at")}  '
          f'partial={d.get("partial")}  truncated={d.get("truncated")}')
    print(f'[general]  DeepSeek: {ds if ds else "无"}')
    assert ds and ds[0][0] <= 30, 'DeepSeek 应回到综合 TOP30！'
    print(f'[general]  top5: {names[:5]}')

    # 2) 代码（raw 缓存命中：配额不再增长）
    d2 = get('/api/aa/rankings?category=code&limit=30')['data']
    used2 = d2.get('quota_used')
    ds2 = [(m['rank'], m['name'], m['score']) for m in d2['models'] if 'deepseek' in m['name'].lower()]
    print(f'[code]     quota_used={used2}（应与 general 相同=raw 共享生效）  DeepSeek: {ds2[:2] if ds2 else "无"}')
    assert used2 == used1, 'raw 缓存未生效，类别切换不应再耗配额！'

    # 3) 智能体（同上）
    d3 = get('/api/aa/rankings?category=agentic&limit=30')['data']
    used3 = d3.get('quota_used')
    ds3 = [(m['rank'], m['name'], m['score']) for m in d3['models'] if 'deepseek' in m['name'].lower()]
    print(f'[agentic]  quota_used={used3}  DeepSeek: {ds3[:2] if ds3 else "无"}')
    assert used3 == used1

    # 4) 快照落库状态
    q = get('/api/aa/quota')['data']
    print('[quota]    snapshots:', json.dumps(q['snapshots'], ensure_ascii=False))
    print(f'[quota]    本地计数 used={q["quota_used"]}/{q["quota_max"]}（4 页全量 = 4 次）')
    print('\n=== E2E ALL PASS ===')
finally:
    srv.stop()
    print('temp server stopped.')
