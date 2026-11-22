import _bootstrap  # Workspace paths and historical cross-script imports.
from pathlib import Path
import shutil
import textwrap

path = Path("e3_baseline/b7_percepttwin/e3_percepttwin_p24b_native_plan.py")
s = path.read_text()

marker = "P24_B_SPATIAL_RELATION_FIX_V1"

if marker in s:
    print("Already patched:", path)
    raise SystemExit(0)

anchor1 = "    def inspect_after(action_name, cb=None):\n"
anchor2 = (
    '        if name == "PickupObject":\n'
    '            callback_result = {}\n'
)

assert s.count(anchor1) == 1, "inspect_after anchor changed"
assert s.count(anchor2) == 1, "PickupObject anchor changed"

helper = r'''
# P24_B_SPATIAL_RELATION_FIX_V1
# Repair only a verified reversed Pan/CounterTop relation.

def reconcile_initial_pan_support():
    truth = unity_objects()

    support_ids = [
        oid for oid in sim.current_object_container.object_names
        if oid.startswith("CounterTop|")
    ]

    assert len(support_ids) == 1, support_ids
    countertop = support_ids[0]

    # Ground truth must show Pan resting on CounterTop.
    parents = truth[pan].get("parentReceptacles") or []

    assert parents == [countertop], (
        "Unexpected Pan parents", parents
    )
    assert truth[pan].get("isPickedUp") is False

    # Do not remove a genuine obstruction.
    physical_children = [
        oid for oid, obj in truth.items()
        if oid != pan
        and pan in (obj.get("parentReceptacles") or [])
    ]

    pan_children = (
        truth[pan].get("receptacleObjectIds") or []
    )

    assert not physical_children and not pan_children, (
        "Pan may actually contain objects",
        physical_children,
        pan_children,
    )

    container = sim.current_object_container

    incorrectly_on_pan = (
        container.get_objects_that_are_on_obj(pan)
    )

    assert incorrectly_on_pan == [countertop], (
        "Unexpected native obstruction",
        incorrectly_on_pan,
    )

    p_idx = container.object_names.index(pan)
    c_idx = container.object_names.index(countertop)

    reverse_before = bool(
        container.obj_isOnTopOf[c_idx, p_idx]
    )

    forward_before = bool(
        container.obj_isOnTopOf[p_idx, c_idx]
    )

    assert reverse_before is True
    assert forward_before is False

    # Remove the incorrect reverse relation.
    rel = container.obj_isOnTopOf.at[
        c_idx, p_idx
    ].set(False)

    # Restore the physically correct support relation.
    rel = rel.at[p_idx, c_idx].set(True)

    # Update only the latest native state.
    sim.object_containers[-1] = container.replace(
        obj_isOnTopOf=rel
    )

    repaired = sim.current_object_container

    assert repaired.is_obj_surface_free(pan)
    assert (
        repaired.get_obj2id_that_obj1id_is_ontop_of(pan)
        == countertop
    )

    report["spatial_relation_fix"] = {
        "scope": "Pan_CounterTop_only",
        "origin": "P24-B runtime adapter",
        "unity_pan_parentReceptacles": parents,
        "unity_pan_children": physical_children,
        "native_countertop_on_pan_before": reverse_before,
        "native_pan_on_countertop_before": forward_before,
        "native_countertop_on_pan_after": False,
        "native_pan_on_countertop_after": True,
        "original_pickup_preconditions_preserved": True,
    }

    print(
        "P24-B relation fix: "
        "CounterTop->Pan removed, "
        "Pan->CounterTop restored",
        flush=True,
    )
'''

new_s = s.replace(
    anchor1,
    textwrap.indent(
        textwrap.dedent(helper).strip("\n") + "\n\n",
        "    ",
    ) + anchor1,
    1,
)

new_s = new_s.replace(
    anchor2,
    '        if name == "PickupObject":\n'
    '            reconcile_initial_pan_support()\n'
    '            callback_result = {}\n',
    1,
)

# Avoid printing the full native container on exception.
old_err = (
    '    report["error"] = repr(exc)\n'
    '    traceback.print_exc()'
)

new_err = (
    '    report["error"] = '
    'f"{type(exc).__name__}: {str(exc)[:500]}"\n'
    '    print("P24-B ERROR:", report["error"], flush=True)\n'
    '    print("".join(traceback.format_tb('
    'exc.__traceback__, limit=8)), flush=True)'
)

if old_err in new_s:
    new_s = new_s.replace(old_err, new_err, 1)

# Compile before modifying the runner.
compile(new_s, str(path), "exec")

backup = path.with_name(
    "e3_percepttwin_p24b_native_plan.before_spatial_fix.py"
)

if not backup.exists():
    shutil.copy2(path, backup)

path.write_text(new_s)

print("Patched:", path)
print("Backup:", backup)
print("Original PerceptTwin source files unchanged.")
