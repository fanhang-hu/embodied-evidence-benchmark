"""M6-3B: locate a stove observation with ground truth only for camera selection.
No vision model, state injection, or object interaction is performed.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import math
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller

OUT = Path('results/m6_vision')
OUT.mkdir(parents=True, exist_ok=True)


def pos2d(obj):
    p = obj['position']
    return p['x'], p['z']


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def physical_state(objects):
    keys = ('position', 'rotation', 'parentReceptacles', 'receptacleObjectIds',
            'isToggled', 'isOpen', 'isPickedUp', 'isBroken')
    return {o['objectId']: {k: deepcopy(o.get(k)) for k in keys} for o in objects}


controller = None
try:
    controller = Controller(
        scene='FloorPlan1', width=300, height=300,
        quality='Low', renderDepthImage=True,
    )
    initial_objects = deepcopy(controller.last_event.metadata['objects'])
    before = physical_state(initial_objects)
    burners = [o for o in initial_objects if o['objectType'] == 'StoveBurner']
    knobs = [o for o in initial_objects if o['objectType'] == 'StoveKnob']
    assert len(burners) == len(knobs) == 4

    stove = (sum(o['position']['x'] for o in burners) / len(burners),
             sum(o['position']['z'] for o in burners) / len(burners))

    event = controller.step(action='GetReachablePositions')
    assert event.metadata['lastActionSuccess'], event.metadata.get('errorMessage')
    reachable = event.metadata['actionReturn']
    assert reachable, 'No reachable camera positions'

    # The stove is mounted against the negative-z kitchen wall in FloorPlan1.
    # Prefer reachable positions in front of it, at a moderate viewing distance.
    points = sorted(
        reachable,
        key=lambda p: (
            3.0 if p['z'] <= stove[1] else 0.0,
            abs(distance((p['x'], p['z']), stove) - 1.45),
            abs(p['x'] - stove[0]) * 0.2,
        ),
    )

    selected = []
    for p in points:
        if all(distance((p['x'], p['z']), (q['x'], q['z'])) >= 0.35 for q in selected):
            selected.append(p)
        if len(selected) == 12:
            break

    candidates = []
    best = None
    for idx, p in enumerate(selected):
        dx, dz = stove[0] - p['x'], stove[1] - p['z']
        heading = (math.degrees(math.atan2(dx, dz)) + 360) % 360
        event = controller.step(
            action='TeleportFull',
            x=p['x'], y=p['y'], z=p['z'],
            rotation={'x': 0, 'y': heading, 'z': 0},
            horizon=30, standing=True,
        )
        if not event.metadata.get('lastActionSuccess', False):
            candidates.append({
                'attempt': idx, 'success': False,
                'error': event.metadata.get('errorMessage', ''),
            })
            continue

        objects = event.metadata['objects']
        n_burner = sum(o['objectType'] == 'StoveBurner' and o['visible'] for o in objects)
        n_knob = sum(o['objectType'] == 'StoveKnob' and o['visible'] for o in objects)
        n_pan = sum(o['objectType'] in ('Pan', 'Pot') and o['visible'] for o in objects)
        score = 3 * n_burner + 2 * n_knob + n_pan
        image_path = OUT / f'stove_candidate_{idx:02d}.png'
        Image.fromarray(np.asarray(event.frame, dtype=np.uint8)).save(image_path)
        item = {
            'attempt': idx, 'success': True, 'score': score,
            'stove_burners_visible': n_burner,
            'stove_knobs_visible': n_knob,
            'cookware_visible': n_pan,
            'pose': {'position': p, 'heading': heading, 'horizon': 30},
            'image': str(image_path),
        }
        candidates.append(item)
        if best is None or item['score'] > best['score']:
            best = item

    assert best is not None, 'All camera reposition attempts failed'
    best_image = OUT / 'stove_view.png'
    best_image.write_bytes(Path(best['image']).read_bytes())
    (OUT / 'stove_camera_candidates.json').write_text(json.dumps(candidates, indent=2))
    (OUT / 'stove_view_manifest.json').write_text(json.dumps({
        'scene': 'FloorPlan1',
        'purpose': 'camera view selection only, not visual perception benchmark',
        'camera_selection_uses_private_simulator_metadata': True,
        'best': best,
        'object_interaction_executed': False,
        'vlm_called': False,
    }, indent=2))

    assert physical_state(controller.last_event.metadata['objects']) == before, (
        'Physical object state changed during camera positioning'
    )
    print('=== M6-3B Stove RGB View ===')
    print('Reachable positions:', len(reachable))
    print('Camera candidates evaluated:', sum(x['success'] for x in candidates))
    print('Best stove burners visible:', best['stove_burners_visible'])
    print('Best stove knobs visible:', best['stove_knobs_visible'])
    print('Best cookware visible:', best['cookware_visible'])
    print('Best image:', best_image)
    print('Object states unchanged: YES')
    print('VLM called: NO')
    print('Physical interaction: NO')
    if best['stove_burners_visible'] and best['stove_knobs_visible']:
        print('M6-3B STOVE VIEW CANDIDATE FOUND; REVIEW IMAGE')
    else:
        print('M6-3B STOVE VISIBILITY NOT VERIFIED; REVIEW CANDIDATES')
finally:
    if controller is not None:
        controller.stop()
