"""Audit frozen routing, stage completion, and unified artifact bindings."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_v0_suite_v1 import checked_path,sha
from benchmark_v0_unified_runner_v1 import STAGES,verify,stage_output_ok


def load(p): return json.loads(p.read_text())
def must(x,message):
    if not x: raise ValueError(message)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--run',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args(); run,out=checked_path(a.run),checked_path(a.out)
    p=verify(run/'protocol.json'); s=load(run/'status.json')
    must(s['status']=='COMPLETE' and s['source_protocol_sha256']==sha(run/'protocol.json'),'execution incomplete')
    must([x['stage'] for x in s['stages']]==list(STAGES) and all(x['status']=='COMPLETE' for x in s['stages']),'stage order/status')
    for stage in STAGES:
        must(stage_output_ok(stage,run) and (run/(stage+'.log')).is_file(),'stage output/log '+stage)
    unified=load(run/'unified_export/summary.json'); audit=load(run/'unified_audit/audit.json')
    must(audit['status']=='PASS_UNIFIED_EXPORT_AUDIT' and audit['source_summary_sha256']==sha(run/'unified_export/summary.json') and
         audit['source_episodes_sha256']==sha(run/'unified_export/episodes.jsonl') and
         audit['source_cases_sha256']==sha(run/'unified_export/cases.jsonl'),'unified audit binding')
    must(unified['planned']==unified['audited_completed']==s['planned_episodes']==s['audited_completed']==p['planned_episodes'], 'episode counts')
    cases=[json.loads(x) for x in (run/'unified_export/cases.jsonl').read_text().splitlines() if x.strip()]
    must([(c['contract'],c['case_id'],c['scene'],c['family'],c['split']) for c in cases]==
         [(c['contract'],c['case_id'],c['scene'],c['family'],c['split']) for c in p['cases']],'routing cases')
    must(unified['method_matrix']==p['method_matrix'],'method capabilities')
    paths={str((run/(stage+'.log')).relative_to(run)):sha(run/(stage+'.log')) for stage in STAGES}
    paths.update({'status.json':sha(run/'status.json'),'protocol.json':sha(run/'protocol.json'),
                  'unified_export/summary.json':sha(run/'unified_export/summary.json'),
                  'unified_export/episodes.jsonl':sha(run/'unified_export/episodes.jsonl'),
                  'unified_export/cases.jsonl':sha(run/'unified_export/cases.jsonl'),
                  'unified_audit/audit.json':sha(run/'unified_audit/audit.json')})
    out.mkdir(parents=True,mode=0o700,exist_ok=False); os.chmod(out,0o700)
    result=dict(status='PASS_UNIFIED_EXECUTION_AUDIT',planned=p['planned_episodes'],audited_completed=s['audited_completed'],
                cases=len(cases),stage_count=len(STAGES),source_run=str(run.relative_to(ROOT)),source_hashes=paths,
                auditor_sha256=sha(Path(__file__).resolve()),
                limitations=['Checks recorded stage routing and source audits; no new Unity or Guard replay',
                             'Fixed pre-frozen development backends, not a general plugin interface',
                             'Does not establish held-out independence or complete task success'])
    path=out/'audit.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); os.chmod(path,0o600)
    print(result['status'],result['audited_completed'],'/',result['planned'])

if __name__=='__main__': main()
