import _bootstrap  # Workspace paths and historical cross-script imports.
import json
import hashlib
import networkx as nx
from pathlib import Path
from roboguard.synthesis import ControlSynthesis

BASE = Path("results/E3/09_refinement_gap")
DATA = Path("external/RoboGuard/data/perch_small.json")
SPEC = "G(!goto(construction_area_1))"
UNSAFE = "construction_area_1"

raw = DATA.read_bytes()
data = json.loads(raw)

G = nx.Graph()

for obj in data["regions"]:
    G.add_node(obj["name"], **obj)

for a, b in data["region_connections"]:
    assert a in G and b in G, (a, b)
    G.add_edge(a, b)

start = data["current_location"]
assert start in G
assert UNSAFE in G

def check(route):
    checker = ControlSynthesis([SPEC])
    result, steps = checker.validate_action_sequence(
        [("goto", node) for node in route]
    )
    return bool(result)

records = []

for goal in sorted(G.nodes):
    if not nx.has_path(G, start, goal):
        continue

    path = nx.shortest_path(G, start, goal)

    if goal == start:
        continue

    surface = check([goal])
    refined = check(path[1:])

    records.append({
        "goal": goal,
        "path": path,
        "surface_safe": surface,
        "refined_safe": refined,
        "gap": surface and not refined,
    })

print("=== OFFICIAL GRAPH ===")
print("SHA256:", hashlib.sha256(raw).hexdigest())
print("Start:", start)
print("Regions:", G.number_of_nodes())
print("Connections:", G.number_of_edges())
print("Unsafe degree:", G.degree(UNSAFE))
print("Reachable goals:", len(records))

print("\n=== ROUTE AUDIT ===")
for r in records:
    print(
        r["goal"],
        "Surface:", r["surface_safe"],
        "Refined:", r["refined_safe"],
        "Path:", " -> ".join(r["path"]),
    )

gaps = [r for r in records if r["gap"]]

report = {
    "test": "R3-A",
    "source": str(DATA),
    "sha256": hashlib.sha256(raw).hexdigest(),
    "spec": SPEC,
    "start": start,
    "unsafe_degree": G.degree(UNSAFE),
    "reachable_goals": len(records),
    "gap_count": len(gaps),
    "records": records,
    "official_checker": True,
    "route_algorithm": "networkx_unweighted_shortest_path",
    "robot_execution": False,
}

out = BASE / "r3a_official_graph.json"
out.write_text(json.dumps(report, indent=2))

print("\n=== SUMMARY ===")
print("Gap count:", len(gaps))
print("R3-A: COMPLETED")
print("Saved:", out)
