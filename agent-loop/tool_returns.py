"""Change 3, what the loop hands back when a tool fails.

A raw traceback tells the model that something broke, and not what to do about it. A timeout
looks temporary, so the model tries again. One plain sentence says what failed and what to do
next, and the result is flagged as an error.
"""

import sys

import tools
from loop import MODEL, run_agent
from meter import Meter, compare

# Decision: your own code owns the retry policy, so the tool says plainly that a retry won't help.
CARRIER_DOWN = ("Carrier tracking is not responding, so trying again won't help right now. "
                "Answer without tracking and say it's unavailable.")


def run_tool(block, meter: Meter) -> dict:
    meter.lookup(block.name, *block.input.values())
    try:
        output = tools.lookup(block.name, *block.input.values())
        return {"type": "tool_result", "tool_use_id": block.id, "content": output}
    except tools.CarrierTimeout:
        # Decision: one sentence written for the model, saying what failed and what to do next.
        # A timeout looks temporary, so without it the model tries again. is_error marks the failure.
        return {"type": "tool_result", "tool_use_id": block.id, "content": CARRIER_DOWN, "is_error": True}


def with_clear_returns(task: str, meter: Meter) -> str:
    return run_agent(task, meter, run_tool=run_tool)


if __name__ == "__main__":
    tools.carrier_down = True
    task = sys.argv[1] if len(sys.argv) > 1 else "Where is order O-1042 right now, and when will it arrive?"
    compare(task, MODEL, {"before: raw traceback": run_agent, "after: one clear return": with_clear_returns},
            int(sys.argv[2]) if len(sys.argv) > 2 else 1)
