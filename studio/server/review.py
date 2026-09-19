"""
Review gate storage.

Three independent gates:
- script
- storyboard
- clip

Changing the approved asset hash invalidates the related approval.
"""
from datetime import datetime

GATES = ("script", "storyboard", "clip")


def default_state():
    return {
        gate: {
            "status": "pending",
            "approved_hash": None,
            "updated_at": None,
        }
        for gate in GATES
    }


def approve(state, gate, content_hash):
    if gate not in GATES:
        raise ValueError(gate)
    state[gate] = {
        "status": "approved",
        "approved_hash": content_hash,
        "updated_at": datetime.utcnow().isoformat(),
    }
    return state


def validate(state, gate, current_hash):
    item = state.get(gate, {})
    return item.get("status") == "approved" and item.get("approved_hash") == current_hash
