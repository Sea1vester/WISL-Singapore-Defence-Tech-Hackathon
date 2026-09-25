import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


def build_environment(root, overrides, separator=os.pathsep):
    env = dict(overrides)
    defaults = {
        'DATABASE_PATH': str(root / 'data/demo-console.db'),
        'RAW_UPLOAD_DIR': str(root / 'data/demo-uploads'),
        'REPORTS_DIR': str(root / 'data/demo-reports'),
        'VISUALS_DIR': str(root / 'data/demo-visuals'),
        'TILE_CACHE_DIR': str(root / 'data/tiles'),
        'OLLAMA_BASE_URL': 'http://127.0.0.1:11434',
        'OLLAMA_MODEL': 'qwen2.5:7b-instruct',
        'AUTO_START_LOCAL_MODEL': 'true',
        'INGEST_API_KEYS': 'dev-key-12345',
        'API_PORT': '8010',
    }
    for key, value in defaults.items():
        if not env.get(key):
            env[key] = value
    env.update({
        'LOCAL_DEMO_WORKER': 'true',
        'INGEST_MODEL_ENRICHMENT': 'false',
        'API_HOST': '127.0.0.1',
        'REPLAY_STATIC_DIR': str(root / 'sdth-replay/public'),
        'DEMO_STATIC_DIR': str(root / 'sdth-demo'),
    })
    paths = [str(root / 'sdth-telemetry/platform-api'), str(root / 'sdth-telemetry')]
    if env.get('PYTHONPATH'):
        paths.append(env['PYTHONPATH'])
    env['PYTHONPATH'] = separator.join(paths)
    return env


def ensure_cesium(root):
    vendor = root / 'sdth-replay/public/cesium'
    if all((vendor / name).exists() for name in ('Cesium.js', 'Workers', 'Assets', 'Widgets/widgets.css')):
        return
    node = shutil.which('node')
    if not node:
        raise FileNotFoundError('Install Node.js 22+ to download Cesium once, or copy the complete sdth-replay/public/cesium directory from a working installation.')
    subprocess.run([node, str(root / 'sdth-replay/scripts/fetch-cesium.cjs')], check=True)


def open_when_ready(url):
    opener = build_opener(ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open(url + '/health', timeout=1):
                webbrowser.open_new_tab(url + '/demo/')
                return
        except (URLError, OSError):
            time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description='Start the WISL API, local worker and replay console on Windows, macOS or Linux.')
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env = build_environment(root, os.environ)
    try:
        port = int(env['API_PORT'])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        parser.error('API_PORT must be an integer between 1 and 65535.')
    try:
        ensure_cesium(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Cesium setup failed: {exc}\nCheck the download connection or copy a complete local Cesium build before retrying.\n')
    os.environ.update(env)
    sys.path[:0] = [str(root / 'sdth-telemetry/platform-api'), str(root / 'sdth-telemetry')]
    os.chdir(root / 'sdth-telemetry/platform-api')
    import uvicorn
    url = f'http://127.0.0.1:{port}'
    print(f'WISL console: {url}/demo/', flush=True)
    print('Local demo only. Enter your configured API key in Session. Stop with Ctrl+C.', flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, reload=False)


if __name__ == '__main__':
    main()
