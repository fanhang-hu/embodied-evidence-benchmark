"""Shared bootstrap, linked as _bootstrap.py beside each experiment entrypoint.

Only path setup lives here. Safety policies, model prompts, and experiment
decisions remain in the original experiment scripts.
"""
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('EMBODIED_RUN_ROOT', str(SOURCE_ROOT))).expanduser().resolve()
if not (ROOT / 'external').is_dir():
    raise RuntimeError('Workspace external/ directory is missing: ' + str(ROOT))

# Most historical experiments resolve inputs relative to their working directory.
os.chdir(ROOT)
paths = [SOURCE_ROOT, SOURCE_ROOT / 'e1_validation', SOURCE_ROOT / 'e2_validation',
         SOURCE_ROOT / 'setup_checks']
paths.extend(sorted((SOURCE_ROOT / 'e3_baseline').glob('b[1-9]_*')))
paths.extend(SOURCE_ROOT / p for p in (
    'external/RoboGuard/src', 'external/SPINE/src', 'external/SafeAgentBench',
    'external/safe-hierarchical-embodied-ai/src', 'external/selp/src',
    'external/PerceptTwin',
    # SafeGate's original pip --target installation lives with its evidence.
    'results/E3/04_contract/safegate/deps',
))
for path in reversed(paths):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Child Python processes need the same cross-directory imports, including when
# their source is compiled from a historical script prefix.
previous = os.environ.get('PYTHONPATH', '').split(os.pathsep)
os.environ['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(
    [str(p) for p in paths] + [p for p in previous if p]
))
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
