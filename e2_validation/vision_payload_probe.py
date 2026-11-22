import _bootstrap  # Workspace paths and historical cross-script imports.
import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from ai2thor.controller import Controller

OUT = Path("results/m6_vision")
OUT.mkdir(parents=True, exist_ok=True)

controller = None

try:
    controller = Controller(
        scene="FloorPlan1",
        width=300,
        height=300,
        quality="Low",
        renderDepthImage=True,
    )

    frame = controller.last_event.frame.copy()
    truth = controller.last_event.metadata["objects"]

    assert isinstance(frame, np.ndarray)
    assert frame.ndim == 3 and frame.shape[2] == 3

    # 正确编码 RGB 图像
    buffer = io.BytesIO()
    Image.fromarray(frame.astype("uint8")).save(
        buffer, format="PNG"
    )

    raw_png = buffer.getvalue()
    encoded = base64.b64encode(raw_png).decode("ascii")

    image_uri = "data:image/png;base64," + encoded

    assert base64.b64decode(
        image_uri.split(",", 1)[1]
    ) == raw_png

    with Image.open(io.BytesIO(raw_png)) as check:
        check.verify()

    # 只向视觉接口传递图像和任务，不传递模拟器元数据。
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe the visible objects and their spatial relationships."
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_uri}
                }
            ]
        }]
    }

    (OUT / "observation.png").write_bytes(raw_png)
    (OUT / "vision_payload.json").write_text(
        json.dumps(payload)
    )

    # 私有评估真值：不参与视觉模型输入。
    (OUT / "private_truth.json").write_text(
        json.dumps(truth, indent=2)
    )

    manifest = {
        "scene": "FloorPlan1",
        "image_shape": list(frame.shape),
        "image_sha256": hashlib.sha256(raw_png).hexdigest(),
        "image_format": "PNG",
        "mime_type": "image/png",
        "oracle_objects_in_vision_payload": False,
        "model_called": False,
        "action_executed": False,
    }

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    print("=== M6-3A Vision Input Probe ===")
    print("RGB shape:", frame.shape)
    print("PNG bytes:", len(raw_png))
    print("PNG encoding:", "VALID")
    print("Oracle metadata in VLM input:", False)
    print("Model called:", False)
    print("Action executed:", False)
    print("Saved:", OUT)
    print("M6-3A PASSED")

finally:
    if controller is not None:
        controller.stop()
