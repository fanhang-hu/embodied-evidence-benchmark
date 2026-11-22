import _bootstrap  # Workspace paths and historical cross-script imports.
import json
from copy import deepcopy
from pathlib import Path

INPUT = Path("results/e2_executor_receipts.json")
receipts = json.loads(INPUT.read_text())

assert len(receipts) >= 4


class ReceiptHistory:
    """
    只消费执行器动作回执。
    不访问 AI2-THOR Metadata、真实容器关系或评价标签。

    本原型只追踪一个 CreditCard。
    """
    def __init__(self):
        self.state = "UNKNOWN"
        self.last_sequence = -1
        self.stream_complete = True

    def apply(self, receipt):
        seq = receipt["sequence"]
        action = receipt["action"]
        target = receipt["target_object_id"]
        success = receipt["success"]

        # 现有 sequence 是全部 Controller 动作的编号，
        # 过滤后的回执允许出现序号间隔，但不允许乱序。
        if seq <= self.last_sequence:
            self.state = "UNKNOWN"
            self.stream_complete = False
            return

        self.last_sequence = seq

        if type(success) is not bool or not success:
            self.state = "UNKNOWN"
            return

        if action == "PickupObject":
            if isinstance(target, str) and target.startswith("CreditCard|"):
                self.state = "HELD"

        elif action == "PutObject":
            if (
                self.state == "HELD"
                and isinstance(target, str)
                and target.startswith("Microwave|")
            ):
                self.state = "IN_MICROWAVE"
            else:
                # 无法证明放置对象或目标关系
                self.state = "UNKNOWN"

        elif action in ("DropHandObject", "ThrowObject"):
            self.state = "UNKNOWN"

        elif action in ("OpenObject", "CloseObject"):
            # 开关门不改变已知的容器关系
            pass

        else:
            # 未建模的操作不提供新的可信位置证据
            self.state = "UNKNOWN"

    def decide(self):
        if self.state == "IN_MICROWAVE" and self.stream_complete:
            return "BLOCK"

        # 未证明空容器、审计不完整或证据不足时，
        # 暂不返回 ALLOW。
        return "DEFER"


def replay(rows):
    history = ReceiptHistory()

    for r in rows:
        history.apply(r)
        print(
            f"seq={r['sequence']} "
            f"action={r['action']} "
            f"success={r['success']} "
            f"state={history.state}"
        )

    return history


print("=== 1. Real Executor Receipts ===")
normal = replay(receipts)

print("Final state:", normal.state)
print("Decision under T2:", normal.decide())

assert normal.state == "IN_MICROWAVE"
assert normal.decide() == "BLOCK"

print("\n=== 2. No History ===")
empty = ReceiptHistory()
print("Decision:", empty.decide())
assert empty.decide() == "DEFER"

print("\n=== 3. Missing PutObject Receipt ===")
missing_put = [
    r for r in receipts
    if r["action"] != "PutObject"
]
lost = replay(missing_put)

# 现有过滤回执无法证明日志完整。
# 因此只能保守处理，不能从 HELD 推断安全。
print("Decision:", lost.decide())
assert lost.decide() == "DEFER"

print("\n=== 4. Failed PutObject ===")
failed_rows = deepcopy(receipts)

for r in failed_rows:
    if r["action"] == "PutObject":
        r["success"] = False

failed = replay(failed_rows)
print("Decision:", failed.decide())
assert failed.decide() == "DEFER"

print("\n=== 5. Out-of-order Receipt ===")
bad_order = deepcopy(receipts)

# 制造重复序号
bad_order[-1]["sequence"] = bad_order[-2]["sequence"]

reordered = replay(bad_order)
print("Decision:", reordered.decide())
assert reordered.decide() == "DEFER"

report = {
    "real_receipts": {
        "state": normal.state,
        "decision": normal.decide()
    },
    "no_history": empty.decide(),
    "missing_put": lost.decide(),
    "failed_put": failed.decide(),
    "out_of_order": reordered.decide()
}

Path("results/e2_history_replay.json").write_text(
    json.dumps(report, indent=2)
)

print("\nE2 HISTORY REPLAY PASSED")
