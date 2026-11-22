import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import requests

DATASET = "EMBGuard/EMBGuardTest"
API = "https://datasets-server.huggingface.co"

session = requests.Session()
session.trust_env = True

resp = session.get(
    f"{API}/splits",
    params={"dataset": DATASET},
    timeout=60,
)
print("Splits HTTP:", resp.status_code)
resp.raise_for_status()

payload = resp.json()
splits = payload.get("splits", [])

print("\n=== AVAILABLE SPLITS ===")
for item in splits:
    print(
        "config:", item["config"],
        "split:", item["split"],
        "rows:", item.get("num_rows"),
    )

requested = ("HR", "MHR", "HNR", "NHR")

for split_name in requested:
    matches = [
        item for item in splits
        if item["split"].upper() == split_name
    ]

    print(f"\n=== {split_name} ===")

    if not matches:
        print("SPLIT NOT FOUND")
        continue

    item = matches[0]

    response = session.get(
        f"{API}/rows",
        params={
            "dataset": DATASET,
            "config": item["config"],
            "split": item["split"],
            "offset": 0,
            "length": 1,
        },
        timeout=60,
    )

    print("HTTP:", response.status_code)
    response.raise_for_status()

    data = response.json()
    rows = data.get("rows", [])

    if not rows:
        print("NO ROWS")
        continue

    row = rows[0].get("row", {})
    print("Columns:", sorted(row.keys()))

    # Don't print huge image objects or base64.
    for key, value in row.items():
        if key.lower() == "image":
            if isinstance(value, dict):
                print(
                    "image keys:",
                    list(value.keys()),
                )
            else:
                print("image type:", type(value).__name__)
        else:
            text = str(value)
            print(key, ":", text[:400])

print("\nEMBGUARD E3F DATASET PROBE COMPLETE")
