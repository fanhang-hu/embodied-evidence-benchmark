import _bootstrap  # Workspace paths and historical cross-script imports.
from pathlib import Path
from huggingface_hub import hf_hub_download
import pyarrow.parquet as pq

REPO = "EMBGuard/EMBGuardTest"
REVISION = "48f2eb559b669dd900328001e4771478bababe4c"
LOCAL = Path("external/EMBGuardTest-v1")

for split in ["HR", "MHR", "HNR", "NHR"]:
    filename = f"data/{split}-00000-of-00001.parquet"

    print(f"\n=== {split} ===", flush=True)

    path = hf_hub_download(
        repo_id=REPO,
        repo_type="dataset",
        filename=filename,
        revision=REVISION,
        local_dir=str(LOCAL),
        token=False,
    )

    pf = pq.ParquetFile(path)

    print("File:", path)
    print("Rows:", pf.metadata.num_rows)
    print("Bytes:", Path(path).stat().st_size)
    print("Columns:", pf.schema_arrow.names)

    assert pf.metadata.num_rows > 0
    assert {
        "ID", "Action", "Risk", "Risk Type", "image"
    }.issubset(pf.schema_arrow.names)

print("\nEMBGUARD E3F FOUR SPLITS DATA PASS")
