"""Storage relocation and discovery contracts through real CLI/API boundaries."""
from contextlib import chdir
import json
from pathlib import Path
import shutil
import time
from unittest.mock import patch
from urllib.parse import quote

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app as cli
from magic_geo.config import create_config, dump_config_yaml
from magic_geo.config_store import ConfigStore
from magic_geo.paths import RuntimePaths
from magic_geo.debug_server import create_app
from magic_geo.web_jobs import JobInputError, JobManager, operation_catalog
from test_debug_server import asgi_call, _make_cache


@pytest.fixture
def storage(tmp_path, monkeypatch):
    for name in tuple(__import__('os').environ):
        if name.startswith('MAGIC_GEO_') and name != 'MAGIC_GEO_NATIVE_LIBRARY':
            monkeypatch.delenv(name)
    project = tmp_path / 'source'
    project.mkdir()
    roots = {'WORKSPACE': 'work', 'OUTPUT_DIR': 'worlds', 'DEBUG_DIR': 'cache',
             'CONFIG_DIR': 'definitions', 'SAVED_CONFIG_DIR': 'saved', 'STATE_DIR': 'state',
             'REPORTS_DIR': 'reports', 'EXPORTS_DIR': 'exports', 'CALIBRATION_DIR': 'calibration'}
    for setting, name in roots.items():
        monkeypatch.setenv(f'MAGIC_GEO_{setting}', str(tmp_path / name))
    monkeypatch.setenv('MAGIC_GEO_PROJECT_ROOT', str(project))
    return project, RuntimePaths.resolve()


def request(app, method, url, body=None):
    status, _, content = asgi_call(app, method, url, json_body=body)
    return status, json.loads(content)


def close(app):
    app.state.job_manager.close()
    app.state.cache_manager.close()


def test_repository_defaults_and_subdirectory_discovery(tmp_path):
    (tmp_path / 'src/magic_geo').mkdir(parents=True)
    (tmp_path / 'pyproject.toml').touch()
    with chdir(tmp_path / 'src/magic_geo'):
        p = RuntimePaths.resolve(environ={})
    assert p.project == tmp_path
    assert p.workspace == p.output_dir == p.reports_dir == p.exports_dir == tmp_path / 'runs'
    assert p.config_dir == tmp_path / 'configs'
    assert p.saved_config_dir == tmp_path / 'runs/configs'
    assert p.debug_dir == tmp_path / 'runs/debug'
    assert p.state_dir == tmp_path / 'runs/.magic-geo-web'


def test_discovery_excludes_matrices_and_keeps_explicit_errors(storage, monkeypatch):
    root, p = storage
    p.config_dir.mkdir()
    p.saved_config_dir.mkdir()
    (p.config_dir / 'matrix.yaml').write_text('scenarios: []\n')
    (p.config_dir / 'earthlike_seed.yaml').write_text(dump_config_yaml(create_config('smoke')))
    selected = p.saved_config_dir / 'world.yaml'
    selected.write_text(dump_config_yaml(create_config('smoke')))
    (p.config_dir / 'alias.yaml').symlink_to(selected)
    store = ConfigStore(p)
    catalog = store.catalog()
    assert catalog['default'] == str(selected)
    assert len(catalog['configs']) == 2
    assert store.default() == selected
    monkeypatch.setenv('MAGIC_GEO_CONFIG_PATH', str(root / 'missing.yaml'))
    explicit = ConfigStore(RuntimePaths.resolve()).catalog()
    assert 'MAGIC_GEO_CONFIG_PATH' in explicit['error']
    assert explicit['default'] == 'missing.yaml'


def test_external_config_save_preserves_text_and_detects_stale_edits(storage):
    root, p = storage
    app = create_app()
    text = '# exact source\nconfig_version: 2\nrun:\n  seed: 18446744073709551615\n'
    try:
        status, saved = request(app, 'POST', '/api/config/save', {'name': 'world', 'yaml': text})
        assert status == 200
        path = p.saved_config_dir / 'world.yaml'
        assert path.read_text() == text
        status, opened = request(app, 'GET', '/api/config/file?path=' + quote(str(path)))
        assert status == 200 and opened['yaml'] == text
        update = {'name': opened['name'], 'path': opened['path'], 'revision': opened['revision'], 'yaml': text + '# edited\n'}
        status, changed = request(app, 'POST', '/api/config/save', update)
        assert status == 200 and changed['revision'] != opened['revision']
        status, conflict = request(app, 'POST', '/api/config/save', update | {'force': True})
        assert status == 409 and conflict['detail']['code'] == 'config_changed'
        assert path.read_text() == update['yaml']
        assert not (root / 'runs').exists()
        status, _ = request(app, 'GET', '/api/config/file?path=/etc/passwd')
        assert status == 422
        status, info = request(app, 'GET', '/api/status')
        assert info['paths']['state_dir'] == str(p.state_dir)
    finally:
        close(app)


def test_explicit_config_outside_directories_loads_and_saves(storage, monkeypatch, tmp_path):
    root, _ = storage
    source = tmp_path / 'one-file.yaml'
    source.write_text('config_version: 2\n# editable\n')
    monkeypatch.setenv('MAGIC_GEO_CONFIG_PATH', str(source))
    app = create_app()
    try:
        _, catalog = request(app, 'GET', '/api/config/files')
        assert catalog['default'] == str(source)
        _, opened = request(app, 'GET', '/api/config/file?path=' + quote(str(source)))
        status, _ = request(app, 'POST', '/api/config/save', {k: opened[k] for k in ('name', 'path', 'revision', 'yaml')})
        assert status == 200
        assert source.read_text() == 'config_version: 2\n# editable\n'
    finally:
        close(app)


def test_external_job_defaults_and_download_snapshots(storage):
    root, p = storage
    p.config_dir.mkdir()
    config = p.config_dir / 'earthlike_seed.yaml'
    config.write_text(dump_config_yaml(create_config('smoke')))
    manager = JobManager(root, p.workspace, paths=p)
    try:
        catalog = operation_catalog(root, p.workspace, paths=p)
        fields = {(op['id'], field['name']): field['default'] for op in catalog['operations'] for field in op['fields']}
        assert fields['generate', 'config'] == str(config)
        assert fields['generate', 'output'] == str(p.output_dir / 'world.json')
        assert fields['generate', 'debug_output'] == str(p.debug_dir)
        assert fields['render', 'output'] == str(p.exports_dir / 'world.svg')
        assert fields['calibrate', 'output'] == str(p.reports_dir / 'calibration.json')
        world = p.output_dir / 'world.json'
        world.parent.mkdir()
        world.write_text('{}')
        def render(job, command):
            target = Path(command[command.index('--output') + 1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('<svg/>')
            return 0
        with patch.object(manager, '_spawn', side_effect=render):
            job = manager.submit('render', {'world': str(world)})
            for _ in range(500):
                result = manager.get(job['id'])
                if result['status'] not in {'queued', 'running'}:
                    break
                time.sleep(.01)
        assert result['status'] == 'succeeded', result
        snapshot = manager.artifact_path(job['id'], 0)
        assert snapshot.is_relative_to(p.state_dir)
        (p.exports_dir / 'world.svg').write_text('changed')
        assert snapshot.read_text() == '<svg/>'
        with pytest.raises(JobInputError):
            manager.submit('render', {'world': str(world), 'output': str(root / 'unsafe.svg')})
        with pytest.raises(JobInputError):
            manager.submit('render', {'world': str(world), 'output': str(p.state_dir / 'overwrite')})
    finally:
        manager.close()


def test_cache_discovery_uses_external_debug_dir_and_skips_broken_candidate(storage, tmp_path):
    _, p = storage
    cache = _make_cache(tmp_path / 'fixture')
    shutil.copytree(cache, p.debug_dir)
    app = create_app()
    try:
        _, status = request(app, 'GET', '/api/status')
        assert status['cache_available'] and status['cache_dir'] == str(p.debug_dir)
        _, worlds = request(app, 'GET', '/api/worlds')
        assert any(w['cache_dir'] == str(p.debug_dir) for w in worlds['worlds'])
    finally:
        close(app)
    (p.debug_dir / 'manifest.json').write_text('{broken')
    fallback = p.workspace / 'world-a' / 'custom-cache-name'
    shutil.copytree(cache, fallback)
    app = create_app()
    try:
        _, status = request(app, 'GET', '/api/status')
        assert status['cache_available'] and status['cache_dir'] == str(fallback)
    finally:
        close(app)


def test_cli_discovery_and_explicit_option_precedence(storage, monkeypatch):
    root, p = storage
    p.config_dir.mkdir()
    config = p.config_dir / 'earthlike_seed.yaml'
    config.write_text(dump_config_yaml(create_config('smoke')))
    explicit = root / 'explicit.yaml'
    explicit.write_text(dump_config_yaml(create_config('smoke')))
    # Fail at generation after confirming which file/default destination reached
    # the command; no expensive native simulation is needed for this contract.
    with chdir(root), patch('magic_geo.cli.commands.generate.generate_world', side_effect=RuntimeError('probe')) as generate:
        result = CliRunner().invoke(cli, ['generate'])
        assert result.exit_code == 2 and 'probe' in result.output
        assert generate.call_args.args[0].mesh.cell_count == 128
        monkeypatch.setenv('MAGIC_GEO_CONFIG_PATH', str(root / 'missing.yaml'))
        result = CliRunner().invoke(cli, ['generate', '-c', str(explicit)])
        assert 'probe' in result.output
        result = CliRunner().invoke(cli, ['generate'])
        assert result.exit_code == 2 and generate.call_count == 2
    world = root / 'world.json'
    world.write_text('{}')
    with chdir(root), patch('magic_geo.cli.commands.render._load_world_for_cli', return_value={}), patch('magic_geo.cli.commands.render.write_svg_map') as write:
        result = CliRunner().invoke(cli, ['render', '-w', str(world)])
        assert result.exit_code == 0, result.output
        assert write.call_args.args[0] == p.exports_dir / 'world.svg'
        explicit_output = root / 'explicit.svg'
        result = CliRunner().invoke(cli, ['render', '-w', str(world), '-o', str(explicit_output)])
        assert result.exit_code == 0, result.output
        assert write.call_args.args[0] == explicit_output


def test_generation_publishes_cache_and_artifacts_across_independent_roots(storage, tmp_path):
    _, p = storage
    p.config_dir.mkdir()
    (p.config_dir / 'earthlike_seed.yaml').write_text(dump_config_yaml(create_config('smoke')))
    fixture = _make_cache(tmp_path / 'fixture')
    app = create_app()
    commands = []
    def produce(_job, command):
        commands.append(command)
        destination = Path(command[command.index('--output') + 1])
        if command[3] == 'generate':
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text('{"name":"external world"}')
        else:
            assert command[3] == 'export-debug'
            assert destination.parent == p.debug_dir.parent
            assert destination != p.debug_dir
            shutil.copytree(fixture, destination, dirs_exist_ok=True)
        return 0
    try:
        with patch.object(app.state.job_manager, '_spawn', side_effect=produce):
            status, job = request(app, 'POST', '/api/jobs', {'operation':'generate', 'arguments':{}})
            assert status == 202, job
            for _ in range(500):
                _, finished = request(app, 'GET', '/api/jobs/' + job['id'])
                if finished['status'] not in {'queued','running'}:
                    break
                time.sleep(.01)
        assert finished['status'] == 'succeeded', finished
        assert finished['cache_dir'] == str(p.debug_dir)
        assert len(commands) == 2
        _, status = request(app, 'GET', '/api/status')
        assert status['cache_available'] and status['cache_dir'] == str(p.debug_dir)
        status, headers, data = asgi_call(app, 'GET', f"/api/jobs/{job['id']}/artifacts/0")
        assert status == 200 and b'external world' in data
        assert not list(p.debug_dir.parent.glob('*.staging'))
    finally:
        close(app)
