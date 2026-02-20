#!/usr/bin/env python3
"""
启动脚本：在后台并行启动三个开发服务并记录 PID 与日志。

服务：
- Django 开发服务器: `uv run uvicorn netops.asgi:application --port 8000 --reload`
- FastAPI (uvicorn)    : `uvicorn main:app --host 0.0.0.0 --port 8001`
- 前端开发服务器    : `pnpm run dev`（回退到 `npm run dev` 当 pnpm 不可用）

用法:
  python start_services.py start
  python start_services.py stop
  python start_services.py status
"""
import os
import sys
import json
import time
import signal
import shutil
import argparse
from subprocess import Popen
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
PID_FILE = ROOT / "service_pids.json"

SERVICES = {}

def detect_commands():
    # Django
    SERVICES['django'] = {
        # 'cmd': ['uv', 'run', 'gunicorn', 'netops.wsgi:application', '--bind', '0.0.0.0:8000', '--reload'],
        'cmd': ['uv', 'run', 'uvicorn', 'netops.asgi:application', '--port', '8000', '--reload'],
        'cwd': str(ROOT),
        'log': str(LOG_DIR / 'django.log')
    }

    # FastAPI / uvicorn
    if shutil.which('uvicorn'):
        fastapi_cmd = ['uv', 'run', 'main.py']
    else:
        # fallback to running the provided runner script
        fastapi_cmd = ['uv', 'run', str(ROOT / 'main.py')]

    SERVICES['fastapi'] = {
        'cmd': fastapi_cmd,
        'cwd': str(ROOT),
        'log': str(LOG_DIR / 'fastapi.log')
    }

    # Frontend
    if shutil.which('pnpm'):
        frontend_cmd = ['pnpm', 'run', 'dev']
    elif shutil.which('npm'):
        frontend_cmd = ['npm', 'run', 'dev']
    else:
        frontend_cmd = None

    SERVICES['frontend'] = {
        'cmd': frontend_cmd,
        'cwd': str(ROOT / 'frontend'),
        'log': str(LOG_DIR / 'frontend.log')
    }


def ensure_dirs():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def start_services():
    ensure_dirs()
    detect_commands()

    procs = {}
    for name, info in SERVICES.items():
        cmd = info['cmd']
        if not cmd:
            print(f"跳过 {name}：未检测到可用命令（pnpm/npm/uvicorn 可能缺失）")
            continue

        log_path = Path(info['log'])
        cwd = info['cwd']

        fout = log_path.open('ab')

        print(f"启动 {name}: {' '.join(cmd)} (cwd={cwd}) -> 日志: {log_path}")
        # 使用 setsid 让子进程成为独立进程组，便于统一终止
        proc = Popen(cmd, cwd=cwd, stdout=fout, stderr=fout, preexec_fn=os.setsid)
        procs[name] = {
            'pid': proc.pid,
            'pgid': os.getpgid(proc.pid),
            'log': str(log_path)
        }

    # 写 PID 文件
    with PID_FILE.open('w', encoding='utf-8') as f:
        json.dump({'services': procs, 'started_at': time.time()}, f, indent=2)

    print('\n已启动服务:')
    for n, p in procs.items():
        print(f" - {n}: pid={p['pid']} pgid={p['pgid']} log={p['log']}")


def stop_services():
    if not PID_FILE.exists():
        print('没有找到 PID 文件，无法停止服务')
        return

    with PID_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)

    services = data.get('services', {})
    for name, info in services.items():
        pgid = info.get('pgid')
        pid = info.get('pid')
        try:
            if pgid:
                print(f'向进程组 {pgid} 发送 SIGTERM ({name})')
                os.killpg(pgid, signal.SIGTERM)
            elif pid:
                print(f'向进程 {pid} 发送 SIGTERM ({name})')
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print(f'{name} (pid={pid}) 不存在')
        except Exception as e:
            print(f'停止 {name} 时出错: {e}')

    try:
        PID_FILE.unlink()
    except OSError:
        pass

    print('停止命令已发送，等待进程退出...')


def status():
    if not PID_FILE.exists():
        print('未找到 PID 文件，服务可能未启动')
        return

    with PID_FILE.open('r', encoding='utf-8') as f:
        data = json.load(f)

    services = data.get('services', {})
    for name, info in services.items():
        pid = info.get('pid')
        try:
            os.kill(pid, 0)
            alive = True
        except Exception:
            alive = False
        print(f"{name}: pid={pid} alive={alive} log={info.get('log')}")


def main():
    parser = argparse.ArgumentParser(description='Start/stop dev services in background')
    parser.add_argument('action', choices=['start', 'stop', 'status'], help='要执行的操作')
    args = parser.parse_args()

    if args.action == 'start':
        if os.path.exists(PID_FILE):
            print('检测到已存在的 PID 文件，先查看状态或运行 stop 后再 start')
            status()
            sys.exit(1)
        start_services()
    elif args.action == 'stop':
        stop_services()
    elif args.action == 'status':
        status()


if __name__ == '__main__':
    main()
