"""Copy selected workspace text files into this Git worktree; never delete files."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

REPO=Path(__file__).resolve().parents[1]
WORKSPACE=REPO.parent
FOLDERS=('e1_validation','e2_validation','e3_baseline','e4_validation','e5_validation','e6_validation',
         'benchmark_v0','scripts','configs','experiment_tools','setup_checks','tests','share-pool')
SUFFIXES={'.py','.md','.json','.yaml','.yml','.sh','.txt','.toml'}
SUMMARIES={'e6_online_summary.json':'results/E6/36_online_report/online_20261025_170422_914231/summary.json',
           'unified_development_summary.json':'results/benchmark_v0/unified_execution_run_20261122_01/unified_export/summary.json',
           'attribute_four_scene_summary.json':'results/benchmark_v0/attribute_expanded_export_20261122_01/summary.json',
           'unified_72_summary.json':'results/benchmark_v0/unified_development_72_20261122_01/summary.json',
           'candidate_four_scene_summary.json':'results/benchmark_v0/candidate_evaluation_attempts_20261122_01/summary.json'}


def candidates():
    for folder in FOLDERS:
        for p in (WORKSPACE/folder).rglob('*'):
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or '.git' in p.parts: continue
            if p.name.startswith('.env') or p.name in ('.netrc','.git-credentials') or p.suffix.lower() not in SUFFIXES: continue
            yield p,REPO/p.relative_to(WORKSPACE)
    for p in WORKSPACE.glob('*.md'):
        yield p,(REPO/'docs/original-project-readme.md' if p.name=='README.md' else REPO/p.name)
    for name,source in SUMMARIES.items():
        p=WORKSPACE/source
        if p.is_file(): yield p,REPO/'evidence/summaries'/name


def digest(p): return hashlib.sha256(p.read_bytes()).digest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply',action='store_true',help='copy changes after verifying the Git worktree is clean')
    args=ap.parse_args()
    differences=[(src,dst) for src,dst in candidates() if not dst.exists() or digest(src)!=digest(dst)]
    if args.apply:
        state=subprocess.run(['git','status','--porcelain'],cwd=REPO,text=True,capture_output=True,check=True)
        if state.stdout.strip(): raise SystemExit('Refusing to overwrite a dirty Git worktree; commit or inspect it first.')
        for src,dst in differences:
            dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        # This tool copies without deleting; update the summary provenance index
        # to match the exact four selected source files that are available.
        import json
        manifest=[{'file':name,'workspace_source':source,'sha256':hashlib.sha256((WORKSPACE/source).read_bytes()).hexdigest()}
                  for name,source in SUMMARIES.items() if (WORKSPACE/source).is_file()]
        (REPO/'evidence/summaries/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(('COPIED' if args.apply else 'CHANGED_OR_NEW'),len(differences))
    for _,dst in differences: print(dst.relative_to(REPO))
    if not args.apply: print('Check only; --apply copies selected files and never deletes removed source files.')

if __name__=='__main__': main()
