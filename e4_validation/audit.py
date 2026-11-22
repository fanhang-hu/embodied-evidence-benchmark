"""Read-only source/permissions audit; does not execute upstream model scripts."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import os
import stat
import tempfile
from pathlib import Path

from e4_validation.simulator import ROOT


def sha(value):
    return hashlib.sha256(value).hexdigest()


def source_record(path, names):
    data = path.read_bytes()
    tree = ast.parse(data)
    functions = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names:
            functions.append(dict(name=n.name, line=n.lineno, end_line=n.end_lineno))
    s = path.stat()
    return dict(path=str(path), sha256=sha(data), uid=s.st_uid, gid=s.st_gid,
                mode=stat.filemode(s.st_mode), functions=functions)


CAPABILITIES = [
    [1, "RoboGuard", "A", "semantic map", "adapted online", "LTL pre-execution", "navigation submission only", "accurate-map safety assumption", "N", "e3_baseline/b1_roboguard/README.md"],
    [2, "SafeGate-inspired", "M", "kitchen state copy", "no native planner", "researcher Z3 contract", "adapted Unity", "researcher contract", "K", "e3_baseline/b2_safegate/README.md"],
    [3, "RoboSafe-inspired", "M", "RGB+history adapted", "not joint native", "researcher fusion", "offline", "researcher policy", "K", "e3_baseline/b3_robosafe/README.md"],
    [4, "EMBGuard", "O model / A fusion", "official RGB+Action; adapted state gate", "absent in live fusion", "official classifier+adapted gate", "Unity fusion experiment", "V0/V1 must distinguish", "K", "e3_baseline/b4_embguard/README.md"],
    [5, "HD-Guard", "A", "video frames", "N/A", "alert only", "N/A pre-execution", "video risk categories", "alert", "e3_baseline/b5_hdguard/README.md"],
    [6, "SELP", "O component / M mapping", "symbolic cookbook", "component only", "constrained decoding", "not full official chain", "adapted predicates", "K component", "e3_baseline/b6_selp/README.md"],
    [7, "PerceptTwin", "A", "digital twin objects", "adapted original planner", "posthoc native judge+added pre-gate", "Unity skills, no physical robot", "researcher empty-burner policy", "K", "e3_baseline/b7_percepttwin/README.md"],
    [8, "GuardAgent", "A / M embodied", "software tools / proxy state", "software agent", "software permissions", "embodied intercepted", "embodied core N/A", "software supplement", "e3_baseline/b8_guardagent/README.md"],
    [9, "Refinement Gap", "A component", "SPINE shared semantic map", "SPINE adapted", "RoboGuard LTL", "intercepted no ROS navigation", "map alias grounding", "N", "e3_baseline/b9_refinement_gap/README.md"],
]


def main():
    import ai2thor.controller
    import ai2thor.fifo_server
    import ai2thor.server

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [
        (Path(ai2thor.controller.__file__), {"step", "start", "reset"}),
        (Path(ai2thor.fifo_server.__file__), {"__init__", "_recv_message", "receive", "start"}),
        (Path(ai2thor.server.__file__), {"create_event", "__init__"}),
        (ROOT / "external/SafeAgentBench/low_level_controller/low_level_controller.py", {"get_obj_information", "get_obj_id_from_name", "turn_on", "turn_off", "pick", "put", "llm_skill_interact"}),
        (ROOT / "external/SafeAgentBench/methods/map_vlm.py", {"get_info_env", "single_agent_table_planning", "single_agent_vision_planning", "run_map"}),
        (ROOT / "external/SafeAgentBench/methods/utils.py", {"gen_low_level_plan", "execute_low_level_plan"}),
        (ROOT / "external/safe-hierarchical-embodied-ai/src/ae_rl/execution/kitchen_safety.py", {"build_kitchen_snapshot", "infer_stove_knob_burner_map", "check_toggle_scene_safety"}),
        (ROOT / "external/safe-hierarchical-embodied-ai/src/ae_rl/rl/interaction/controller.py", {"toggle_object"}),
        (ROOT / "external/SPINE/src/spine/mapping/graph_util.py", {"update_with_node", "update_node_description", "update_with_edge"}),
    ]
    # Real native transport construction; no Unity and no pipe injection.
    server = ai2thor.fifo_server.FifoServer(640, 480)
    try:
        server.start()
        permissions = []
        for p in [server.tmp_dir.name, server.server_pipe_path, server.client_pipe_path]:
            s = os.stat(p)
            permissions.append(dict(path=p, uid=s.st_uid, gid=s.st_gid,
                                    mode=stat.filemode(s.st_mode), mode_octal=oct(stat.S_IMODE(s.st_mode))))
    finally:
        server.stop()
        server.tmp_dir.cleanup()
    # Actual native low-level reader consumes explicitly supplied metadata copy.
    # This proves the read edge, not a low-privilege write edge or exploit.
    from types import SimpleNamespace
    from low_level_controller.low_level_controller import LowLevelPlanner
    import copy
    event_data = {"objects": [{"objectId": "StoveKnob|audit", "objectType": "StoveKnob", "isToggled": True}],
                  "agent": {"position": {"y": .9}}, "screenWidth": 640, "screenHeight": 480}
    native_event = ai2thor.server.Event(copy.deepcopy(event_data))
    reader = LowLevelPlanner(SimpleNamespace(last_event=native_event))
    before = reader.get_obj_information("StoveKnob|audit")["isToggled"]
    native_event.metadata["objects"][0]["isToggled"] = False
    after = reader.get_obj_information("StoveKnob|audit")["isToggled"]
    report = dict(classification="T0 CONTROLLED-COPY ONLY", native_T1_demonstrated=False,
                  native_T2_demonstrated=False, ai2thor_version=importlib.metadata.version("ai2thor"),
                  interpreter=os.sys.executable, sources=[source_record(p, n) for p, n in sources],
                  fifo_permissions=permissions,
                  native_reader_probe=dict(kind="synthetic Event input / native reader", before=before,
                                           after=after, simulator_running=False, lower_privilege_write_proven=False),
                  native_safeagent_monitor="No unified pre-execution gate in audited methods/low-level path",
                  independent_recheck="Unity Pass is simulator-authoritative X upper bound under T0 adapter scope")
    (args.output / "source_audit.json").write_text(json.dumps(report, indent=2))
    with (args.output / "capability_matrix.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["baseline", "name", "implementation", "consumer", "planner", "monitor", "executor", "policy", "track", "evidence"])
        writer.writerows(CAPABILITIES)
    print(json.dumps({"classification": report["classification"], "source_files": len(sources),
                      "fifo_permissions": permissions, "native_reader_probe": report["native_reader_probe"]}, indent=2))


if __name__ == "__main__":
    main()
