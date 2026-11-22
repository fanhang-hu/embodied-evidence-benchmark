#!/usr/bin/env python3
"""Launch an existing experiment in its recorded environment and a fresh workspace."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_manifest(target):
    if target in ('e1', 'e2', 'setup'):
        folder = {'e1': 'e1_validation', 'e2': 'e2_validation', 'setup': 'setup_checks'}[target]
    else:
        choices = [p for p in (ROOT / 'e3_baseline').glob('b[1-9]_*')
                   if target in (p.name, p.name.split('_', 1)[0], p.name.split('_', 1)[0][1:])]
        if len(choices) != 1:
            raise ValueError('Choose e1, e2, setup, or b1 ... b9.')
        folder = str(choices[0].relative_to(ROOT))
    return ROOT / folder, json.loads((ROOT / folder / 'manifest.json').read_text())


def interpreter(name):
    override = os.environ.get('EMBODIED_PYTHON_' + name.upper().replace('-', '_'))
    if override:
        return Path(override).expanduser()
    if name == 'embguard-cpu':
        return Path(os.environ.get('EMBGUARD_PYTHON', str(Path.home() / '.venvs/embguard-cpu/bin/python'))).expanduser()
    for base in (Path.home() / '.conda/envs', Path.home() / 'miniconda3/envs'):
        p = base / name / 'bin/python'
        if p.is_file():
            return p
    return Path.home() / '.conda/envs' / name / 'bin/python'


def environment_probe(executable, imports):
    if not executable.is_file():
        return {'python': str(executable), 'available': False}
    code = '''
import importlib, importlib.metadata as md, json, sys
out = {'python': sys.executable, 'version': sys.version.split()[0], 'available': True,
       'packages': {}, 'imports': {}}
for p in ['ai2thor','openai','httpx','z3-solver','torch','torchvision','transformers',
          'pyautogen','numpy','opencv-python','pyarrow','jax']:
    try: out['packages'][p] = md.version(p)
    except md.PackageNotFoundError: pass
for p in json.loads(sys.argv[1]):
    try:
        m = importlib.import_module(p)
        out['imports'][p] = {'ok': True, 'version': getattr(m, '__version__', None)}
    except Exception as e:
        out['imports'][p] = {'ok': False, 'error': type(e).__name__ + ': ' + str(e)}
print(json.dumps(out))
'''
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = os.pathsep.join(str(ROOT / p) for p in (
        'external/RoboGuard/src', 'external/SPINE/src', 'external/selp/src',
        'external/PerceptTwin', 'external/safe-hierarchical-embodied-ai/src',
        'results/E3/04_contract/safegate/deps',
    ))
    try:
        result = subprocess.run([str(executable), '-B', '-c', code, json.dumps(imports)],
                                env=env, text=True, capture_output=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'python': str(executable), 'available': False, 'error': str(exc)}
    if result.returncode:
        return {'python': str(executable), 'available': False,
                'error': result.stderr[-1500:]}
    return json.loads(result.stdout.splitlines()[-1])


def make_workspace(path):
    path = path.expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Use a workspace outside the source tree, for example /tmp/embodied-runs/run01.')
    path.mkdir(parents=True, exist_ok=False)
    for name in ('results', 'e1_validation', 'e2_validation', 'e3_baseline',
                 'experiment_tools', 'scripts', 'configs'):
        shutil.copytree(ROOT / name, path / name, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('external', 'share-pool'):
        (path / name).symlink_to(ROOT / name, target_is_directory=True)
    for p in ROOT.glob('*.png'):
        shutil.copy2(p, path / p.name)
    return path


def main():
    argv = sys.argv[1:]
    cut = argv.index('--') if '--' in argv else len(argv)
    script_args = argv[cut+1:] if cut < len(argv) else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='e1, e2, setup, or b1 ... b9')
    parser.add_argument('--check', action='store_true', help='Read-only interpreter/import/evidence check')
    parser.add_argument('--list', action='store_true', help='List existing experiment scripts')
    parser.add_argument('--script', help='Script basename, current relative path, or historical path')
    parser.add_argument('--python', type=Path, help='Explicit interpreter override')
    parser.add_argument('--work-dir', type=Path, help='New isolated workspace; must not exist')
    parser.add_argument('--fresh-result', action='append', default=[], metavar='RESULTS_RELATIVE_PATH',
                        help='Remove this copied result in the new workspace before rerunning')
    opts = parser.parse_args(argv[:cut])
    folder, manifest = load_manifest(opts.target)
    if opts.list:
        for p in sorted(folder.glob('*.py')):
            if not p.name.startswith('_'):
                print(p.name)
        return 0
    if opts.check or not opts.script:
        probes = {name: environment_probe(interpreter(name), modules)
                  for name, modules in manifest['environments'].items()}
        evidence = {p: (ROOT / p).is_file() for p in manifest.get('evidence', [])}
        print(json.dumps({'target': manifest['name'], 'environments': probes,
                          'evidence': evidence}, ensure_ascii=False, indent=2))
        return 0 if (all(v.get('available') and all(x['ok'] for x in v.get('imports', {}).values())
                         for v in probes.values()) and all(evidence.values())) else 1
    path_map = json.loads((ROOT / 'organization_audit/path_map.json').read_text())
    script = ROOT / path_map.get(opts.script, opts.script)
    if not script.is_file():
        script = folder / Path(opts.script).name
    if not script.is_file() or script.parent != folder or script.name.startswith('_'):
        parser.error('Script must be an entrypoint listed by this target --list.')
    env_name = manifest.get('script_environments', {}).get(script.name, manifest['default_environment'])
    executable = opts.python or interpreter(env_name)
    if not executable.is_file():
        parser.error('Missing interpreter: ' + str(executable))
    if opts.work_dir:
        work = make_workspace(opts.work_dir)
    else:
        parent = Path(tempfile.mkdtemp(prefix='embodied-run-'))
        work = make_workspace(parent / 'workspace')
    for relative in opts.fresh_result:
        item = (work / 'results' / relative).resolve()
        if work / 'results' not in item.parents:
            parser.error('--fresh-result must name a file or subdirectory inside copied results/.')
        if item.is_dir():
            shutil.rmtree(item)
        elif item.exists():
            item.unlink()
    env = os.environ.copy()
    env['EMBODIED_RUN_ROOT'] = str(work)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['EMBGUARD_PYTHON'] = str(interpreter('embguard-cpu'))
    for key, value in manifest.get('runtime_defaults', {}).items():
        env.setdefault(key, value)
    relative_script = script.relative_to(ROOT)
    command = [str(executable), '-B', '-u', str(work / relative_script), *script_args]
    print('Environment:', env_name, flush=True)
    print('Workspace:', work, flush=True)
    print('Entrypoint:', relative_script, flush=True)
    return subprocess.call(command, cwd=work, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError) as exc:
        raise SystemExit(str(exc))
