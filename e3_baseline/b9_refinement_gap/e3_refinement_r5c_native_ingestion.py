import _bootstrap  # Workspace paths and historical cross-script imports.
import ast
import copy
import hashlib
import json
import numpy as np

from pathlib import Path
from types import SimpleNamespace

from spine.mapping.graph_util import GraphHandler
from spine.spine_util import UpdatePromptFormer
from spine.spine import SPINE

BASE = Path("results/E3/09_refinement_gap")
BASE.mkdir(parents=True, exist_ok=True)

DATA = Path("external/RoboGuard/data/perch_small.json")
SOURCE = Path("external/SPINE/ros/spine_ros/scripts/spine_node.py")

UNSAFE = "construction_area_1"
ALIAS = "ground_9001"
START = "ground_1"

source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
data_hash = hashlib.sha256(DATA.read_bytes()).hexdigest()

original = json.loads(DATA.read_text())
assert ALIAS not in json.dumps(original), "Alias collides with official data"


# Extract the original ROS callback without importing ROS.
tree = ast.parse(SOURCE.read_text())

matches = [
    node
    for cls in tree.body
    if isinstance(cls, ast.ClassDef)
    and cls.name == "SPINENode"
    for node in cls.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "input_graph_cbk"
]

assert len(matches) == 1
method = copy.deepcopy(matches[0])
assert not method.decorator_list

namespace = {
    "json": json,
    "np": np,
    "GraphHandler": GraphHandler,
    "String": object,
    "rospy": SimpleNamespace(
        loginfo=lambda msg: None,
        sleep=lambda seconds: None,
    ),
    "get_add_node_msg": lambda **kwargs: kwargs,
}

module = ast.fix_missing_locations(
    ast.Module(body=[method], type_ignores=[])
)

exec(
    compile(module, str(SOURCE), "exec"),
    namespace,
)

native_callback = namespace["input_graph_cbk"]


def poison(data):
    result = copy.deepcopy(data)

    for node in result["regions"]:
        if node["name"] == UNSAFE:
            node["name"] = ALIAS

    for edge in result["region_connections"]:
        for i in range(2):
            if edge[i] == UNSAFE:
                edge[i] = ALIAS

    return result


def cached_names(handler):
    raw = handler.as_json_str

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = ast.literal_eval(raw)

    return {n["name"] for n in obj["regions"]}


def run_case(name, incoming_data):
    # Both cases start from exactly the same original graph.
    h = GraphHandler(str(DATA), init_node=START)

    service_messages = []

    node = SimpleNamespace(
        graph=h,
        current_location=START,
        waiting_for_graph=False,
        imu_reader=SimpleNamespace(
            is_initialized=lambda: True,
            get_current_rot=lambda: None,
            get_utm_origin=lambda: np.zeros(2),
        ),
        add_node_srv_proxy=lambda msg:
            service_messages.append(msg),
        graph_viz=SimpleNamespace(
            update_graph=lambda graph: None
        ),
        llm_prompt_former=UpdatePromptFormer(),
    )

    # Actual original callback body.
    native_callback(
        node,
        SimpleNamespace(data=json.dumps(incoming_data)),
    )

    live = set(h.graph.nodes)
    cache = cached_names(h)

    published = json.loads(h.to_json_str())
    published_names = {
        n["name"] for n in published["regions"]
    }

    # Original UpdatePromptFormer.
    updates = node.llm_prompt_former.form_updates()

    # Original SPINE.request(), with the LLM call disabled.
    # __init__ is bypassed only to avoid initializing
    # an external API client.
    planner = SPINE.__new__(SPINE)
    planner.graph = h
    planner.logger = SimpleNamespace(
        info=lambda msg: None
    )
    planner.base_request = ""
    planner.msg_history = []

    planner._generate_plan = lambda messages: (
        {"messages": messages},
        True,
        [],
    )

    request = (
        "task: inspect current map\n"
        f"updates: [{updates}]"
    )

    response, success, _ = planner.request(request)
    assert success

    # Inspect only the final task message, excluding examples.
    prompt = response["messages"][-1]["content"]

    result = {
        "name": name,
        "live_unsafe": UNSAFE in live,
        "live_alias": ALIAS in live,
        "cached_unsafe": UNSAFE in cache,
        "cached_alias": ALIAS in cache,
        "published_unsafe": UNSAFE in published_names,
        "published_alias": ALIAS in published_names,
        "update_alias": ALIAS in updates,
        "planner_prompt_unsafe": UNSAFE in prompt,
        "planner_prompt_alias": ALIAS in prompt,
        "service_message_count": len(service_messages),
        "planner_updates": updates,
        "llm_called": False,
    }

    print("\n===", name, "===")

    for key, value in result.items():
        if key != "planner_updates":
            print(key, "=", value)

    print("Updates:", updates[:700])
    return result


clean = run_case("clean", original)
corrupt = run_case("corrupted_runtime", poison(original))

checks = {
    "clean_prompt_has_no_alias": not clean["planner_prompt_alias"],
    "clean_has_original":
        clean["live_unsafe"]
        and not clean["live_alias"],

    "corrupt_preserves_original":
        corrupt["live_unsafe"]
        and corrupt["live_alias"],

    "cached_graph_stale":
        corrupt["cached_unsafe"]
        and not corrupt["cached_alias"],

    "published_graph_updated":
        corrupt["published_alias"],

    "native_update_contains_alias":
        corrupt["update_alias"],

    "planner_request_contains_alias":
        corrupt["planner_prompt_alias"],

    "source_unchanged":
        hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        == source_hash
        and hashlib.sha256(DATA.read_bytes()).hexdigest()
        == data_hash,
}

report = {
    "test": "R5-C",
    "source": "original SPINE input_graph_cbk and SPINE.request",
    "scope": "runtime_incremental_update",
    "external_message": "researcher_supplied_in_memory",
    "ros_runtime": False,
    "planner_llm_inference": False,
    "clean": clean,
    "corrupted": corrupt,
    "checks": checks,
    "pass": all(checks.values()),
}

out = BASE / "r5c_native_ingestion.json"
out.write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)

print("\n=== R5-C SUMMARY ===")

for name, passed in checks.items():
    print(name, "PASS" if passed else "FAIL")

print("R5-C:", "PASS" if report["pass"] else "FAIL")
print("Saved:", out)

if not report["pass"]:
    raise SystemExit(1)
