"""Export development-only selected setup configurations with provenance."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha


def load(p): return json.loads(p.read_text())


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',required=True); ap.add_argument('--audit',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args(); run,audit,out=map(checked_path,(a.run,a.audit,a.out))
    result=load(run/'results.json'); proof=load(audit/'audit.json')
    if (proof['status']!='PASS_SETUP_RECORD_AUDIT' or proof['source_protocol_sha256']!=sha(run/'protocol.json') or
        proof['source_results_sha256']!=sha(run/'results.json') or result['status']!='FINISHED'):
        raise ValueError('setup audit/provenance mismatch')
    rows=[]
    for s in result['scenes']:
        row=dict(scene=s['scene'],selection_status=s['status'],split='observed_development',
                 attempts=len(s['attempts']),source_setup_results_sha256=sha(run/'results.json'),
                 source_setup_audit_sha256=sha(audit/'audit.json'))
        if s['status']=='FEASIBLE':
            row.update(case_id='dev_setup_'+s['scene']+'_01',**s['selected'],
                       setup_validation='one setup and evaluator drift; no attack or guard run',
                       full_task_validated=False,heldout=False)
        rows.append(row)
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    path=out/'cases.jsonl'; path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    manifest=dict(schema='embodied.evidence_benchmark.dev_setup_manifest.v1',scenes=len(rows),
                  feasible=sum(r['selection_status']=='FEASIBLE' for r in rows),cases_sha256=sha(path),
                  source_results_sha256=sha(run/'results.json'),source_audit_sha256=sha(audit/'audit.json'),
                  exporter_sha256=sha(Path(__file__).resolve()),
                  limitations=['Observed development cases only', 'One setup trial per attempted pair',
                               'No original truth snapshots retained for independent replay',
                               'Not compatible with the old hard-coded candidate evaluation runner'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for f in out.iterdir(): os.chmod(f,0o600)
    print('DEVELOPMENT_SETUP_CASES',len(rows),'FEASIBLE',manifest['feasible'])

if __name__=='__main__': main()
