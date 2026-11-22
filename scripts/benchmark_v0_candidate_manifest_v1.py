"""Export provisional scene candidates; not a formal benchmark test split."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--discovery', required=True); ap.add_argument('--out', required=True)
    args = ap.parse_args(); src, out = checked_path(args.discovery), checked_path(args.out)
    protocol, state = (json.loads((src / n).read_text()) for n in ('protocol.json', 'status.json'))
    if state['status'] != 'DISCOVERY_FINISHED' or state['protocol_sha256'] != sha(src/'protocol.json'):
        raise ValueError('Discovery incomplete or protocol mismatch')
    if state['expected'] != len(protocol['scenes']) or state['completed'] != state['expected']:
        raise ValueError('Discovery count mismatch')
    if [r['scene'] for r in state['scenes']] != protocol['scenes']:
        raise ValueError('Discovery scene ordering mismatch')
    for name, value in protocol['source_sha256'].items():
        if sha(ROOT / name) != value: raise ValueError('Frozen discovery source changed: ' + name)
    rows = []
    for row in state['scenes']:
        target = row.get('selected_metadata')
        base = dict(scene=row['scene'], status='PROVISIONAL_METADATA_ELIGIBLE' if target else 'NOT_ELIGIBLE_OR_ERROR',
                    discovery_status=row['status'], split='unassigned_candidate_not_heldout',
                    source_protocol_sha256=sha(src/'protocol.json'), source_discovery_status_sha256=sha(src/'status.json'))
        if target:
            base.update(case_id='candidate_relation_' + row['scene'] + '_01', family='relation',
                        pan_id=target['cookware_id'], burner_id=target['burner_id'], knob_id=target['knob_id'],
                        object_type=target['cookware_type'], initial_target_on_burner=target['initial_target_on_burner'],
                        preparation_validated=False, action_execution_validated=False, history_independence_verified=False)
        rows.append(base)
    out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    (out/'candidates.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))
    meta = dict(schema='embodied.evidence_benchmark.provisional_scene_candidates.v1', candidates=len(rows),
                metadata_eligible=sum(r['status']=='PROVISIONAL_METADATA_ELIGIBLE' for r in rows),
                source_protocol_sha256=sha(src/'protocol.json'), source_discovery_status_sha256=sha(src/'status.json'),
                exporter_sha256=sha(Path(__file__).resolve()), output_sha256=sha(out/'candidates.jsonl'),
                limitations=['Not an established held-out split', 'Not yet accepted by legacy suite runner',
                             'No native preparation, attack, Guard, candidate action or model evaluated',
                             'Historical independence and layout similarity require additional review'])
    (out/'manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
    for f in out.iterdir(): os.chmod(f, 0o600)
    print('PROVISIONAL_CANDIDATES', meta['candidates'], 'METADATA_ELIGIBLE', meta['metadata_eligible'])

if __name__ == '__main__': main()
