import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import base64
import hashlib
import io
import json
import logging
import os
import time
from pathlib import Path

import cv2
from PIL import Image
from openai import OpenAI

ROOT = Path("external/HomeSafe-Bench")
BASE = Path("results/E3/05_hdguard")
SOURCE = ROOT / "detector_dual_brain/dual_brain.py"
VIDEO = ROOT / "assets/230_C4_L1_D1.mp4"

BASE.mkdir(parents=True, exist_ok=True)

MODEL = os.getenv("HD_DEEPSEEK_MODEL", "deepseek-flash")
KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
URL = os.getenv(
    "OPENAI_BASE_URL",
    "https://api.deepseek.com"
)

assert KEY, "DeepSeek API key missing"
assert MODEL == "deepseek-flash", (
    "Vision test requires deepseek-flash"
)

assert SOURCE.is_file()
assert VIDEO.is_file()

client = OpenAI(
    api_key=KEY,
    base_url=URL,
    timeout=120.0,
    max_retries=0,
)

# --------------------------------------------------
# 1. Extract original FastBrain prompt and
#    original SlowBrain class from official source.
# --------------------------------------------------

tree = ast.parse(SOURCE.read_text())

classes = {
    node.name: node
    for node in tree.body
    if isinstance(node, ast.ClassDef)
}

assert "FastBrain" in classes
assert "SlowBrain" in classes

fast_init = next(
    node
    for node in classes["FastBrain"].body
    if isinstance(node, ast.FunctionDef)
    and node.name == "__init__"
)

prompt_assignments = [
    node
    for node in ast.walk(fast_init)
    if isinstance(node, ast.Assign)
    and any(
        isinstance(t, ast.Attribute)
        and t.attr == "sys_prompt"
        for t in node.targets
    )
]

assert len(prompt_assignments) == 1

FAST_PROMPT = ast.literal_eval(
    prompt_assignments[0].value
)

logger = logging.getLogger("hdguard_e5")

slow_scope = {
    "OpenAI": OpenAI,
    "io": io,
    "base64": base64,
    "time": time,
    "logger": logger,
    "VLLM_API_KEY": "unused",
    "VLLM_API_URL": URL,
    "SLOW_BRAIN_MODEL_NAME": MODEL,
}

exec(
    compile(
        ast.Module(
            body=[classes["SlowBrain"]],
            type_ignores=[],
        ),
        str(SOURCE),
        "exec",
    ),
    slow_scope,
)

NativeSlowBrain = slow_scope["SlowBrain"]

class DeepSeekSlowBrain(NativeSlowBrain):
    def __init__(self):
        # Change model endpoint only.
        # Original deep_reason() is inherited unchanged.
        self.client = client
        self.model_name = MODEL


# --------------------------------------------------
# 2. Read genuine frames from the official video.
# --------------------------------------------------

cap = cv2.VideoCapture(str(VIDEO))
assert cap.isOpened()

fps = cap.get(cv2.CAP_PROP_FPS)
assert fps > 0

def get_frame(t):
    cap.set(
        cv2.CAP_PROP_POS_FRAMES,
        round(t * fps)
    )
    ok, bgr = cap.read()
    assert ok, f"Video decode failed at {t}s"

    rgb = cv2.cvtColor(
        bgr,
        cv2.COLOR_BGR2RGB
    )

    image = Image.fromarray(rgb)
    image.thumbnail((512, 512))
    return image

TIMES = [3.4, 3.6, 3.8, 4.0]
clean_frames = [get_frame(t) for t in TIMES]
cap.release()

black_frames = [
    Image.new("RGB", im.size, (0, 0, 0))
    for im in clean_frames
]

def sha_image(im):
    return hashlib.sha256(im.tobytes()).hexdigest()

def encode_image(im):
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=75)
    return "data:image/jpeg;base64," + base64.b64encode(
        buf.getvalue()
    ).decode("utf-8")

print("=== SOURCE ===")
print("Video:", VIDEO)
print("FPS:", fps)
print("Frame times:", TIMES)
print("Model:", MODEL)
print("Original Fast prompt: YES")
print("Original Slow deep_reason: YES")

# --------------------------------------------------
# 3. Real DeepSeek FastBrain visual inference.
# --------------------------------------------------

def real_fast(image):
    t0 = time.perf_counter()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": FAST_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this actual robot-video "
                            "frame and return the risk "
                            "classification as JSON."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": encode_image(image),
                            "detail": "low",
                        },
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=512,
    )

    elapsed = time.perf_counter() - t0

    raw = response.choices[0].message.content or ""

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    category = (
        parsed.get("category")
        if isinstance(parsed, dict)
        else None
    )

    if isinstance(category, str):
        category = category.lower()

    valid = category in {
        "green", "yellow", "red"
    }

    return {
        "raw": raw,
        "category": category,
        "valid": valid,
        "elapsed_seconds": round(elapsed, 3),
        "usage": (
            response.usage.model_dump()
            if response.usage else None
        ),
    }


# --------------------------------------------------
# 4. Real DeepSeek SlowBrain visual inference.
# --------------------------------------------------

slow = DeepSeekSlowBrain()

def real_slow(frames):
    start = time.perf_counter()

    # Original official SlowBrain.deep_reason(),
    # but self.client and self.model_name are
    # the DeepSeek endpoint/model.
    raw, native_cost = slow.deep_reason(frames)

    wall = time.perf_counter() - start

    upper = raw.upper()

    verdict = None
    if "**VERDICT**: DANGER" in upper:
        verdict = "DANGER"
    elif "**VERDICT**: SAFE" in upper:
        verdict = "SAFE"

    return {
        "raw": raw,
        "verdict": verdict,
        "valid": verdict is not None,
        "native_cost_seconds": round(native_cost, 3),
        "wall_seconds": round(wall, 3),
    }


# --------------------------------------------------
# 5. Four actual API calls.
# --------------------------------------------------

report = {
    "test": "HD-Guard E5-A",
    "type": "real_deepseek_vision_pilot",
    "model": MODEL,
    "video": str(VIDEO),
    "sample_times": TIMES,
    "fast_original_prompt": True,
    "slow_original_deep_reason": True,
    "fast_original_minicpm_model": False,
    "slow_original_qwen_model": False,
    "original_scheduler_executed": False,
    "GT_provided_to_model": False,
    "cases": {},
}

out = BASE / "e5a_deepseek_vision.json"

def save():
    out.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

tests = [
    ("fast_clean", lambda: real_fast(clean_frames[-1])),
    ("fast_corrupted", lambda: real_fast(black_frames[-1])),
    ("slow_clean", lambda: real_slow(clean_frames)),
    ("slow_corrupted", lambda: real_slow(black_frames)),
]

for name, fn in tests:
    print(f"\n=== {name} ===", flush=True)

    try:
        result = fn()
        result["api_error"] = None
    except Exception as e:
        result = {
            "valid": False,
            "api_error": (
                f"{type(e).__name__}: {e}"
            ),
        }

    result["frame_hashes"] = [
        sha_image(x)
        for x in (
            clean_frames if "clean" in name
            else black_frames
        )
    ]

    report["cases"][name] = result
    save()

    print("Valid:", result.get("valid"))
    print("Category:", result.get("category"))
    print("Verdict:", result.get("verdict"))
    print("Raw:", result.get("raw"))
    print("Error:", result.get("api_error"))
    print(
        "Latency:",
        result.get(
            "elapsed_seconds",
            result.get("wall_seconds")
        )
    )

print("\n=== E5-A SUMMARY ===")

valid = sum(
    bool(x.get("valid"))
    for x in report["cases"].values()
)

print("Valid predictions:", f"{valid}/4")
print("Saved:", out)

report["valid_predictions"] = valid
save()
