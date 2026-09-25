import importlib.util
from pathlib import Path, PureWindowsPath


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'demo-console.py'


def launcher():
    spec = importlib.util.spec_from_file_location('demo_launcher', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_defaults_use_absolute_paths_and_semicolon_pythonpath():
    module = launcher()
    root = PureWindowsPath('C:/Work with spaces/SDTH')
    env = module.build_environment(root, {'PYTHONPATH': 'C:\\existing'}, separator=';')
    assert env['DATABASE_PATH'] == str(root / 'data/demo-console.db')
    assert env['REPLAY_STATIC_DIR'] == str(root / 'sdth-replay/public')
    assert env['PYTHONPATH'] == ';'.join([str(root / 'sdth-telemetry/platform-api'), str(root / 'sdth-telemetry'), 'C:\\existing'])
    assert env['LOCAL_DEMO_WORKER'] == 'true'
    assert env['INGEST_MODEL_ENRICHMENT'] == 'false'
    assert env['API_HOST'] == '127.0.0.1'


def test_launcher_preserves_explicit_settings_without_mutating_the_input(tmp_path):
    original = {'API_PORT': '8099', 'DATABASE_PATH': 'custom.db', 'INGEST_API_KEYS': 'test-key', 'WARM_LOCAL_MODEL': 'false', 'AUTO_START_LOCAL_MODEL': 'false'}
    env = launcher().build_environment(tmp_path, original)
    assert all(env[key] == value for key, value in original.items())
    assert 'PYTHONPATH' not in original
    assert env['RAW_UPLOAD_DIR'] == str(tmp_path / 'data/demo-uploads')


def test_empty_overrides_get_the_same_defaults_as_the_shell_launcher(tmp_path):
    env = launcher().build_environment(tmp_path, {'API_PORT': '', 'OLLAMA_MODEL': ''})
    assert env['API_PORT'] == '8010'
    assert env['OLLAMA_MODEL'] == 'qwen2.5:7b-instruct'


def test_complete_local_cesium_needs_no_node_or_network(tmp_path, monkeypatch):
    module = launcher()
    vendor = tmp_path / 'sdth-replay/public/cesium'
    for name in ['Cesium.js', 'Workers/worker.js', 'Assets/asset.json', 'Widgets/widgets.css']:
        target = vendor / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture', encoding='utf-8')
    monkeypatch.setattr(module.shutil, 'which', lambda name: None)
    module.ensure_cesium(tmp_path)


def test_incomplete_cesium_runs_the_installer_with_space_safe_arguments(tmp_path, monkeypatch):
    module = launcher()
    calls = []
    monkeypatch.setattr(module.shutil, 'which', lambda name: 'C:\\Program Files\\nodejs\\node.exe')
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: calls.append((args, kwargs)))
    module.ensure_cesium(tmp_path / 'space in path')
    assert calls[0][0][0] == ['C:\\Program Files\\nodejs\\node.exe', str(tmp_path / 'space in path/sdth-replay/scripts/fetch-cesium.cjs')]
    assert calls[0][1]['check'] is True
