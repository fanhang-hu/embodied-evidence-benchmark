import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import base64
import io
import json
import os
import time
from pathlib import Path

import cv2
from PIL import Image
from openai import OpenAI

ROOT = Path("external/HomeSafe-Bench")
OUT = Path("results/E3/05_hdguard")
OUT.mkdir(parents=True, exist_ok=True)

source = ROOT / "detector_dual_brain/dual_brain.py"
tree = ast.parse(source.read_text())

fast = next(
    x for x in tree.body
    if isinstance(x, ast.ClassDef)
    and x.name == "FastBrain"
)

assign = next(
    x for x in ast.walk(fast)
    if isinstance(x, ast.Assign)
    and any(
        isinstance(t, ast.Attribute)
        and t.attr == "sys_prompt"
        for t in x.targets
    )
)

prompt = ast.literal_eval(assign.value)

video = ROOT / "assets/230_C4_L1_D1.mp4"
cap = cv2.VideoCapture(str(video))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, round(4.0 * fps))
ok, bgr = cap.read()
cap.release()
assert ok

rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
image = Image.fromarray(rgb)
image.thumbnail((512, 512))

buf = io.BytesIO()
image.save(buf, format="JPEG", quality=75)
url = "data:image/jpeg;base64," + base64.b64encode(
    buf.getvalue()
).decode("utf-8")

key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
assert key, "Missing API key"

client = OpenAI(
    api_key=key,
    base_url=os.getenv(
        "DEEPSEEK_BASE_URL",
        os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    ),
    timeout=120,
    max_retries=0,
)

model = os.getenv("HD_DEEPSEEK_MODEL", "deepseek-flash")

tests = [
    ("json_mode", {"response_format": {"type": "json_object"}}),
    ("text_mode", {}),
]

results = {}

for name, extra in tests:
    print(f"\n=== {name} ===", flush=True)

    start = time.perf_counter()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Inspect the image. Output exactly "
                                "one JSON object with keys category "
                                "and reason. category must be green, "
                                "yellow, or red. If visual evidence "
                                "is insufficient, explain why."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": url,
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            max_tokens=1024,
            **extra,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        results[name] = {
            "content": content,
            "finish_reason": choice.finish_reason,
            "usage": (
                response.usage.model_dump()
                if response.usage else None
            ),
            "elapsed": round(
                time.perf_counter() - start, 3
            ),
            "error": None,
        }

    except Exception as e:
        results[name] = {
            "content": None,
            "error": f"{type(e).__name__}: {e}",
            "elapsed": round(
                time.perf_counter() - start, 3
            ),
        }

    print(json.dumps(
        results[name], indent=2, ensure_ascii=False
    ))

output = OUT / "e5a2_fast_diagnostic.json"
output.write_text(json.dumps(
    {
        "test": "E5-A2",
        "model": model,
        "video": str(video),
        "frame_time": 4.0,
        "results": results,
    },
    indent=2,
    ensure_ascii=False,
))

print("\nSaved:", output)
