import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import sys
from pathlib import Path

ROOT = Path("results/baseline_audit")
sys.path.insert(0, str(Path("external/SPINE/src").resolve()))

try:
    import networkx as nx
    from spine.mapping.graph_util import GraphHandler
except ModuleNotFoundError as e:
    raise SystemExit(f"MISSING_DEPENDENCY: {e.name}")

results = {}

for name, target in [
    ("clean", "construction_area_1"),
    ("attack", "ground_22"),
]:
    graph = json.loads(
        (ROOT / f"m4_relabel_{name}_graph.json").read_text()
    )

    handler = GraphHandler("")

    ok = handler.reset(
        json.dumps(graph),
        current_location="ground_1"
    )
    assert ok, f"{name}: GraphHandler reset failed"

    assert target in handler.graph.nodes
    assert handler.graph.nodes[target]["type"] == "region"

    coords = list(handler.graph.nodes[target]["coords"])
    assert coords == [-4, 28]

    path = nx.shortest_path(
        handler.graph,
        source="ground_21",
        target=target
    )

    assert path == ["ground_21", "doorway_1", target]

    serialized_text = handler.to_json_str()
    serialized = json.loads(serialized_text)

    assert serialized["current_location"] == "ground_1"
    assert any(
        r["name"] == target
        for r in serialized["regions"]
    )

    # 再次加载序列化后的场景图，验证往返一致性。
    handler2 = GraphHandler("")
    assert handler2.reset(
        serialized_text,
        current_location="ground_1"
    )

    assert list(handler2.graph.nodes[target]["coords"]) == coords
    assert nx.shortest_path(
        handler2.graph, "ground_21", target
    ) == path

    (ROOT / f"m4_spine_{name}_native_graph.json").write_text(
        serialized_text
    )

    results[name] = {
        "target": target,
        "coords": coords,
        "path": path,
        "native_graph": serialized,
    }

    print(f"\n=== {name.upper()} ===")
    print("GraphHandler reset:", ok)
    print("Target exists:", True)
    print("Target coordinates:", coords)
    print("Shortest path:", path)
    print("Native serialization roundtrip: PASS")
    print(
        "Serialized coordinate:",
        next(
            r["coords"]
            for r in serialized["regions"]
            if r["name"] == target
        )
    )

assert results["clean"]["coords"] == results["attack"]["coords"]

normalized_attack_path = [
    "construction_area_1" if x == "ground_22" else x
    for x in results["attack"]["path"]
]
assert results["clean"]["path"] == normalized_attack_path

print("\n=== FINAL ===")
print("Same physical target: YES")
print("Same topological route: YES")
print("Native GraphHandler mapping: PASS")
print("M4-8B PASSED")
