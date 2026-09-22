"""确认 TrendingService 是否真的加载了新代码（去重逻辑）。

原理：
  /api/data 在本次改动后新增了 `raw_total_items` 字段。该字段缺失
  就说明运行进程加载的仍是改动前的 server.py。

用法（重启服务后运行）：
    venv\\Scripts\\python.exe scripts\\check_dedupe_status.py
"""
import json
import socket
import subprocess
import sys
import time

PORT = 8888
RANGE = ('2026-09-15', '2026-09-20')


def http_get(port, path, timeout=120):
    """原始 socket 请求，绕过系统代理（代理对 localhost 会返回 502）"""
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    try:
        s.sendall((
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Accept: application/json\r\nConnection: close\r\n\r\n"
        ).encode())
        chunks = []
        while True:
            data = s.recv(65536)
            if not data:
                break
            chunks.append(data)
        raw = b"".join(chunks)
        head, _, body = raw.partition(b"\r\n\r\n")
        return head.split(b"\r\n")[0].decode(), body
    finally:
        s.close()


def listener_pid(port):
    """返回监听指定端口的进程 PID"""
    out = subprocess.run(['netstat', '-ano', '-p', 'TCP'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f':{port}' in line and 'LISTENING' in line:
            try:
                return int(line.split()[-1])
            except ValueError:
                pass
    return None


def proc_start_time(pid):
    """通过 PowerShell 取进程启动时间（用文件传递，避免编码问题）"""
    ps = (
        f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($p) {{ $p.StartTime.ToString('yyyy-MM-dd HH:mm:ss') }}"
    )
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except Exception:
        return None


def main():
    pid = listener_pid(PORT)
    started = proc_start_time(pid) if pid else None

    print('=' * 66)
    print(f'端口 :{PORT}   PID={pid}   进程启动={started or "(未知)"}')
    print('=' * 66)

    try:
        status, body = http_get(PORT, f'/api/data?start_date={RANGE[0]}&end_date={RANGE[1]}')
    except Exception as e:
        print(f'无法连接 :{PORT} -> {type(e).__name__}: {e}')
        return 1

    print(f'STATUS: {status}')
    payload = json.loads(body)
    if not payload.get('success'):
        print('接口返回失败:', payload)
        return 1

    d = payload['data']
    raw = d.get('raw_total_items')

    hn = d['sources'].get('hackernews', [])
    targets = [i for i in hn if 'e-ink' in (i.get('title') or '')]

    if raw is None:
        print()
        print('>>> 仍是【旧代码】—— 重启未生效')
        print('    raw_total_items 字段缺失。')
        print(f'    total_items={d["total_items"]} / HN={len(hn)} / e-ink 帖={len(targets)}')
        print()
        print('  排查方向：')
        print('    1) 提权窗口是否点了「是」？服务是否真的重启（看进程启动时间是否更新）？')
        print('    2) 若启动时间没变，说明 NSSM 未真正重启该进程。')
        return 2

    print()
    print('>>> 已加载【新代码】，跨日去重生效')
    print(f'    raw_total_items = {raw}（去重前）')
    print(f'    total_items     = {d["total_items"]}（去重后）')
    print(f'    减少            = {raw - d["total_items"]} 条')
    print(f'    HN = {len(hn)} 条 / e-ink 帖 = {len(targets)} 条（期望 1）')

    for t in targets:
        if t.get('daily_trend'):
            print(f'      峰值 {t["hot_score"]} | 在榜 {t.get("seen_days")} 天 | '
                  f'{t.get("first_seen_date")} -> {t.get("last_seen_date")}')

    if len(targets) == 1:
        print()
        print('去重验证通过 ✅')
        return 0

    print()
    print(f'⚠️ 去重未完全生效：e-ink 帖仍有 {len(targets)} 条')
    return 3


if __name__ == '__main__':
    sys.exit(main())
