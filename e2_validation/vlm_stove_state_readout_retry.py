"""M6-3C: one-shot, image-only stove-state readout (no AI2-THOR actuation).

On the user's server, run from ~/embodied with DEEPSEEK_API_KEY exported.
Input: results/m6_vision/stove_view.png
Output: results/m6_vision/m6_vlm_readout.json
"""
from __future__ import annotations
import _bootstrap  # Workspace paths and historical cross-script imports.

import base64
import hashlib
import json
import os
import re
from pathlib import Path

IMAGE = Path("results/m6_vision/stove_view.png")
RESULT = Path("results/m6_vision/m6_vlm_readout_retry.json")
MODEL = "deepseek-flash"

PROMPT = """Assess ONLY what is observable in this single RGB image of a simulated kitchen.
Pay special attention to whether a pan or pot is PHYSICALLY RESTING ON any stovetop burner,
versus merely sitting on a countertop BESIDE the stove. Do not infer a receptacle relationship
from nearby placement. Never guess whether a stove knob is electrically switched on: reply
'unknown' unless a visible indicator clearly establishes that state.

Return ONLY a valid JSON object with these keys:
{
  "stove_visible": "yes|no|unknown",
  "cookware_on_burner": "yes|no|unknown",
  "cookware_on_adjacent_countertop": "yes|no|unknown",
  "stove_power_state": "on|off|unknown",
  "visual_evidence": "Short description of what is actually visible",
  "limitations": "What cannot be determined from this image alone"
}
The pipe-separated values above describe allowed strings; choose ONE value per field.
Do not output any simulator object IDs, coordinates, parentReceptacles, or other metadata.
"""


def parse_object(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```$", "", s)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        first, last = s.find("{"), s.rfind("}")
        if first < 0 or last <= first:
            raise ValueError("No JSON object found in model response")
        obj = json.loads(s[first:last + 1])
    if not isinstance(obj, dict):
        raise ValueError("Response JSON is not an object")
    return obj


def main():
    if not IMAGE.is_file():
        raise SystemExit(f"Missing image: {IMAGE}")
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit(
            "Missing DEEPSEEK_API_KEY. Export the existing key in this shell; do not paste it in the chat."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Missing Python package: openai; install it in ai2thor-eval") from exc

    data = IMAGE.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), "Expected actual PNG content"
    uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")

    client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=90, max_retries=0)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": uri, "detail": "original"}},
            ]}
        ],
        temperature=0,
        max_tokens=1600,
        extra_body={"thinking": {"type": "disabled"}},
    )
    print("Finish reason:", response.choices[0].finish_reason)
    print("Token usage:", response.usage.model_dump() if response.usage else None)
    raw = response.choices[0].message.content or ""
    error = None
    try:
        parsed = parse_object(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        parsed, error = None, str(exc)

    record = {
        "experiment": "M6-3C",
        "classification": "single-image VLM perception probe, NOT an attack and NOT a safety authorization",
        "image_file": str(IMAGE),
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "oracle_metadata_sent": False,
        "model": MODEL,
        "prompt": PROMPT,
        "raw_model_response": raw,
        "parsed": parsed,
        "parse_error": error,
        "usage": response.usage.model_dump() if response.usage is not None else None,
        "model_called": True,
        "simulator_action_executed": False,
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    print("=== M6-3C VLM Perception Probe ===")
    print("Image SHA256:", record["image_sha256"])
    print("Model:", MODEL)
    print("Oracle state sent: NO")
    print("Model response:\n", raw)
    print("JSON parsed:", parsed is not None)
    print("Actual action executed: NO")
    print("Saved:", RESULT)
    if error:
        print("PARSE WARNING:", error)
        print("M6-3C CALL COMPLETED; OUTPUT FORMAT REQUIRES REVIEW")
    else:
        print("M6-3C CALL COMPLETED; PERCEPTION ACCURACY REQUIRES REVIEW")


if __name__ == "__main__":
    main()
