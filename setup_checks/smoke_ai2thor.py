import _bootstrap  # Workspace paths and historical cross-script imports.
from ai2thor.controller import Controller
from PIL import Image
import time

c = None
try:
    t0 = time.perf_counter()
    c = Controller(scene='FloorPlan1', width=300, height=300, quality='Low', renderDepthImage=True)
    e = c.step(action='RotateRight')
    assert e.metadata['lastActionSuccess']
    assert e.frame is not None and e.frame.size > 0
    assert e.depth_frame is not None
    Image.fromarray(e.frame).save('smoke_rgb.png')
    print({'frame': e.frame.shape, 'seconds': time.perf_counter()-t0})
finally:
    if c is not None:
        c.stop()
